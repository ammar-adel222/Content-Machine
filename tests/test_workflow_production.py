"""Production adapters use real saved contracts; external providers/encoders are injected."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from war_content.models import Manifest, ManifestReview, Design, DesignReview, Brief
from war_content.agent import check_manifest
from war_content.geodata import Battlefield, HeightGrid
from war_workflow.models import Edit
from war_workflow.planner import fingerprint
from war_workflow.store import ProjectStore, WorkflowError
from war_workflow.production import FrameReview, render
from .content_helpers import manifest, ready, design, passing
from .test_geography import layer


class VisualModel:
    def __init__(self):
        d,s,p=ready();self.requirements=manifest(d,p);self.used=[];self.calls=[];self.responses={}
    def generate(self,prompt,schema,consume,**kwargs):
        consume();self.used.append('synthetic:visual');self.calls.append((schema,prompt,kwargs))
        if self.responses.get(schema):return deepcopy(self.responses[schema].pop(0))
        if schema is Manifest:
            category='terrain' if prompt.startswith('Plan only terrain') else 'unit'
            return Manifest(bindings=[b for b in self.requirements.bindings if b.brief.category==category])
        if schema is FrameReview:return FrameReview(phone_readable=True,terrain_clear=True,units_distinct=True,captions_clear=True)
        return ManifestReview() if schema is ManifestReview else passing() if schema is DesignReview else design()


@unittest.skipUnless(importlib.util.find_spec('langgraph'),'Install workflow extra')
class ProductionTests(unittest.TestCase):
    def setUp(self):
        from war_workflow.graph import Runner
        from war_workflow.authoring import adapters
        from war_workflow.speech import adapters as speech
        from war_workflow.production import adapters as production
        from .test_workflow_authoring import Model
        from .test_narration import Speech
        from .helpers import FakeWeb
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=ProjectStore.create(self.root/'project','Example Battle')
        revision=self.store.load();revision.params['terrain']={'mode':'schematic'};self.store.save(revision)
        self.model=Model();self.visual=VisualModel();self.speech=Speech(24);self.renders=[]
        def renderer(bundle,target,seconds=None,fps=30,aspect='portrait'):
            self.renders.append((Path(bundle),Path(target),seconds,fps,aspect));Path(target).write_bytes(b'Synthetic encoded fixture')
        self.renderer=renderer
        self.info={'format':{'duration':'97'},'streams':[{'codec_type':'video','width':1080,'height':1920}]}
        self.registry=adapters(lambda:self.model,FakeWeb)|speech(lambda:self.speech)|production(
            lambda:self.visual,lambda:self.visual,preview=lambda design:b'PNG fixture',renderer=renderer,
            inspector=lambda path:self.info,library=self.root/'library')
        self.runner=Runner(self.store,self.registry)

    def artifact(self,stage):return self.store.read_artifact(stage,self.store.load().artifacts[stage])

    def terrain_source(self):
        folder=self.root/'field';folder.mkdir(exist_ok=True)
        field=Battlefield(layer=layer(),heights=HeightGrid(columns=2,rows=2,values=[0,10,20,30]),
                         features=[],sources=[{'url':'https://example.test/terrain','role':'Synthetic test field'}],notes=['Synthetic coordinates only.'])
        (folder/'scene.json').write_text(json.dumps({'battlefield':field.model_dump(mode='json')}),encoding='utf-8')
        (folder/field.layer.relief).write_bytes(b'Synthetic source pixels')
        blueprint=self.artifact('direction').output.data['blueprint']
        return {'mode':'battlefield','source_bundle':str(folder),'spatial_binding':{
            'coordinate_frame':'battlefield_uv','blueprint_sha256':fingerprint(blueprint),'battlefield_sha256':fingerprint(field),
            'reviewed':True,'sources':['https://example.test/spatial-binding'],'note':'Synthetic fixture binding; no historical positions are asserted.'}}

    def test_graph_builds_reviewed_bundle_and_silent_picture_before_audio_production(self):
        result=self.runner.run()
        self.assertEqual(result.blocked_stage,'effects');self.assertEqual(result.status,'needs_input')
        for stage in ('terrain','assets','visual_review','picture'):self.assertIn(stage,result.artifacts)
        review=self.artifact('visual_review');self.assertEqual(review.output.review,'pass')
        self.assertEqual(review.output.data['sampled_scenes'],4)
        self.assertEqual(len([r for r in self.renders if r[1].suffix=='.png']),4)
        self.assertEqual(len([r for r in self.renders if r[1].suffix=='.mp4']),1)
        self.assertFalse(self.artifact('picture').output.data['publishing_ready'])
        scene=json.loads((Path(review.output.data['bundle'])/'scene.json').read_text(encoding='utf-8'))
        self.assertNotIn('soundtrack',scene);self.assertEqual(scene['duration'],97)
        self.assertEqual(scene['captions'][0]['end'],24)
        self.assertEqual(len(scene['bindings']['unit']),2)
        self.assertTrue(all(asset['review_basis']=='rendered_image' for asset in self.artifact('assets').output.data['assets'].values()))

    def test_restart_reuses_visuals_and_picture_without_calls(self):
        self.runner.run();calls=len(self.visual.calls);renders=len(self.renders)
        result=self.runner.run()
        self.assertEqual(len(self.visual.calls),calls);self.assertEqual(len(self.renders),renders)
        self.assertNotIn('final_review',result.artifacts)

    def test_unit_edit_creates_a_new_supported_design_and_retains_terrain_and_voice(self):
        parent=self.runner.run();previous=Manifest.model_validate(self.artifact('assets').output.data['manifest'])
        edited=previous.model_copy(deep=True)
        edited.bindings[0].brief=Brief(category='unit',concept='cavalry',description='A readable top-down horse silhouette for the cited cavalry.')
        self.visual.responses[Manifest]=[edited]
        self.store.edit(Edit(parent_revision=parent.id,kind='unit_design',object_ids=['west'],notes='Use the supported cavalry silhouette.'))
        result=self.runner.run()
        self.assertEqual(result.artifacts['terrain'],parent.artifacts['terrain'])
        self.assertEqual(result.artifacts['narration'],parent.artifacts['narration'])
        self.assertEqual(len(self.artifact('assets').output.data['assets']),2)
        self.assertIn('picture',result.executed);self.assertNotIn('direction',result.executed)
        self.assertTrue(any(schema is Design and 'cavalry' in prompt for schema,prompt,kwargs in self.visual.calls))

    def test_unsupported_equipment_stops_before_design_generation(self):
        self.visual.responses[ManifestReview]=[ManifestReview(issues=['Infantry evidence does not establish tanks.'])]
        result=self.runner.run()
        self.assertEqual(result.blocked_stage,'terrain');self.assertIn('terrain',result.drafts)
        self.assertFalse(any(schema is Design for schema,prompt,kwargs in self.visual.calls))

    def test_targeted_manifest_cannot_change_other_unit(self):
        parent=self.runner.run();edited=Manifest.model_validate(self.artifact('assets').output.data['manifest'])
        edited.bindings[0].brief.description+=' Clear head shape.'
        edited.bindings[1].brief.description+=' Unrequested alteration.'
        self.visual.responses[Manifest]=[edited]
        self.store.edit(Edit(parent_revision=parent.id,kind='unit_design',object_ids=['west'],notes='Clarify this unit.'))
        result=self.runner.run();self.assertEqual(result.blocked_stage,'assets')
        self.assertTrue(any('unrelated' in issue for issue in result.issues))
        # A retry must compare preserved units with the last passing artifact,
        # never adopt the unrelated change from a failed draft as its new baseline.
        edited.bindings[1].brief.description=Manifest.model_validate(self.store.read_artifact('assets',parent.artifacts['assets']).output.data['manifest']).bindings[1].brief.description
        self.visual.responses[Manifest]=[edited]
        result=self.runner.run();self.assertIn('picture',result.artifacts)
        current=Manifest.model_validate(self.artifact('assets').output.data['manifest'])
        self.assertNotIn('Unrequested',current.bindings[1].brief.description)

    def test_approved_design_note_is_not_reapplied_during_upstream_revision(self):
        from war_director.models import ScenePlan
        parent=self.runner.run();edited=Manifest.model_validate(self.artifact('assets').output.data['manifest'])
        edited.bindings[0].brief.description+=' A more distinct readable head.'
        self.visual.responses[Manifest]=[edited]
        self.store.edit(Edit(parent_revision=parent.id,kind='unit_design',object_ids=['west'],notes='Clarify this silhouette.'))
        self.runner.run();calls=sum(schema is Manifest for schema,prompt,kwargs in self.visual.calls)
        plan=self.artifact('direction').output.data['blueprint']
        scene=ScenePlan.model_validate(plan['scenes'][0]);scene.focus_reason='Keep the crossing easy to understand.'
        self.model.responses[ScenePlan]=[scene]
        self.store.edit(Edit(parent_revision=self.store.load().id,kind='route',scene_ids=['s1'],notes='Clarify this view.'))
        result=self.runner.run()
        self.assertIn('picture',result.artifacts)
        self.assertEqual(sum(schema is Manifest for schema,prompt,kwargs in self.visual.calls),calls)

    def test_unknown_object_and_scene_scope_fail_before_visual_request(self):
        parent=self.runner.run();calls=len(self.visual.calls)
        self.store.edit(Edit(parent_revision=parent.id,kind='unit_design',object_ids=['missing'],notes='Edit this object.'))
        result=self.runner.run();self.assertIn('unknown',result.issues[0]);self.assertEqual(len(self.visual.calls),calls)
        self.store.edit(Edit(parent_revision=result.id,kind='unit_design',scene_ids=['s1'],notes='Change design.'))
        result=self.runner.run();self.assertIn('object IDs',result.issues[0]);self.assertEqual(len(self.visual.calls),calls)

    def test_visual_review_failure_retains_frames_and_blocks_picture(self):
        self.visual.responses[FrameReview]=[FrameReview(phone_readable=False,terrain_clear=True,units_distinct=True,captions_clear=False)]
        result=self.runner.run()
        self.assertEqual(result.blocked_stage,'visual_review');self.assertNotIn('picture',result.artifacts)
        draft=self.store.read_artifact('visual_review',result.drafts['visual_review'])
        self.assertIn('frame-0.png',draft.output.files)

    def test_changed_reviewed_scene_is_rejected_on_read(self):
        self.runner.run();review=self.artifact('visual_review')
        (Path(review.output.data['bundle'])/'scene.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(WorkflowError):self.store.read_artifact('visual_review',review.id)

    def test_export_rejects_wrong_duration_size_and_audio_stream(self):
        for metadata in ({'format':{'duration':'5'},'streams':[{'codec_type':'video','width':1080,'height':1920}]},
                         {'format':{'duration':'97'},'streams':[{'codec_type':'video','width':1920,'height':1080}]},
                         {'format':{'duration':'97'},'streams':[{'codec_type':'video','width':1080,'height':1920},{'codec_type':'audio'}]}):
            self.info=metadata;result=self.runner.run()
            self.assertEqual(result.blocked_stage,'picture');self.assertNotIn('picture',result.artifacts)

    def test_missing_map_mode_stops_without_spending_visual_budget(self):
        revision=self.store.load();revision.params['terrain']={};self.store.save(revision)
        result=self.runner.run();self.assertEqual(result.blocked_stage,'terrain')
        self.assertIn('Choose terrain mode',result.issues[0]);self.assertEqual(self.visual.calls,[])

    def test_visual_budget_resume_keeps_completed_terrain_stage(self):
        revision=self.store.load();self.store.set_limit(revision.id,'model_attempts',12)
        result=self.runner.run();self.assertEqual(result.status,'quota_wait')
        self.assertEqual(result.blocked_stage,'assets');terrain=result.artifacts['terrain']
        terrain_requests=len(self.visual.calls)
        self.store.set_limit(result.id,'model_attempts',32)
        result=self.runner.run();self.assertIn('picture',result.artifacts)
        self.assertEqual(result.artifacts['terrain'],terrain)
        self.assertFalse(any(schema is Manifest and prompt.startswith('Plan only terrain') for schema,prompt,kwargs in self.visual.calls[terrain_requests:]))

    def test_local_visual_limit_stops_before_second_request(self):
        revision=self.store.load();revision.params['terrain']['max_model_calls']=1;self.store.save(revision)
        result=self.runner.run();self.assertEqual(result.blocked_stage,'terrain')
        self.assertIn('Visual model limit',result.issues[0]);self.assertEqual(len(self.visual.calls),1)

    def test_measured_battlefield_requires_current_binding_and_copies_terrain(self):
        parent=self.runner.run();settings=self.terrain_source()
        self.store.edit(Edit(parent_revision=parent.id,kind='terrain',patch=settings))
        result=self.runner.run();self.assertIn('picture',result.executed)
        terrain=self.artifact('terrain');review=self.artifact('visual_review')
        scene=json.loads((Path(review.output.data['bundle'])/'scene.json').read_text(encoding='utf-8'))
        self.assertEqual(scene['purpose'],'battlefield_replay')
        self.assertEqual(scene['battlefield']['heights']['values'],[0,10,20,30])
        self.assertEqual(scene['spatial_binding']['coordinate_frame'],'battlefield_uv')
        source=Path(settings['source_bundle'])/'relief-overview.png';source.write_bytes(b'changed external pixels')
        self.assertNotEqual(Path(terrain.output.files['relief']).read_bytes(),source.read_bytes())
        self.store.read_artifact('terrain',terrain.id)

    def test_stale_binding_and_missing_source_fail_without_new_design_calls(self):
        parent=self.runner.run();calls=len(self.visual.calls);settings=self.terrain_source()
        settings['spatial_binding']['blueprint_sha256']='outdated'
        self.store.edit(Edit(parent_revision=parent.id,kind='terrain',patch=settings))
        result=self.runner.run();self.assertIn('stale',result.issues[0]);self.assertEqual(len(self.visual.calls),calls)
        self.store.edit(Edit(parent_revision=result.id,kind='terrain',patch={'spatial_binding':None}))
        result=self.runner.run();self.assertIn('spatial_binding',result.issues[0])

    def test_format_edit_reuses_units_terrain_and_narration(self):
        parent=self.runner.run()
        self.store.edit(Edit(parent_revision=parent.id,kind='format',patch={'aspect':'landscape'}))
        self.info['streams'][0]|={'width':1920,'height':1080}
        result=self.runner.run()
        for stage in ('assets','terrain','narration'):self.assertEqual(result.artifacts[stage],parent.artifacts[stage])
        self.assertEqual(self.artifact('picture').output.data['aspect'],'landscape')

    def test_camera_notes_are_not_silently_ignored(self):
        parent=self.runner.run()
        self.store.edit(Edit(parent_revision=parent.id,kind='camera',notes='Zoom much closer.'))
        result=self.runner.run();self.assertEqual(result.blocked_stage,'visual_review')
        self.assertIn('director',result.issues[0])

    def test_subset_manifest_validation_rejects_cross_category_objects(self):
        d,s,p=ready();full=manifest(d,p)
        units=Manifest(bindings=[b for b in full.bindings if b.brief.category=='unit'])
        self.assertEqual(check_manifest(units,d,p,'unit'),[])
        self.assertTrue(check_manifest(full,d,p,'unit'))


class ExportTests(unittest.TestCase):
    def test_subprocess_arguments_timeouts_and_encoder_failures_are_bounded(self):
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'frame.png';target.write_bytes(b'fixture')
            with patch('war_workflow.production.subprocess.run',return_value=type('Result',(),{'returncode':0})()) as call:
                render(tmp,target,4,24,'portrait')
                args=call.call_args.args[0];self.assertEqual(args[-3:],['4','24','portrait'])
                self.assertEqual(call.call_args.kwargs['timeout'],180)
            for error in (OSError('missing'),subprocess.TimeoutExpired('node',1)):
                with patch('war_workflow.production.subprocess.run',side_effect=error),self.assertRaises(WorkflowError):render(tmp,target,1)
            with patch('war_workflow.production.subprocess.run',return_value=type('Result',(),{'returncode':1})()),self.assertRaises(WorkflowError):render(tmp,target,1)


if __name__=='__main__':unittest.main()
