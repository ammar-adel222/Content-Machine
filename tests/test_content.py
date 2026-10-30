import contextlib
import io
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
from pydantic import ValidationError
from war_content.agent import ContentAgent, ContentError, Library, OfflineModel, asset_key, check_manifest
from war_content.models import Asset, Brief, DesignReview, ManifestReview, Primitive, Vertex
from war_content.storage import save
from war_director.agent import barrier_for
from war_director.models import AudioTiming
from war_research.providers import ProviderError
from war_writer.agent import fingerprint
from .content_helpers import ContentModel, asset, design, manifest, passing, ready


class GeometryTests(unittest.TestCase):
    def test_bounded_visible_primitives(self):
        for values in ({'kind':'rect','x':1}, {'kind':'rect','width':float('nan')},
                       {'kind':'ellipse','points':[{'x':0,'y':0}]},
                       {'kind':'rect','fill':'none','stroke':'none'},
                       {'kind':'line','points':[{'x':0,'y':0},{'x':1,'y':0}]},
                       {'kind':'polygon','points':[{'x':0,'y':0}]*3}):
            with self.subTest(values=values),self.assertRaises(ValidationError):Primitive(**values)
        for points in ([{'x':0,'y':0},{'x':.5,'y':0},{'x':1,'y':0}],):
            with self.assertRaises(ValidationError):Primitive(kind='polygon',points=points)
        self.assertEqual(Primitive(kind='line',fill='none',points=[Vertex(x=-.5,y=0),Vertex(x=.5,y=0)]).kind,'line')
        self.assertEqual(Primitive(kind='polygon',points=[Vertex(x=0,y=0),Vertex(x=.8,y=0),Vertex(x=0,y=.8)]).kind,'polygon')

    def test_new_terrain_kind_obeys_movement_domain(self):
        d,s,p=ready();terrain=p.blueprint.terrain[0].model_copy(deep=True);terrain.kind='desert_dunes'
        fleet=p.blueprint.forces[0].model_copy(update={'kind':'fleet'})
        self.assertTrue(barrier_for(fleet,terrain))
        terrain.kind='sea';self.assertFalse(barrier_for(fleet,terrain))
        payload=terrain.model_dump();payload['kind']='cliff';self.assertEqual(type(terrain).model_validate(payload).kind,'cliff')


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.library=Library(self.root/'library')
        self.d,self.s,self.p=ready();self.m=manifest(self.d,self.p)

    def build(self,model=None,**kwargs):
        return ContentAgent(model or ContentModel(self.m),self.library).build(self.d,self.s,self.p,**kwargs)

    def test_generate_cache_reuse_and_manifest_preservation(self):
        model=ContentModel(self.m);result=self.build(model)
        self.assertEqual(result.status,'ready');self.assertEqual(result.model_calls,6)
        self.assertEqual(len(result.assets),2);self.assertEqual(len(self.library.briefs()),2)
        cached=self.build(manifest=self.m)
        self.assertEqual(cached.model_calls,0);self.assertEqual(len(cached.reused),2)
        self.assertEqual(cached.manifest,self.m)
        before=asset_key(self.m.bindings[0].brief)
        changed=self.m.bindings[0].brief.model_copy(update={'description':'Different historically supported equipment silhouette.'})
        self.assertNotEqual(before,asset_key(changed))
        self.assertEqual(self.build(OfflineModel(),manifest=self.m).status,'ready')

    def test_manifest_semantic_audit_and_offline_missing_design(self):
        for response in (ManifestReview(issues=['Infantry evidence does not support tanks.']),ProviderError('Unavailable')):
            result=self.build(ContentModel(replies=[self.m,response]))
            self.assertEqual(result.status,'needs_revision');self.assertEqual(result.assets,{})
        with self.assertRaises(ContentError):self.build(OfflineModel())
        self.assertEqual(self.build(OfflineModel(),manifest=self.m).status,'needs_revision')

    def test_invalid_manifest_is_not_renderable(self):
        self.m.bindings[0].evidence_quote='This statement is invented.'
        self.assertIn('exact quote',' '.join(check_manifest(self.m,self.d,self.p)))
        result=self.build(manifest=self.m);self.assertEqual(result.status,'needs_revision');self.assertEqual(result.model_calls,0)
        self.m.bindings[0].object_id='unknown'
        self.m.bindings.append(self.m.bindings[-1])
        self.assertGreaterEqual(len(check_manifest(self.m,self.d,self.p)),2)

    def test_input_identity_readiness_review_and_timeline(self):
        for field,value in (('status','needs_revision'),('dossier_sha256','wrong'),('script_sha256','wrong'),
                            ('issues',['Known issue']),('review',None),('timeline',[]),('timing_basis','measured')):
            plan=self.p.model_copy(update={field:value},deep=True)
            with self.subTest(field=field),self.assertRaises(ContentError):ContentAgent(ContentModel(),self.library).build(self.d,self.s,plan)
        with self.assertRaises(ValueError):self.build(max_model_calls=0)

    def test_repair_rejected_design_and_budget_failure(self):
        rejected=passing().model_copy(update={'recognizable':False,'issues':['Needs distinctive silhouette.']})
        model=ContentModel(replies=[design(),rejected,design(),passing()])
        self.assertEqual(self.build(model,manifest=self.m).status,'ready')
        self.assertTrue(any('REPAIR' in p for p in model.prompts))
        self.library=Library(self.root/'other')
        model=ContentModel(replies=[design(),rejected,design(),rejected])
        self.assertEqual(self.build(model,manifest=self.m).status,'needs_revision')
        self.library=Library(self.root/'budget')
        result=self.build(manifest=self.m,max_model_calls=1)
        self.assertEqual(result.status,'needs_revision');self.assertEqual(result.model_calls,1)
        self.assertEqual(self.library.briefs(),[])
        result=self.build(ContentModel(replies=[ProviderError('Offline'),ProviderError('Offline')]),manifest=self.m)
        self.assertEqual(result.status,'needs_revision')
        result=self.build(ContentModel(replies=[ProviderError('Temporary')]),manifest=self.m)
        self.assertEqual(result.status,'ready')

    def test_failed_shared_design_is_not_attempted_again_for_another_force(self):
        rejected=passing().model_copy(update={'recognizable':False,'issues':[]})
        model=ContentModel(replies=[design(),rejected,design(),rejected])
        result=self.build(model,manifest=self.m)
        self.assertEqual(result.status,'needs_revision')
        self.assertEqual(result.model_calls,6)
        self.assertEqual(len(result.draft_designs),1)
        self.assertIn('reviewer rejected',' '.join(result.issues))

    def test_library_corruption_and_rejected_records(self):
        brief=self.m.bindings[0].brief;record=asset(brief)
        record.review.recognizable=False
        with self.assertRaises(ContentError):self.library.put(record)
        self.library.root.mkdir();path=self.library.root/(asset_key(brief)+'.json')
        path.write_text('broken',encoding='utf-8');self.assertEqual(self.library.briefs(),[])
        with self.assertRaises(ContentError):self.library.get(brief)
        path.write_text(record.model_dump_json(),encoding='utf-8')
        with self.assertRaises(ContentError):self.library.get(brief)
        path.write_text(asset(brief.model_copy(update={'concept':'cavalry'})).model_dump_json(),encoding='utf-8')
        with self.assertRaises(ContentError):self.library.get(brief)
        changed=asset(brief);changed.design.label='Changed after review'
        path.write_text(changed.model_dump_json(),encoding='utf-8')
        with self.assertRaises(ContentError):self.library.get(brief)
        with self.assertRaises(ContentError):self.library.put(changed)

    def test_rendered_review_upgrades_cache_and_uses_independent_reviewer(self):
        self.build(manifest=self.m)
        designer,reviewer=ContentModel(),ContentModel()
        engine=ContentAgent(designer,self.library,preview=lambda design:b'png-fixture',reviewer=reviewer)
        result=engine.build(self.d,self.s,self.p,manifest=self.m)
        self.assertEqual(result.status,'ready');self.assertEqual(result.model_calls,2)
        self.assertEqual(designer.prompts,[])
        self.assertTrue(all(a.review_basis=='rendered_image' for a in result.assets.values()))
        self.assertTrue(all('attached REAL render' in p for p in reviewer.prompts))
        cached=engine.build(self.d,self.s,self.p,manifest=self.m)
        self.assertEqual(cached.model_calls,0);self.assertEqual(len(cached.reused),2)

    def test_measured_timing_contract(self):
        from war_director.agent import phrase_times,retime
        clock=phrase_times(self.s)
        pauses={f'{s.id}.p{i}':p.pause_after_ms/1000 for s in self.s.draft.scenes for i,p in enumerate(s.phrases,1)}
        audio=AudioTiming(script_sha256=fingerprint(self.s),durations={key:end-start-pauses[key] for key,(start,end) in clock.items()})
        plan=retime(self.p,self.d,self.s,audio)
        result=ContentAgent(ContentModel(),self.library).build(self.d,self.s,plan,manifest=self.m,audio=audio)
        self.assertEqual(result.status,'ready')
        with self.assertRaises(ContentError):self.build(manifest=self.m,audio=audio)
        with self.assertRaises(ContentError):save(result,plan,self.s,self.root/'missing-audio')
    def test_bundle_storage_ready_incomplete_and_invalid_inputs(self):
        result=self.build(manifest=self.m)
        pixi=self.root/'pixi.js';pixi.write_text('// fixture',encoding='utf-8')
        folder=save(result,self.p,self.s,self.root/'bundles',pixi=pixi)
        payload=json.loads((folder/'scene.json').read_text(encoding='utf-8'))
        self.assertEqual(set(payload['bindings']['unit']),{'west','east'})
        self.assertEqual(len(payload['scenes']),4);self.assertTrue((folder/'player.mjs').exists())
        with self.assertRaises(ContentError):save(result,self.p,self.s.model_copy(update={'topic':'changed'}),self.root/'bad')
        with self.assertRaises(ContentError):save(result,self.p,self.s,self.root/'missing')
        result.assets={}
        with self.assertRaises(ContentError):save(result,self.p,self.s,self.root/'unresolved',pixi=pixi)
        result.status='needs_revision';result.issues=['No valid asset.']
        folder=save(result,self.p,self.s,self.root/'blocked')
        self.assertFalse((folder/'scene.json').exists());self.assertTrue((folder/'report.md').exists())

    def test_saving_changed_asset_rejects_stale_review(self):
        result=self.build(manifest=self.m)
        next(iter(result.assets.values())).design.label='Changed after review'
        pixi=self.root/'pixi.js';pixi.write_text('// fixture',encoding='utf-8')
        with self.assertRaises(ContentError):save(result,self.p,self.s,self.root/'changed-asset',pixi=pixi)

    def test_cli_success_and_failure(self):
        from war_content.__main__ import main
        files=[]
        for name,model in (('dossier',self.d),('script',self.s),('plan',self.p)):
            path=self.root/(name+'.json');path.write_text(model.model_dump_json(),encoding='utf-8');files.append(str(path))
        pixi=self.root/'pixi.js';pixi.write_text('// fixture',encoding='utf-8')
        env=self.root/'.env';env.write_text('GEMINI_API_KEY=fake-key\nGROQ_API_KEY=fake-key\n',encoding='utf-8')
        with patch('war_content.__main__.LanguageModel',return_value=ContentModel(self.m)) as client,patch('war_content.__main__.render_preview',return_value=b'png'),patch.dict('os.environ',{'CONTENT_MODEL':'qwen/qwen3.8-27b'}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(files+['--output',str(self.root/'cli'),'--library',str(self.root/'cache'),'--env-file',str(env),'--pixi',str(pixi)]),0)
            self.assertEqual(client.call_args.args[0][0][:2],('groq','qwen/qwen3.8-27b'))
            self.assertEqual(main(['missing.json',*files[1:],'--env-file',str(env)]),1)
            Path(files[0]).write_text('{}',encoding='utf-8')
            self.assertEqual(main(files+['--env-file',str(env)]),1)


class PreviewTests(unittest.TestCase):
    def test_renderer_success_failures_and_timeout(self):
        from war_content.preview import render_preview
        def render(args,**kwargs):
            self.assertEqual(json.loads(Path(args[2]).read_text())['label'],design().label)
            Path(args[3]).write_bytes(b'png-fixture')
            return SimpleNamespace(returncode=0)
        with patch('war_content.preview.subprocess.run',side_effect=render):self.assertEqual(render_preview(design()),b'png-fixture')
        with patch('war_content.preview.subprocess.run',return_value=SimpleNamespace(returncode=1)),self.assertRaises(ContentError):render_preview(design())
        for error in (OSError('No node'),subprocess.TimeoutExpired('node',45)):
            with patch('war_content.preview.subprocess.run',side_effect=error),self.assertRaises(ContentError):render_preview(design())


class ImageProviderTests(unittest.TestCase):
    def test_inline_image_payloads_and_validation(self):
        from war_research.providers import LanguageModel
        for provider in ('gemini','groq','openrouter'):
            payloads=[]
            def transport(url,payload,headers,**kwargs):
                payloads.append(payload)
                content=passing().model_dump_json()
                return {'candidates':[{'content':{'parts':[{'text':content}]}}]} if provider=='gemini' else {'choices':[{'message':{'content':content}}]}
            model=LanguageModel([(provider,'fake','key')],transport=transport)
            model.generate('Inspect',DesignReview,lambda:None,images=[('image/png','aGVsbG8=')])
            if provider=='gemini':self.assertEqual(payloads[0]['contents'][0]['parts'][1]['inlineData']['mimeType'],'image/png')
            else:self.assertIn('data:image/png;base64,',payloads[0]['messages'][1]['content'][1]['image_url']['url'])
            with self.assertRaises(ValueError):model.generate('Inspect',DesignReview,lambda:None,images=[('text/plain','bad')])
