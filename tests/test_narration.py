import base64
from copy import deepcopy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import URLError
import wave
from pydantic import ValidationError
from war_narration.agent import generate, verify, alignment, audio_timing, prepare, atomic, trim_edges, inspect
from war_narration.models import NarrationRequest
from war_narration.provider import GeminiSpeech, SpeechQuotaError
from war_narration.timing import align_plan, srt
from war_research.providers import ProviderError, request_json
from war_writer.agent import fingerprint
from war_director.agent import DirectorAgent, phrase_times
from .director_helpers import inputs, DirectorModel


def wav(seconds=1,rate=24000,channels=1,width=2,silent=False):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as out:
        out.setnchannels(channels);out.setsampwidth(width);out.setframerate(rate)
        out.writeframes((b'\0'*width if silent else b'\x01'*width)*channels*round(seconds*rate))
    return buffer.getvalue()


class Speech:
    def __init__(self,seconds=1):self.calls=[];self.seconds=seconds;self.error=None
    def synthesize(self,text,direction,model,voice):
        self.calls.append((text,direction,model,voice))
        if self.error:raise self.error
        return wav(self.seconds)


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.dossier,self.script=inputs()
        # Make each phrase's direction distinct so cache tests exercise partial reuse.
        for i,scene in enumerate(self.script.draft.scenes):scene.tone=f'Thoughtful {i}'
        self.provider=Speech();self.output=self.root/'output';self.cache=self.root/'cache'

    def generate(self,script=None,request=None,consume=lambda:None):
        return generate(script or self.script,self.output,self.cache,lambda:self.provider,request,consume)

    def test_atomic_write_does_not_push_a_valid_target_past_windows_path_limit(self):
        folder=self.root/('p'*max(1,170-len(str(self.root))))
        target=folder/('narration-'+'a'*64+'.wav')
        original=Path.write_bytes
        def windows_limit(path,data):
            if len(str(path))>=260:raise FileNotFoundError('Simulated Windows MAX_PATH')
            return original(path,data)
        with patch.object(Path,'write_bytes',windows_limit):atomic(target,b'valid output')
        self.assertEqual(target.read_bytes(),b'valid output')
        self.assertEqual(list(folder.iterdir()),[target])

    def test_edge_trim_removes_provider_padding_and_changes_the_cache_identity(self):
        buffer=io.BytesIO()
        with wave.open(buffer,'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(24000)
            audio.writeframes(b'\0'*14400+b'\x00\x10'*4800+b'\0'*19200)
        trimmed=trim_edges(buffer.getvalue());frames,_=inspect(trimmed)
        self.assertTrue(.29*24000<=frames<=.33*24000)
        self.assertNotEqual(prepare(self.script,NarrationRequest())[0][2],prepare(self.script,NarrationRequest(trim_silence=True))[0][2])
        self.provider.synthesize=lambda *args:buffer.getvalue()
        result=self.generate(request=NarrationRequest(trim_silence=True));verify(result,self.script)
        self.assertTrue(all(c.frames==frames for c in result.clips))
        self.assertEqual(self.generate(request=NarrationRequest(trim_silence=True)).requests,0)

    def test_pcm_assembly_uses_measured_samples_and_adds_pauses_once(self):
        narration=self.generate();verify(narration,self.script)
        self.assertEqual(narration.requests,4);self.assertEqual(narration.frames,4*30000)
        with wave.open(narration.wave,'rb') as audio:
            self.assertEqual(audio.getnframes(),120000);pcm=audio.readframes(120000)
        self.assertEqual(pcm[48000:60000],b'\0'*12000)
        self.assertEqual(alignment(narration)[1]['start_sec'],1.25)
        self.assertEqual(audio_timing(narration).durations,dict.fromkeys(['s1.p1','s2.p1','s3.p1','s4.p1'],1))

    def test_exact_cache_reuse_requires_no_provider_or_reservation(self):
        first=self.generate()
        def forbidden():raise AssertionError('No provider or reservation needed.')
        second=generate(self.script,self.output,self.cache,forbidden,consume=forbidden)
        self.assertEqual(second.sha256,first.sha256);self.assertEqual(second.requests,0);self.assertEqual(second.reused,4)

    def test_text_delivery_and_voice_edits_invalidate_only_relevant_clips(self):
        self.generate();changed=self.script.model_copy(deep=True)
        changed.draft.scenes[1].phrases[0].text+=' The crossing mattered.'
        self.assertEqual(self.generate(changed).requests,1)
        self.assertEqual(self.generate(changed,NarrationRequest(phrase_notes={'s1.p1':'Sound curious.'})).requests,1)
        self.assertEqual(self.generate(changed,NarrationRequest(voice='Kore')).requests,4)

    def test_pause_only_edit_reassembles_without_synthesis(self):
        before=self.generate();changed=self.script.model_copy(deep=True)
        changed.draft.scenes[0].phrases[0].pause_after_ms=900
        after=self.generate(changed)
        self.assertEqual(after.requests,0);self.assertEqual(after.frames-before.frames,15600)
        self.assertNotEqual(after.sha256,before.sha256);verify(after,changed)

    def test_failed_call_and_quota_stop_preserve_completed_clips(self):
        from war_workflow.store import BudgetExhausted
        count=0
        def consume():
            nonlocal count
            if count==2:raise BudgetExhausted('test quota')
            count+=1
        with self.assertRaises(BudgetExhausted):self.generate(consume=consume)
        resumed=self.generate();self.assertEqual(resumed.requests,2);self.assertEqual(resumed.reused,2)
        self.assertEqual(len(self.provider.calls),4)

    def test_local_request_limit_resumes_from_receipts(self):
        with self.assertRaisesRegex(ValueError,'request limit'):self.generate(request=NarrationRequest(max_requests=1))
        resumed=self.generate();self.assertEqual(resumed.reused,1);self.assertEqual(resumed.requests,3)

    def test_modified_cached_clip_fails_closed(self):
        narration=self.generate();path=Path(narration.clips[0].file);path.write_bytes(wav(2))
        with self.assertRaisesRegex(ValueError,'integrity'):self.generate()

    def test_invalid_silent_truncated_and_wrong_format_audio_is_not_cached(self):
        for data in (b'not audio',wav(silent=True),wav(rate=48000),wav(channels=2),wav()[:-20]):
            with self.subTest(size=len(data)),patch.object(self.provider,'synthesize',return_value=data):
                with self.assertRaises(ValueError):self.generate()
        self.assertEqual(list(self.cache.glob('*.json')),[])

    def test_invalid_request_or_unready_script_never_sends_audio_request(self):
        for values in ({'voice':'bad/path'},{'model':'non-tts'},{'phrase_notes':{'s1.p1':'x'*3001}},{'max_requests':0}):
            with self.assertRaises(ValidationError):NarrationRequest(**values)
        with self.assertRaisesRegex(ValueError,'unknown phrase'):self.generate(request=NarrationRequest(phrase_notes={'missing':'quiet'}))
        bad=self.script.model_copy(update={'status':'needs_revision'})
        with self.assertRaisesRegex(ValueError,'ready'):self.generate(bad)
        self.assertEqual(self.provider.calls,[])

    def test_timing_rejects_wrong_script_and_tampered_clock(self):
        narration=self.generate();changed=self.script.model_copy(deep=True);changed.draft.title+='!'
        with self.assertRaisesRegex(ValueError,'different script'):verify(narration,changed)
        narration.clips[1].start_frame+=1
        with self.assertRaisesRegex(ValueError,'clock'):verify(narration,self.script)

    def test_actions_and_captions_follow_measured_speech_not_word_estimates(self):
        self.provider.seconds=24
        narration=self.generate();plan=DirectorAgent(DirectorModel()).direct(self.dossier,self.script)
        timed,clock=align_plan(self.dossier,self.script,plan,narration)
        self.assertEqual(timed.status,'ready');self.assertEqual(timed.timing_basis,'measured')
        self.assertEqual(timed.duration_seconds,97);self.assertEqual(clock['duration'],97)
        self.assertEqual(phrase_times(self.script,audio_timing(narration))['s2.p1'],(24.25,48.5))
        action=next(a for a in timed.timeline if a['action_id']=='a2')
        self.assertEqual(action['start_sec'],24.25);self.assertEqual(action['end_sec'],48.5)
        subtitles=srt(clock['phrases']);self.assertIn('00:00:24,250 --> 00:00:48,250',subtitles)
        self.assertEqual(timed.blueprint,plan.blueprint)

    def test_duration_outside_allowed_range_fails_plan_without_stretching_audio(self):
        narration=self.generate();plan=DirectorAgent(DirectorModel()).direct(self.dossier,self.script)
        timed,clock=align_plan(self.dossier,self.script,plan,narration)
        self.assertEqual(timed.status,'needs_revision');self.assertEqual(timed.timeline,[])
        self.assertTrue(any('60' in issue for issue in timed.issues));self.assertEqual(clock['duration'],5)

    def test_long_narration_stops_without_truncating(self):
        self.provider.seconds=40
        with self.assertRaisesRegex(ValueError,'exceeds 150'):self.generate()

    def test_pronunciation_guidance_only_affects_relevant_phrase(self):
        from war_writer.models import Pronunciation
        self.script.draft.scenes[0].phrases[0].text+=' Austerlitz.'
        self.generate()
        changed=self.script.model_copy(deep=True)
        changed.draft.pronunciations=[Pronunciation(term='Austerlitz',say_as='OW-ster-lits')]
        self.assertEqual(self.generate(changed).requests,1)
        self.assertIn('OW-ster-lits',self.provider.calls[-1][1])

    def test_cli_saves_contract_and_aligns_without_real_provider(self):
        from war_narration.__main__ import main
        self.provider.seconds=24
        plan=DirectorAgent(DirectorModel()).direct(self.dossier,self.script)
        paths=[]
        for name,contract in [('script',self.script),('dossier',self.dossier),('plan',plan)]:
            path=self.root/(name+'.json');path.write_text(contract.model_dump_json(),encoding='utf-8');paths.append(path)
        args=[str(paths[0]),'--output',str(self.output),'--cache',str(self.cache),'--env-file',str(self.root/'absent'),
              '--dossier',str(paths[1]),'--plan',str(paths[2])]
        with patch('war_narration.__main__.GeminiSpeech',return_value=self.provider),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args),0)
            self.assertEqual(main(args[:-2]),1)
        self.assertTrue(list(self.output.glob('*-captions.srt')))


class ProviderTests(unittest.TestCase):
    def test_transcript_is_separate_from_style_and_rest_audio_is_decoded(self):
        captured=[]
        def transport(url,payload,headers):
            captured.append(payload)
            return {'status':'completed','steps':[{'type':'model_output','content':[
                {'type':'audio','mime_type':'audio/wav','data':base64.b64encode(wav()).decode()}]}]}
        self.assertEqual(GeminiSpeech('test-key',transport).synthesize('Hold the crossing.','Curious and restrained.','gemini-3.8-flash-tts','Charon'),wav())
        part=captured[0]['input'][0]['content'][0]
        self.assertEqual(part['text'],'Hold the crossing.');self.assertNotIn('Curious',part['text'])
        self.assertIn('Curious',part['annotations'][0]['style']);self.assertFalse(captured[0]['store'])

    def test_bad_provider_responses_and_missing_key_fail_explicitly(self):
        with self.assertRaises(ValueError):GeminiSpeech('')
        for result in ({},{'status':'failed','steps':[]},{'steps':None},{'steps':['invalid']},
                       {'status':'completed','steps':[{'type':'model_output','content':[{'type':'audio','data':'??'}]}]},
                       {'status':'completed','steps':[{'type':'model_output','content':[{'type':'audio','mime_type':'audio/mpeg'}]}]}):
            with self.subTest(result=result),self.assertRaises(ProviderError):
                GeminiSpeech('test-key',lambda *args:result).synthesize('Text','Style','model','Charon')

    def test_tts_429_has_resumable_quota_error(self):
        def transport(*args):raise ProviderError('Provider HTTP 429.')
        with self.assertRaises(SpeechQuotaError):GeminiSpeech('test-key',transport).synthesize('Text','Style','model','Charon')

    def test_network_transport_can_disable_hidden_retries(self):
        attempts=[]
        def opener(*args,**kwargs):attempts.append(1);raise URLError('Synthetic transport failure')
        with self.assertRaises(ProviderError):request_json('https://example.test',opener=opener,retries=0)
        self.assertEqual(len(attempts),1)
        with patch('war_narration.provider.request_json',side_effect=ProviderError('network')) as call:
            with self.assertRaises(ProviderError):GeminiSpeech('test-key').synthesize('Text','Style','model','Charon')
            self.assertEqual(call.call_args.kwargs['retries'],0)


@unittest.skipUnless(importlib.util.find_spec('langgraph'),'Install workflow extra')
class SpeechGraphTests(unittest.TestCase):
    def setUp(self):
        from war_workflow.store import ProjectStore
        from war_workflow.graph import Runner
        from war_workflow.authoring import adapters
        from war_workflow.speech import adapters as speech_adapters
        from .test_workflow_authoring import Model
        from .helpers import FakeWeb
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=ProjectStore.create(self.root/'project','Example Battle')
        self.model=Model();self.web=FakeWeb();self.provider=Speech(24)
        self.registry=adapters(lambda:self.model,lambda:self.web)|speech_adapters(lambda:self.provider)
        self.runner=Runner(self.store,self.registry)

    def artifact(self,stage):return self.store.read_artifact(stage,self.store.load().artifacts[stage])

    def test_real_graph_connects_tts_and_timing_then_stops_at_visual_production(self):
        result=self.runner.run()
        self.assertIn('narration',result.artifacts);self.assertIn('timing',result.artifacts)
        self.assertEqual(result.blocked_stage,'terrain')
        self.assertEqual(self.artifact('timing').output.data['duration'],97)
        self.assertEqual(self.store.budgets(result.id)['tts_requests']['used'],len(self.provider.calls))
        self.assertTrue(Path(self.artifact('timing').output.files['captions']).is_file())
        calls=len(self.provider.calls);self.runner.run();self.assertEqual(len(self.provider.calls),calls)

    def test_budget_and_provider_quota_resume_without_research_or_writing(self):
        self.store.set_limit(self.store.load().id,'tts_requests',0)
        result=self.runner.run();self.assertEqual(result.status,'quota_wait')
        self.assertEqual(self.provider.calls,[]);models=len(self.model.calls)
        self.store.set_limit(result.id,'tts_requests',20);self.provider.error=SpeechQuotaError('Synthetic provider quota')
        self.assertEqual(self.runner.run().status,'quota_wait')
        self.provider.error=None;result=self.runner.run()
        self.assertIn('timing',result.artifacts);self.assertEqual(len(self.model.calls),models+1) # plan review ran after narration resumed

    def test_queued_settings_keep_delivery_when_a_later_edit_changes_the_voice(self):
        from war_workflow.models import Edit
        self.runner.run()
        first=self.store.edit(Edit(parent_revision=self.store.load().id,kind='narration',patch={'notes':'Brisk and engaged.','trim_silence':True}))
        self.store.edit(Edit(parent_revision=first.id,kind='narration',patch={'voice':'Kore'}))
        self.runner.run();saved=self.artifact('narration').output.data
        self.assertEqual(saved['narration']['request']['notes'],'Brisk and engaged.')
        self.assertTrue(saved['narration']['request']['trim_silence'])
        self.assertEqual(saved['narration']['request']['voice'],'Kore')
        self.assertEqual(saved['request_settings'],self.store.load().params['narration'])

    def test_timing_binds_current_external_plan_review_and_rejects_mismatched_review(self):
        from war_workflow.models import Output
        from war_workflow.planner import fingerprint as key
        self.runner.run();revision=self.store.load();data=self.artifact('direction').output.data.copy();data['review']=None
        direction=self.store.write_artifact('direction',key('external review binding'),Output(data=data))
        revision.artifacts['direction']=direction.id;self.store.save(revision)
        ctx=self.runner.context(revision,'timing');result=self.registry['timing'].run(ctx)
        self.assertEqual(result.data['plan']['review']['status'],'pass')
        bad=self.artifact('plan_review').output.data.copy();bad['artifact_sha256']='0'*64
        review=self.store.write_artifact('plan_review',key('mismatched external review'),Output(data=bad,review='pass'))
        revision.artifacts['plan_review']=review.id;self.store.save(revision)
        with self.assertRaisesRegex(RuntimeError,'current passing'):self.registry['timing'].run(self.runner.context(revision,'timing'))

    def test_scoped_edits_accumulate_and_leave_other_clips_unchanged(self):
        from war_workflow.models import Edit
        self.runner.run();old=self.artifact('narration').output.data['narration']
        first=self.store.edit(Edit(parent_revision=self.store.load().id,kind='narration',scene_ids=['s1'],notes='Sound curious.'))
        result=self.runner.run();one=self.artifact('narration').output.data['narration']
        self.assertNotEqual(one['clips'][0]['key'],old['clips'][0]['key'])
        self.assertEqual(one['clips'][1]['key'],old['clips'][1]['key'])
        self.assertNotIn('writing',result.executed);self.assertNotIn('direction',result.executed)
        self.store.edit(Edit(parent_revision=first.id,kind='narration',object_ids=['s2.p1'],notes='Slightly more restrained.'))
        self.runner.run();two=self.artifact('narration').output.data['narration']
        self.assertEqual(two['clips'][0]['key'],one['clips'][0]['key'])
        self.assertNotEqual(two['clips'][1]['key'],one['clips'][1]['key'])
        self.store.edit(Edit(parent_revision=self.store.load().id,kind='narration',scene_ids=['s1'],notes='Sound curious.'))
        self.runner.run();three=self.artifact('narration').output.data['narration']
        self.assertEqual(three['clips'][1]['key'],two['clips'][1]['key'])
        self.assertEqual(three['requests'],0)

    def test_scoped_voice_setting_is_rejected_before_synthesis(self):
        from war_workflow.models import Edit
        self.runner.run();calls=len(self.provider.calls)
        self.store.edit(Edit(parent_revision=self.store.load().id,kind='narration',scene_ids=['s1'],patch={'voice':'Kore'},notes='Use this voice.'))
        result=self.runner.run()
        self.assertEqual(result.blocked_stage,'narration');self.assertIn('unscoped',result.issues[0])
        self.assertEqual(len(self.provider.calls),calls)

    def test_metadata_only_script_change_rebinds_narration_without_tts(self):
        from war_workflow.graph import Context
        from war_workflow.models import Output
        from war_workflow.planner import fingerprint as key
        self.runner.run();previous=self.artifact('narration');script=self.artifact('writing').output.data
        script['model_calls']+=1
        changed=self.store.write_artifact('writing',key('changed bookkeeping'),Output(data=script))
        ctx=Context(self.store,self.store.load(),'narration',{'writing':changed},previous)
        output=self.registry['narration'].rebind(ctx,previous)
        self.assertNotEqual(output.data['narration']['script_sha256'],previous.output.data['narration']['script_sha256'])
        self.assertEqual(output.data['narration']['requests'],0)


if __name__=='__main__':unittest.main()
