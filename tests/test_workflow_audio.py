from array import array
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave
from war_content.sound_models import SoundConfig
from war_content.sound_plan import compile_plan
from war_content.sound_render import read_wave, write_wave
from war_workflow import audio
from war_workflow.graph import Context
from war_workflow.models import Edit, Output
from war_workflow.planner import fingerprint
from war_workflow.store import ProjectStore, WorkflowError
from .test_sound import scene


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=ProjectStore.create(self.root/'project','Synthetic audio integration',target_seconds=1)
        self.revision=self.store.load();self.registry=audio.adapters()
        self.scene=scene();self.scene['duration']=1
        for action in self.scene['timeline']:
            action['start_sec']/=4;action['end_sec']/=4
        self.seed('timing',{'duration':1,'plan':{'blueprint':self.scene['blueprint']},'actions':self.scene['timeline']})
        self.seed('direction',{'blueprint':self.scene['blueprint']})
        voice=self.root/'voice.wav';write_wave(voice,array('f',[.2,-.2])*48000)
        self.seed('narration',{'present':True,'narration':{'basis':'synthetic fixture'}},files={'wave':str(voice)})
        # A short synthetic bed keeps unit tests fast; production uses the approved bed.
        self.bed=patch('war_content.music.ambient_bed',return_value=array('f',[.1,-.1])*24000)
        self.bed.start();self.addCleanup(self.bed.stop)

    def seed(self,stage,data,files=None):
        artifact=self.store.write_artifact(stage,fingerprint([stage,data]),Output(data=data,files=files or {}))
        self.revision.artifacts[stage]=artifact.id;return artifact

    def artifact(self,stage):return self.store.read_artifact(stage,self.revision.artifacts[stage])

    def context(self,stage):
        from war_workflow.planner import SPECS
        inputs={s:self.artifact(s) for s in SPECS[stage].inputs}
        previous=self.artifact(stage) if stage in self.revision.artifacts else None
        return Context(self.store,self.revision.model_copy(deep=True),stage,inputs,previous)

    def run_stage(self,stage):
        ctx=self.context(stage);result=self.registry[stage].run(ctx)
        artifact=self.store.write_artifact(stage,fingerprint([stage,result.data]),result)
        self.revision.artifacts[stage]=artifact.id;return result

    def ready_stems(self):self.run_stage('effects');self.run_stage('music_source')

    def test_effects_use_actual_moves_and_do_not_infer_firing(self):
        result=self.run_stage('effects')
        cues=json.loads(Path(result.files['plan']).read_text(encoding='utf-8'))['cues']
        self.assertEqual(len(cues),3);self.assertEqual({c['effect'] for c in cues},{'footsteps'})
        self.assertAlmostEqual(cues[-1]['start'],.35)
        with wave.open(result.files['wave'],'rb') as wav:self.assertEqual(wav.getnframes(),48000)

    def test_battlefield_production_replay_gets_movement_foley(self):
        value=self.scene|{'battlefield':{'mode':'context'},'purpose':'battlefield_replay'}
        self.assertEqual(len(compile_plan(value,SoundConfig()).cues),3)
        value['purpose']='battlefield_terrain_study'
        self.assertEqual(compile_plan(value,SoundConfig()).cues,[])

    def test_unrecognized_unit_requires_profile_or_explicit_none(self):
        self.scene['blueprint']['forces'][0]['kind']='army'
        self.seed('direction',{'blueprint':self.scene['blueprint']})
        self.seed('timing',{'duration':1,'plan':{'blueprint':self.scene['blueprint']},'actions':self.scene['timeline']})
        result=self.run_stage('effects');self.assertTrue(result.issues);self.assertNotIn('wave',result.files)
        self.revision.params['effects']={'profiles':{'a':{'movement':'none'}}}
        result=self.run_stage('effects');self.assertEqual(result.issues,[]);self.assertEqual(result.data['cue_count'],0)

    def test_engagement_spots_are_explicit_and_time_checked(self):
        self.revision.params['effects']={'spots':[{'action_id':'fire','time':.8,'effect':'cannon'}]}
        result=self.run_stage('effects');self.assertEqual(result.data['cue_count'],4)
        self.revision.params['effects']['spots'][0]['time']=.4
        with self.assertRaises(ValueError):self.run_stage('effects')

    def test_scoped_profile_edits_preserve_other_settings(self):
        self.revision.params['effects']={'profiles':{'a':{'movement':'footsteps','gain_db':-20}}}
        self.run_stage('effects')
        self.revision.params['effects']={'profiles':{'a':{'movement':'heavy_steps'}}}
        self.revision.instructions['effects']={'object_ids':['a']}
        result=self.run_stage('effects')
        self.assertEqual(result.data['sound_config']['profiles']['a']['movement'],'heavy_steps')
        self.assertEqual(result.data['sound_config']['profiles']['a']['gain_db'],-20)
        self.revision.params['effects']={'profiles':{'a':{'gain_db':-28}}}
        result=self.run_stage('effects')
        self.assertEqual(result.data['sound_config']['profiles']['a'],{'movement':'heavy_steps','gain_db':-28})
        self.revision.params['effects']['profiles']['other']={'movement':'none'}
        with self.assertRaises(WorkflowError):self.run_stage('effects')

    def test_sample_hash_changes_identity_and_snapshot_survives_source_loss(self):
        sample=self.root/'step.wav';write_wave(sample,array('f',[.1,-.1])*12000)
        self.revision.params['effects']={'samples':{'footsteps':{'path':str(sample),'attribution':'Synthetic unit-test sample'}}}
        context=self.context('effects');before=self.registry['effects'].cache_context(context)
        first=self.run_stage('effects');saved=Path(first.files['sample_footsteps']).read_bytes()
        write_wave(sample,array('f',[.2,-.2])*12000)
        self.assertNotEqual(before,self.registry['effects'].cache_context(self.context('effects')))
        sample.unlink()
        result=self.run_stage('effects');self.assertEqual(Path(result.files['sample_footsteps']).read_bytes(),saved)

    def test_invalid_replacement_audio_is_not_snapshotted(self):
        sample=self.root/'invalid.wav';sample.write_text('Not audio.',encoding='utf-8')
        self.revision.params['effects']={'samples':{'footsteps':{'path':str(sample),'attribution':'Synthetic invalid fixture'}}}
        with self.assertRaises(ValueError):self.run_stage('effects')
        self.assertFalse(list(self.context('effects').output_dir.glob('*/sample-*.wav')))

    def test_ambient_music_is_prepared_once_and_saved_byte_exactly(self):
        first=self.run_stage('music_source');self.assertFalse(first.data['reused'])
        second=self.run_stage('music_source');self.assertTrue(second.data['reused'])
        self.assertEqual(first.views,second.views)
        self.assertEqual(Path(first.files['wave']).read_bytes(),Path(second.files['wave']).read_bytes())

    def test_local_track_is_snapshotted_and_missing_new_track_fails(self):
        original=self.root/'track.wav';write_wave(original,array('f',[.2,-.2])*24000)
        self.revision.params['music_source']={'kind':'file','path':str(original),'attribution':'Synthetic music fixture'}
        first=self.run_stage('music_source');self.assertIn('original',first.files)
        original.unlink();second=self.run_stage('music_source')
        self.assertEqual(first.views,second.views)
        self.revision.params['music_source']['path']='missing.wav'
        with self.assertRaises(WorkflowError):self.run_stage('music_source')

    def test_mix_keeps_stems_and_music_quiet_under_narration(self):
        self.ready_stems();result=self.run_stage('mix')
        metrics=json.loads(Path(result.files['metrics']).read_text(encoding='utf-8'))
        self.assertGreater(metrics['voice_duck_blocks'],0)
        self.assertLess(metrics['music_rms_dbfs'],-40)
        self.assertLessEqual(metrics['final_peak_dbfs'],-.99)
        self.assertTrue({'wave','music','narration','effects','music_source'}<=set(result.files))
        from war_workflow.media import audio_review
        ctx=Context(self.store,self.revision,'audio_review',{'mix':self.artifact('mix')},None)
        self.assertEqual(audio_review(ctx).review,'pass')

    def test_disabled_music_and_level_edits_do_not_rebuild_sources(self):
        self.ready_stems();self.run_stage('mix');sources={s:self.revision.artifacts[s] for s in ('narration','effects','music_source')}
        self.revision.params['mix']={'enabled':False,'narration_gain_db':-3}
        result=self.run_stage('mix')
        self.assertTrue(all(v==0 for v in read_wave(result.files['music'])))
        self.assertEqual(sources,{s:self.revision.artifacts[s] for s in sources})

    def test_mismatched_stems_and_missing_narration_fail(self):
        self.ready_stems()
        music=self.artifact('music_source');wrong=self.root/'wrong.wav';write_wave(wrong,array('f',[.1,-.1])*24000)
        self.seed('music_source',music.output.data,{'wave':str(wrong)})
        with self.assertRaisesRegex(WorkflowError,'exactly match'):self.run_stage('mix')
        self.revision.artifacts['music_source']=music.id
        self.seed('narration',{'present':True})
        with self.assertRaisesRegex(WorkflowError,'missing'):self.run_stage('mix')

    def test_unstructured_and_invalid_edits_fail_before_rendering(self):
        for stage in ('effects','music_source'):
            self.revision.instructions[stage]={'notes':'Make it different.'}
            with self.assertRaisesRegex(WorkflowError,'structured'):self.run_stage(stage)
        self.revision.instructions={};self.revision.params['music_source']={'kind':'file'}
        with self.assertRaises(ValueError):self.run_stage('music_source')

    def test_different_direction_cannot_be_silently_attached_to_current_timing(self):
        changed=json.loads(json.dumps(self.scene['blueprint']));changed['forces'][0]['subgroups']=3
        self.seed('direction',{'blueprint':changed})
        with self.assertRaisesRegex(WorkflowError,'matching'):self.run_stage('effects')

    def test_waveform_identical_mix_rebinds_current_provenance_without_dsp(self):
        self.ready_stems();self.run_stage('mix');old=self.artifact('mix')
        source=self.artifact('music_source')
        self.seed('music_source',source.output.data|{'reused':True},source.output.files)
        rebound=self.registry['mix'].rebind(self.context('mix'),old)
        self.assertEqual(rebound.files['wave'],old.output.files['wave'])
        self.assertEqual(rebound.data['inputs']['music_source'],self.revision.artifacts['music_source'])


@unittest.skipUnless(importlib.util.find_spec('langgraph'),'Install workflow extra')
class EndToEndAudioTests(unittest.TestCase):
    def test_encoder_timeout_stops_with_a_resumable_redacted_issue(self):
        import subprocess
        from war_workflow.graph import Adapter, Runner
        with TemporaryDirectory() as tmp:
            store=ProjectStore.create(Path(tmp)/'project','Synthetic timeout test')
            def timeout(ctx):raise subprocess.TimeoutExpired('encoder-secret-argument',1)
            result=Runner(store,{'research':Adapter(timeout,'timeout-fixture')}).run()
            self.assertEqual(result.status,'needs_input');self.assertEqual(result.blocked_stage,'research')
            self.assertIn('TimeoutExpired',result.issues[0]);self.assertNotIn('secret-argument',result.issues[0])

    def test_all_seventeen_stages_reach_review_and_remix_retains_picture_and_speech(self):
        from .test_workflow_production import ProductionTests
        from war_workflow import media
        from war_workflow.graph import Adapter, Runner
        case=ProductionTests();case.setUp()
        try:
            registry=case.registry|media.adapters()|audio.adapters()
            def mux(ctx):
                target=ctx.output_dir/'final.mp4';target.write_bytes(b'Synthetic container '+Path(ctx.inputs['mix'].output.files['wave']).read_bytes()[:4096])
                return Output(data={'duration':97,'publishing_ready':False},files={'video':str(target)})
            registry['mux']=Adapter(mux,'synthetic-mux')
            def final(ctx):return Output(data={'basis':'Injected container check for synthetic fixture.'},review='pass')
            registry['final_review']=Adapter(final,'synthetic-container-review')
            runner=Runner(case.store,registry)
            # Use a lower supported sample rate for this long fixture; production is 48kHz.
            with patch('war_workflow.audio.RATE',8000),patch('war_content.music.ambient_bed',return_value=array('f',[.1,-.1])*24000):
                parent=runner.run()
                self.assertEqual(parent.status,'awaiting_review');self.assertEqual(parent.dirty,[])
                self.assertEqual(len(parent.artifacts),17);self.assertIsNone(parent.approval)
                visual_calls=len(case.visual.calls);tts=len(case.speech.calls)
                revision=case.store.edit(Edit(parent_revision=parent.id,kind='music_mix',patch={'music_gain_db':-30}))
                edited=runner.run();self.assertEqual(edited.status,'awaiting_review')
                self.assertEqual(set(edited.executed),{'mix','audio_review','mux','final_review'})
                for stage in ('picture','narration','effects','music_source'):self.assertEqual(edited.artifacts[stage],parent.artifacts[stage])
                self.assertEqual(len(case.visual.calls),visual_calls);self.assertEqual(len(case.speech.calls),tts)
                self.assertTrue(all(b['used']==0 for b in case.store.budgets(revision.id).values()))
                approved=runner.approve(edited.id);self.assertEqual(approved.status,'approved')
                self.assertEqual(approved.approval['revision'],edited.id)
                track=case.root/'replacement.wav';write_wave(track,array('f',[.2,.1])*24000)
                replacement=case.store.edit(Edit(parent_revision=edited.id,kind='music_track',patch={
                    'kind':'file','path':str(track),'title':'Synthetic replacement track'}))
                self.assertIsNone(replacement.approval)
                replaced=runner.run();self.assertEqual(replaced.status,'awaiting_review')
                self.assertIn('music_source',replaced.executed)
                self.assertEqual(replaced.artifacts['picture'],edited.artifacts['picture'])
                self.assertEqual(replaced.artifacts['narration'],edited.artifacts['narration'])
                mixed=case.store.read_artifact('mix',replaced.artifacts['mix'])
                self.assertEqual(mixed.output.data['inputs']['music_source'],replaced.artifacts['music_source'])
                self.assertEqual(len(case.visual.calls),visual_calls);self.assertEqual(len(case.speech.calls),tts)
        finally:case.doCleanups()


if __name__=='__main__':unittest.main()
