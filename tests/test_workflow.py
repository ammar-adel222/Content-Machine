import contextlib
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from war_workflow.models import Edit, Limits, Output
from war_workflow.planner import ORDER, ROOTS, affected, fingerprint
from war_workflow.store import ProjectStore, WorkflowError, Conflict, BudgetExhausted


def make_store(root,**kwargs):return ProjectStore.create(root/'project','Synthetic workflow test',**kwargs)


class PlannerTests(unittest.TestCase):
    def test_music_edit_has_no_picture_or_authoring_work(self):
        self.assertEqual(set(affected(ROOTS['music_mix'])),{'mix','audio_review','mux','final_review'})
        changed=affected(ROOTS['unit_design'])
        self.assertIn('picture',changed);self.assertNotIn('effects',changed);self.assertNotIn('narration',changed)
        changed=affected(ROOTS['route']);self.assertIn('effects',changed);self.assertNotIn('narration',changed)
        self.assertEqual(affected(['research']),ORDER)

    def test_exact_and_semantic_hashes_are_stable(self):
        self.assertEqual(fingerprint({'a':1,'b':2}),fingerprint({'b':2,'a':1}))
        with self.assertRaises(ValueError):fingerprint({'bad':float('nan')})
        with self.assertRaises(ValueError):affected(['unknown'])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=make_store(self.root)

    def test_persistence_versions_and_optimistic_edit_conflicts(self):
        parent=self.store.load();original=parent.model_dump_json()
        edit=Edit(parent_revision=parent.id,kind='music_mix',patch={'music_gain_db':-28})
        new=self.store.edit(edit)
        self.assertIsNone(new.approval);self.assertEqual(new.parent,parent.id)
        self.assertEqual(self.store.load(parent.id).model_dump_json(),original)
        self.assertEqual(ProjectStore(self.store.root).load().id,new.id)
        self.assertEqual(self.store.edit(edit).id,new.id)
        with self.assertRaises(Conflict):self.store.edit(edit.model_copy(update={'patch':{'music_gain_db':-30}}))
        with self.assertRaises(Conflict):self.store.edit(Edit(parent_revision=parent.id,kind='script',notes='Stale revision edit'))

    def test_atomic_budget_reservations_do_not_overspend(self):
        revision=self.store.load();self.store.set_limit(revision.id,'model_attempts',3)
        def consume(_):
            try:self.store.consume(revision.id,'model_attempts');return True
            except BudgetExhausted:return False
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(consume,range(20))),3)
        self.assertEqual(self.store.budgets(revision.id)['model_attempts']['used'],3)
        with self.assertRaises(ValueError):self.store.set_limit(revision.id,'model_attempts',2)
        with self.assertRaises(ValueError):self.store.consume(revision.id,'invalid')

    def test_artifact_receipts_preserve_versions_and_detect_media_changes(self):
        file=self.root/'asset.wav';file.write_bytes(b'first waveform')
        key=fingerprint('input')
        first=self.store.write_artifact('narration',key,Output(data={'binding':'old'},views={'timing':2},files={'wave':str(file)}))
        second=self.store.write_artifact('narration',key,Output(data={'binding':'new'},views={'timing':2},files={'wave':str(file)}))
        self.assertNotEqual(first.id,second.id);self.assertEqual(first.view_hashes,second.view_hashes)
        self.assertEqual(self.store.read_artifact('narration',first.id).output.data['binding'],'old')
        self.assertEqual(self.store.cached('narration',key).id,second.id)
        file.write_bytes(b'changed waveform')
        with self.assertRaises(WorkflowError):self.store.cached('narration',key)
        with self.assertRaises(ValueError):self.store.receipt_path('../escape',key)

    def test_run_lock_conflicts_and_releases(self):
        with self.store.run_lock():
            with self.assertRaises(Conflict):
                with ProjectStore(self.store.root).run_lock():pass
        with self.store.run_lock():pass

    def test_cli_planning_invalid_edits_and_missing_project(self):
        from war_workflow.__main__ import main
        parent=self.store.load().id
        patch=self.root/'settings.json';patch.write_text('{"music_gain_db":-28}',encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['status',str(self.store.root)]),0)
            self.assertEqual(main(['edit',str(self.store.root),'--parent',parent,'--kind','music_mix','--settings',str(patch)]),0)
            self.assertEqual(main(['plan',str(self.root/'missing')]),1)
            self.assertEqual(main(['approve',str(self.store.root)]),1)


@unittest.skipUnless(importlib.util.find_spec('langgraph'),'Install optional workflow dependencies for real graph tests')
class GraphTests(unittest.TestCase):
    def setUp(self):
        from war_workflow.graph import Adapter,Runner
        self.Adapter=Adapter;self.Runner=Runner
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=make_store(self.root);self.calls=[]
        def run(ctx):
            self.calls.append(ctx.stage)
            files={}
            if ctx.stage=='mux':
                file=ctx.output_dir/'final.mp4';file.write_text('synthetic media '+fingerprint({s:a.content_hash for s,a in ctx.inputs.items()}),encoding='utf-8');files={'video':str(file)}
            return Output(data={'stage':ctx.stage,'settings':ctx.params,'parents':{s:a.content_hash for s,a in ctx.inputs.items()}},files=files,
                          review='pass' if ctx.stage.endswith('review') else None)
        self.adapters={stage:Adapter(run,'fake-v1') for stage in ORDER}

    def run_all(self):return self.Runner(self.store,self.adapters).run()

    def test_actual_langgraph_persists_and_music_edit_reuses_picture(self):
        initial=self.run_all();self.assertEqual(initial.status,'awaiting_review');self.assertEqual(set(self.calls),set(ORDER))
        self.assertTrue((self.store.root/'checkpoints.sqlite').exists())
        self.store.approve(initial.id)
        picture=initial.artifacts['picture'];self.calls.clear()
        edited=self.store.edit(Edit(parent_revision=initial.id,kind='music_mix',patch={'music_gain_db':-28}))
        result=self.Runner(ProjectStore(self.store.root),self.adapters).run(edited.id)
        self.assertEqual(set(self.calls),{'mix','audio_review','mux','final_review'})
        self.assertEqual(result.artifacts['picture'],picture);self.assertIsNone(result.approval)
        self.assertEqual(self.store.load(initial.id).status,'approved')
        with self.assertRaises(Conflict):self.store.approve(initial.id)

    def test_reopen_after_failure_runs_only_incomplete_stages(self):
        def fail(ctx):raise RuntimeError('Private transport payload must not be checkpointed')
        self.adapters['direction']=self.Adapter(fail,'fake-v1')
        failed=self.run_all();self.assertEqual(failed.status,'needs_input');self.assertEqual(failed.blocked_stage,'direction')
        self.assertNotIn('Private transport',str(failed.issues));done=set(self.calls);self.calls.clear()
        original=self.adapters['terrain'].run;self.adapters['direction']=self.Adapter(original,'fake-v1')
        result=self.Runner(ProjectStore(self.store.root),self.adapters).run()
        self.assertEqual(result.status,'awaiting_review');self.assertFalse(done&set(self.calls))

    def test_quota_wait_does_not_reset_budget_on_resume(self):
        self.store.set_limit(self.store.load().id,'model_attempts',0)
        original=self.adapters['research'].run
        def consume(ctx):ctx.consume();return original(ctx)
        self.adapters['research']=self.Adapter(consume,'fake-v1')
        failed=self.run_all();self.assertEqual(failed.status,'quota_wait')
        self.assertEqual(self.store.budgets(failed.id)['model_attempts']['used'],0)
        self.store.set_limit(failed.id,'model_attempts',1)
        result=self.run_all();self.assertEqual(result.status,'awaiting_review')
        self.assertEqual(self.store.budgets(failed.id)['model_attempts']['used'],1)

    def test_missing_adapter_and_failed_review_stop_without_fake_completion(self):
        failed=self.Runner(self.store,{}).run();self.assertEqual(failed.blocked_stage,'research')
        self.adapters['script_review']=self.Adapter(lambda ctx:Output(data={},review='revise',issues=['The narration needs clearer evidence.']),'fake-v1')
        result=self.run_all();self.assertEqual(result.blocked_stage,'script_review');self.assertNotIn('direction',self.calls)

    def test_written_receipt_recovers_after_progress_save_crash(self):
        revision=self.store.load();runner=self.Runner(self.store,self.adapters)
        ctx=runner.context(revision,'research');key=runner.cache_key(ctx,'fake-v1')
        artifact=self.store.write_artifact('research',key,Output(data={'stage':'research','settings':ctx.params}),version='fake-v1')
        result=self.run_all()
        self.assertNotIn('research',self.calls);self.assertIn('research',result.reused)
        self.assertEqual(result.artifacts['research'],artifact.id)

    def test_semantic_timing_view_reuses_music_source_when_actions_change(self):
        def timing(ctx):
            self.calls.append('timing');return Output(data={'route':ctx.inputs['direction'].content_hash},views={'duration':24,'visual':ctx.inputs['direction'].content_hash,'effects':ctx.inputs['direction'].content_hash})
        self.adapters['timing']=self.Adapter(timing,'timing-v1')
        initial=self.run_all();self.calls.clear()
        self.store.edit(Edit(parent_revision=initial.id,kind='route',patch={'route':'different'},scene_ids=['s3']))
        result=self.run_all()
        self.assertNotIn('music_source',self.calls);self.assertIn('music_source',result.reused)
        self.assertNotIn('narration',self.calls)

    def test_rebinding_preserves_cached_compute_and_records_current_provenance(self):
        # A timing-only projection can stay constant while exact artifact metadata changes.
        self.adapters['writing']=self.Adapter(lambda ctx:Output(data={'metadata':ctx.params},views={'speech':'same spoken text'}),'writer-v1')
        def narration(ctx):
            self.calls.append('narration');return Output(data={'bound_writer':ctx.inputs['writing'].id})
        def rebind(ctx,cached):return cached.output.model_copy(update={'data':{'bound_writer':ctx.inputs['writing'].id}})
        self.adapters['narration']=self.Adapter(narration,'tts-v1',rebind)
        initial=self.run_all();self.calls.clear()
        self.store.edit(Edit(parent_revision=initial.id,kind='script',patch={'metadata':'new'}))
        result=self.run_all()
        self.assertNotIn('narration',self.calls);self.assertIn('narration',result.reused)
        artifact=self.store.read_artifact('narration',result.artifacts['narration'])
        self.assertEqual(artifact.output.data['bound_writer'],result.artifacts['writing'])

    def test_native_approval_interrupt_survives_process_reopen(self):
        result=self.run_all()
        reopened=self.Runner(ProjectStore(self.store.root),{})
        approved=reopened.approve(result.id)
        self.assertEqual(approved.status,'approved')
        self.assertEqual(reopened.approve(result.id).approval,approved.approval)
        self.assertEqual(approved.approval['video_sha256'],self.store.read_artifact('mux',approved.artifacts['mux']).file_hashes['video'])

    def test_failed_review_retains_draft_and_cannot_be_approved(self):
        self.adapters['script_review']=self.Adapter(lambda ctx:Output(data={'draft':'Keep for inspection'},review='revise',issues=['Needs source correction.']),'critic-v1')
        result=self.run_all();self.assertIn('script_review',result.drafts)
        draft=self.store.read_artifact('script_review',result.drafts['script_review'])
        self.assertEqual(draft.output.data['draft'],'Keep for inspection')
        self.assertIsNone(self.store.cached('script_review',draft.key))
        with self.assertRaises(WorkflowError):self.Runner(self.store,{}).approve(result.id)

    def test_final_approval_rejects_a_stale_review(self):
        result=self.run_all();file=self.root/'other.mp4';file.write_bytes(b'a different video')
        changed=self.store.write_artifact('mux',fingerprint('other-media'),Output(data={'changed':True},files={'video':str(file)}))
        result.artifacts['mux']=changed.id;self.store.save(result)
        with self.assertRaises(WorkflowError):self.store.approve(result.id)

    def test_new_edit_stops_old_run_after_current_stage_and_reuses_its_receipt(self):
        original=self.adapters['writing'].run;edited=[]
        def edit_while_running(ctx):
            if not edited:edited.append(self.store.edit(Edit(parent_revision=ctx.revision.id,kind='music_mix',patch={'music_gain_db':-28})))
            return original(ctx)
        self.adapters['writing']=self.Adapter(edit_while_running,'fake-v1')
        old=self.run_all();self.assertEqual(old.status,'superseded')
        self.assertEqual(self.calls,['research','writing']);self.calls.clear()
        current=self.run_all();self.assertEqual(current.id,edited[0].id)
        self.assertEqual(current.status,'awaiting_review');self.assertNotIn('writing',self.calls)


@unittest.skipUnless(importlib.util.find_spec('langgraph'),'Requires optional workflow dependencies')
class MediaAdapterTests(unittest.TestCase):
    def setUp(self):
        from array import array
        from war_content.music_models import MusicConfig
        from war_content.sound_render import write_wave
        from .test_sound import scene
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.bundle=self.root/'bundle';self.bundle.mkdir()
        data=scene();data['soundtrack']={'file':'soundtrack.wav','has_narration':False,'has_music':True}
        (self.bundle/'scene.json').write_text(json.dumps(data),encoding='utf-8')
        (self.bundle/'content.json').write_text('{"status":"ready"}',encoding='utf-8')
        (self.bundle/'pixi.min.js').write_text('// fixture',encoding='utf-8')
        (self.bundle/'music-config.json').write_text(MusicConfig().model_dump_json(),encoding='utf-8')
        (self.bundle/'music-metrics.json').write_text('{}',encoding='utf-8')
        for name in ('soundtrack.wav','sound-effects.wav','music-source.wav'):write_wave(self.bundle/name,array('f',[.05,-.05])*192000)
        self.video=self.root/'picture.mp4';self.video.write_bytes(b'approved picture bytes')
        self.probe={'format':{'duration':'4'},'streams':[{'codec_type':'video','width':1080,'height':1920},{'codec_type':'audio'}]}

    def test_audio_edit_adapters_use_real_stems_and_never_upstream_agents(self):
        from war_workflow import media
        from war_workflow.graph import Adapter,Runner
        with patch('war_workflow.media.probe',return_value=self.probe):
            store=media.import_media(self.root/'project',self.bundle,self.video,picture_approved=True)
        def fake_mux(ctx):
            target=ctx.output_dir/'final.mp4';target.write_bytes(b'new container');return Output(data={'duration':4},files={'video':str(target)})
        registry=media.adapters();registry['mux']=Adapter(fake_mux,'fake-mux')
        store.edit(Edit(parent_revision=store.load().id,kind='music_mix',patch={'music_gain_db':-28}))
        with patch('war_content.music.compile_bundle',return_value=self.bundle) as mix,patch('war_workflow.media.probe',return_value=self.probe):
            result=Runner(store,registry).run()
        self.assertEqual(result.status,'awaiting_review');self.assertEqual(mix.call_count,1)
        self.assertEqual(set(result.executed),{'mix','audio_review','mux','final_review'})
        self.assertTrue(all(v['used']==0 for v in store.budgets(result.id).values()))
        self.assertNotIn('research',result.artifacts)

    def test_unapproved_picture_cannot_reach_final_review(self):
        from war_workflow import media
        from war_workflow.graph import Runner
        with patch('war_workflow.media.probe',return_value=self.probe):store=media.import_media(self.root/'project',self.bundle,self.video)
        result=Runner(store,media.adapters()).run()
        self.assertEqual(result.status,'needs_input');self.assertEqual(result.blocked_stage,'mux')
        self.assertNotIn('final_review',result.artifacts)

    def test_import_rejects_missing_stems_and_wrong_duration(self):
        from war_workflow import media
        with patch('war_workflow.media.probe',return_value={'format':{'duration':'5'},'streams':[]}):
            with self.assertRaises(WorkflowError):media.import_media(self.root/'project',self.bundle,self.video)
        (self.bundle/'music-source.wav').unlink()
        with self.assertRaises(WorkflowError):media.import_media(self.root/'missing',self.bundle,self.video)

    def test_final_container_checks_reject_missing_audio_and_wrong_length(self):
        from types import SimpleNamespace
        from war_workflow import media
        store=make_store(self.root)
        artifact=store.write_artifact('mux',fingerprint('final'),Output(data={'duration':4},files={'video':str(self.video)}))
        ctx=SimpleNamespace(inputs={'mux':artifact})
        for metadata in ({'format':{'duration':'4'},'streams':[{'codec_type':'video'}]},
                         {'format':{'duration':'5'},'streams':[{'codec_type':'video'},{'codec_type':'audio'}]}):
            with patch('war_workflow.media.probe',return_value=metadata):self.assertEqual(media.final_review(ctx).review,'revise')
