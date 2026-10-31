from array import array
import contextlib
import io
import json
import math
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import wave
from pydantic import ValidationError
from war_content.sound_models import SoundConfig, SoundCue, SoundPlan
from war_content.sound_plan import compile_plan
from war_content.sound_render import mix_voice, read_wave, render_effects, synth_sample, write_wave
from war_content.sound_effects import compile_bundle, main, mux_video


def scene():
    route=[{'x':.2,'y':.5},{'x':.7,'y':.5}]
    return {'schema_version':'1.0','topic':'Synthetic sound test','duration':4,
        'assets':{'unit':{}},'scenes':[{'scene_id':'s'}],
        'blueprint':{'scale':'tactical','forces':[{'id':'a','kind':'infantry','subgroups':4}],
                     'scenes':[{'actions':[{'id':'m','kind':'move','unit_id':'a','route':route,'stagger':.2},
                                           {'id':'fire','kind':'engage','unit_id':'a'}]}]},
        'timeline':[{'action_id':'intro-a','unit_id':'a','kind':'introduce','start_sec':0,'end_sec':0},
                    {'action_id':'m','unit_id':'a','kind':'move','start_sec':1,'end_sec':3},
                    {'action_id':'fire','unit_id':'a','kind':'engage','start_sec':3,'end_sec':4}]}


class SoundPlanTests(unittest.TestCase):
    def test_static_area_callouts_do_not_get_fictional_movement_or_firing(self):
        for mode in ('geography','battlefield'):
            s=scene();s[mode]={'mode':'context'}
            plan=compile_plan(s,SoundConfig())
            self.assertEqual(plan.cues,[]);self.assertEqual(plan.omitted_actions,['m'])
            spots=SoundConfig.model_validate({'spots':[{'action_id':'fire','time':3.2,'effect':'cannon'}]})
            with self.assertRaises(ValueError):compile_plan(s,spots)

    def test_movement_matches_actual_subgroup_departures_and_is_deterministic(self):
        s=scene();plan=compile_plan(s,SoundConfig())
        self.assertEqual([c.subgroup for c in plan.cues],[0,2,3])
        self.assertAlmostEqual(plan.cues[-1].start,1.4)
        self.assertEqual(plan.cues[-1].end,3)
        self.assertEqual({c.effect for c in plan.cues},{'footsteps'})
        self.assertEqual(plan,compile_plan(s,SoundConfig()))
        s['topic']='Different input';self.assertNotEqual(plan.scene_sha256,compile_plan(s,SoundConfig()).scene_sha256)

    def test_profiles_unknown_none_campaign_stationary_and_fade(self):
        s=scene();s['blueprint']['forces'][0]['kind']='army'
        self.assertEqual(compile_plan(s,SoundConfig()).unresolved_units,['a'])
        none=SoundConfig.model_validate({'profiles':{'a':{'movement':'none'}}})
        self.assertEqual(compile_plan(s,none).cues,[])
        tracks=SoundConfig.model_validate({'profiles':{'a':{'movement':'tracks'}}})
        s['blueprint']['scale']='campaign';self.assertEqual(len(compile_plan(s,tracks).cues),1)
        s['timeline'].append({'kind':'fade','unit_id':'a','start_sec':1.5,'end_sec':2})
        self.assertEqual(compile_plan(s,tracks).cues[0].end,2)
        s['blueprint']['scenes'][0]['actions'][0]['route']=[{'x':.2,'y':.5}]*2
        self.assertEqual(compile_plan(s,tracks).cues,[])

    def test_no_weapon_events_inferred_and_explicit_spots_are_checked(self):
        self.assertFalse(any(not c.loop for c in compile_plan(scene(),SoundConfig()).cues))
        config=SoundConfig.model_validate({'spots':[{'action_id':'fire','time':3.2,'effect':'musket'}]})
        plan=compile_plan(scene(),config);self.assertFalse(plan.cues[-1].loop)
        self.assertEqual(plan.cues[-1].effect,'musket');self.assertEqual(plan.cues[-1].end,4)
        for action,time in [('m',1.5),('fire',2),('unknown',3.5)]:
            bad=SoundConfig.model_validate({'spots':[{'action_id':action,'time':time,'effect':'cannon'}]})
            with self.assertRaises(ValueError):compile_plan(scene(),bad)

    def test_invalid_profiles_timing_subgroups_geometry_and_models(self):
        with self.assertRaises(ValueError):compile_plan(scene(),SoundConfig.model_validate({'profiles':{'missing':{'movement':'tracks'}}}))
        for change in ('intro','bounds','subgroups','route','stagger'):
            s=scene()
            if change=='intro':s['timeline'][0]['start_sec']=2
            if change=='bounds':s['timeline'][1]['end_sec']=8
            if change=='subgroups':s['blueprint']['forces'][0]['subgroups']=13
            if change=='route':s['blueprint']['scenes'][0]['actions'][0]['route']=[]
            if change=='stagger':s['blueprint']['scenes'][0]['actions'][0]['stagger']=.9
            with self.subTest(change=change),self.assertRaises(ValueError):compile_plan(s,SoundConfig())
        cue=compile_plan(scene(),SoundConfig()).cues[0].model_dump();cue['end']=cue['start']
        with self.assertRaises(ValidationError):SoundCue(**cue)
        plan=compile_plan(scene(),SoundConfig()).model_dump();plan['duration']=2
        with self.assertRaises(ValidationError):SoundPlan(**plan)
        with self.assertRaises(ValidationError):SoundConfig.model_validate({'profiles':{'a':{'movement':'tracks','gain_db':float('nan')}}})


class SoundRenderTests(unittest.TestCase):
    def test_all_original_effects_are_finite_nonzero_and_repeatable(self):
        for effect in ('footsteps','heavy_steps','hooves','tracks','wheels','cannon','musket','rifle','clash'):
            with self.subTest(effect=effect):
                samples=synth_sample(effect,8000)
                self.assertTrue(all(math.isfinite(v) for v in samples))
                self.assertGreater(max(abs(v) for v in samples),.01)
                self.assertEqual(samples,synth_sample(effect,8000))
                self.assertEqual(samples[0],0)

    def test_effects_are_silent_before_departure_and_after_halt(self):
        plan=compile_plan(scene(),SoundConfig())
        output=render_effects(plan,rate=8000)
        self.assertEqual(len(output),4*8000*2)
        self.assertEqual(max(abs(v) for v in output[:16000]),0)
        self.assertGreater(max(abs(v) for v in output[20000:40000]),.01)
        self.assertEqual(max(abs(v) for v in output[3*16000:]),0)
        plan.unresolved_units=['a']
        with self.assertRaises(ValueError):render_effects(plan,rate=8000)

    def test_voice_ducks_effects_and_preserves_silence_release_and_headroom(self):
        rate=1000;effects=array('f',[.1])*(3*rate*2);voice=array('f',[0])*len(effects)
        for frame in range(rate,2*rate):
            v=.15*math.sin(2*math.pi*50*frame/rate);voice[2*frame]=v;voice[2*frame+1]=v
        mixed,stats=mix_voice(effects,voice,rate)
        residual=lambda frame:mixed[frame*2]-voice[frame*2]
        self.assertGreater(residual(500),.09);self.assertLess(residual(1500),.03)
        self.assertGreater(residual(2800),.09);self.assertGreater(stats['speech_blocks'],0)
        loud,metrics=mix_voice(array('f',[2.0,-2.0])*100)
        self.assertLessEqual(max(abs(v) for v in loud),.892);self.assertLess(metrics['headroom_scale'],1)
        with self.assertRaises(ValueError):mix_voice(effects,voice+array('f',[0,0]),rate)

    def test_wav_roundtrip_resampling_replacements_and_invalid_inputs(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'sample.wav'
            source=array('f',[.2,-.1])*800
            write_wave(path,source,8000)
            decoded=read_wave(path,16000);self.assertEqual(len(decoded),3200)
            self.assertAlmostEqual(decoded[0],.2,places=4)
            plan=compile_plan(scene(),SoundConfig())
            replacement=render_effects(plan,{'footsteps':path},rate=8000)
            self.assertGreater(max(abs(v) for v in replacement),0)
            for values in (array('f',[0]),array('f',[float('nan'),0])):
                with self.assertRaises(ValueError):write_wave(path,values)
            path.write_bytes(b'broken')
            with self.assertRaises(ValueError):read_wave(path)
            for width,channels,frames in ((1,1,8),(2,3,8),(2,1,0)):
                with wave.open(str(path),'wb') as w:
                    w.setnchannels(channels);w.setsampwidth(width);w.setframerate(8000);w.writeframes(b'\0'*(width*channels*frames))
                with self.assertRaises(ValueError):read_wave(path)


class SoundBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.bundle=self.root/'source';self.bundle.mkdir()
        (self.bundle/'scene.json').write_text(json.dumps(scene()),encoding='utf-8')
        (self.bundle/'content.json').write_text('{"status":"ready"}',encoding='utf-8')
        (self.bundle/'pixi.min.js').write_text('// fixture',encoding='utf-8')
        (self.bundle/'secret.env').write_text('DO NOT COPY',encoding='utf-8')

    def test_sound_bundle_preserves_source_and_adds_portable_audio_and_report(self):
        original=(self.bundle/'scene.json').read_bytes()
        target,ok=compile_bundle(self.bundle,SoundConfig(),self.root/'output')
        self.assertTrue(ok);self.assertFalse((target/'secret.env').exists())
        self.assertEqual((self.bundle/'scene.json').read_bytes(),original)
        payload=json.loads((target/'scene.json').read_text(encoding='utf-8'))
        self.assertEqual(payload['soundtrack']['file'],'soundtrack.wav')
        self.assertTrue((target/'sound-report.md').exists());self.assertTrue((target/'playback.mjs').exists())
        with wave.open(str(target/'soundtrack.wav')) as audio:
            self.assertEqual(audio.getframerate(),48000);self.assertEqual(audio.getnframes(),4*48000)

    def test_unresolved_profiles_invalid_bundle_missing_replacement_and_cli(self):
        s=scene();s['blueprint']['forces'][0]['kind']='army'
        (self.bundle/'scene.json').write_text(json.dumps(s),encoding='utf-8')
        target,ok=compile_bundle(self.bundle,SoundConfig(),self.root/'output')
        self.assertFalse(ok);self.assertFalse((target/'soundtrack.wav').exists())
        config=self.root/'config.json';config.write_text('{"profiles":{"a":{"movement":"none"}}}',encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.bundle),'--output',str(self.root/'cli')]),2)
            self.assertEqual(main([str(self.root/'missing')]),1)
            self.assertEqual(main([str(self.bundle),'--profiles',str(config),'--output',str(self.root/'cli')]),0)
            config.write_text('broken',encoding='utf-8');self.assertEqual(main([str(self.bundle),'--profiles',str(config)]),1)
        (self.bundle/'scene.json').write_text(json.dumps(scene()),encoding='utf-8')
        missing=SoundConfig.model_validate({'samples':{'footsteps':{'path':'missing.wav','attribution':'Test source'}}})
        with self.assertRaises(ValueError):compile_bundle(self.bundle,missing,self.root/'output',sample_root=self.root)

    def test_mux_success_duration_mismatch_and_failure(self):
        good=SimpleNamespace(returncode=0,stdout=b'{"format":{"duration":"4"}}')
        with patch('war_content.sound_effects.subprocess.run',side_effect=[good,SimpleNamespace(returncode=0)]):mux_video('v.mp4','a.wav','o.mp4',4)
        with patch('war_content.sound_effects.subprocess.run',return_value=good),self.assertRaises(ValueError):mux_video('v','a','o',5)
        for response,error in ((SimpleNamespace(returncode=0,stdout=b'broken'),ValueError),):
            with patch('war_content.sound_effects.subprocess.run',return_value=response),self.assertRaises(error):mux_video('v','a','o',4)
        with patch('war_content.sound_effects.subprocess.run',side_effect=[good,SimpleNamespace(returncode=1)]),self.assertRaises(RuntimeError):mux_video('v','a','o',4)

    def test_custom_samples_and_narration_survive_effects_rebuild(self):
        recording=self.root/'step.wav';voice=self.root/'voice.wav'
        write_wave(recording,array('f',[.2,.2])*4800)
        write_wave(voice,array('f',[.1,.1])*96000)
        config=SoundConfig.model_validate({'samples':{'footsteps':{'path':'step.wav','attribution':'Original offline test recording'}}})
        target,ok=compile_bundle(self.bundle,config,self.root/'output',narration=voice,sample_root=self.root)
        self.assertTrue(ok);self.assertTrue((target/'narration.wav').exists())
        self.assertEqual(voice.read_bytes(),(target/'narration.wav').read_bytes())
        metrics=json.loads((target/'sound-metrics.json').read_text(encoding='utf-8'))
        self.assertGreater(metrics['mix']['speech_blocks'],0)
        self.assertIn('Original offline test recording',(target/'sound-report.md').read_text(encoding='utf-8'))
        rebuilt,ok=compile_bundle(target,SoundConfig(),self.root/'output')
        self.assertTrue(ok)
        self.assertEqual((target/'narration.wav').read_bytes(),(rebuilt/'narration.wav').read_bytes())
        (target/'narration.wav').unlink()
        with self.assertRaises(ValueError):compile_bundle(target,SoundConfig(),self.root/'output')
