from array import array
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from war_content.music_models import MusicConfig, MusicSource, MixSettings
from war_content.music_render import ambient_bed, fit_track, mix_music
from war_content.music import compile_bundle, decode_track, main, prepare_music
from war_content.sound_effects import compile_bundle as compile_effects
from war_content.sound_models import SoundConfig
from war_content.sound_render import mix_voice, read_wave, write_wave
from .test_sound import scene
from war_content.play import ready


class MusicRenderTests(unittest.TestCase):
    def test_settings_and_source_validation(self):
        for values in ({'music_gain_db':float('nan')},{'music_gain_db':1},{'end_sec':1,'start_sec':2},{'voice_margin_db':1}):
            with self.assertRaises(ValidationError):MixSettings(**values)
        with self.assertRaises(ValidationError):MusicSource(kind='file')
        with self.assertRaises(ValidationError):MusicSource(path='unused.wav')
        source=MusicSource(kind='file',path='a-track.mp3')
        self.assertEqual(source.title,'a-track');self.assertEqual(source.attribution,'User-supplied local track.')

    def test_original_demo_is_deterministic_stereo_and_slowly_evolves(self):
        first=ambient_bed(1000)
        self.assertEqual(first,ambient_bed(1000));self.assertEqual(len(first),32*1000*2)
        self.assertTrue(all(math.isfinite(v) for v in first));self.assertGreater(max(abs(v) for v in first),.01)
        self.assertNotEqual(first[:2000],first[16000:18000])

    def test_track_normalization_repeat_fades_and_padding(self):
        samples=array('f',(.2*math.sin(2*math.pi*20*i/1000) for i in range(1000) for c in (0,1)))
        loop,stats=fit_track(samples,2,True,.05,1000)
        self.assertEqual(len(loop),4000);self.assertEqual(stats['active_duration'],2)
        self.assertLessEqual(max(abs(v) for v in loop),.5)
        self.assertAlmostEqual(stats['prepared_rms_dbfs'],-20,places=4)
        stopped,stats=fit_track(samples,2,False,.05,1000)
        self.assertEqual(max(abs(v) for v in stopped[2000:]),0);self.assertEqual(stats['active_duration'],1)
        with self.assertRaises(ValueError):fit_track(array('f',[0,0]),2,rate=1000)
        with self.assertRaises(ValueError):fit_track(array('f',[0])*1000,2,rate=1000)

    def test_music_is_very_quiet_and_ducks_beneath_voice_and_effects(self):
        rate=1000;size=rate*3*2;fx=array('f',[0])*size;voice=array('f',[0])*size;music=array('f',[.1])*size
        for i in range(rate,rate*2):voice[2*i]=voice[2*i+1]=.1
        settings=MixSettings(fade_in_sec=0,fade_out_sec=0,release_sec=.1)
        mix,bed,stats=mix_music(fx,voice,music,settings,3,rate)
        self.assertLess(abs(bed[3000]),abs(bed[1000])*.4)
        self.assertLess(abs(bed[1000]),.009);self.assertGreater(abs(bed[5600]),abs(bed[3000])*2)
        self.assertGreater(stats['voice_duck_blocks'],0)
        for i in range(rate,rate*2):fx[2*i]=fx[2*i+1]=.2
        mix,bed,stats=mix_music(fx,None,music,settings,3,rate)
        self.assertGreater(stats['effects_duck_blocks'],0);self.assertLess(bed[3000],bed[1000]*.6)

    def test_quiet_narration_gets_extra_margin_and_output_has_headroom(self):
        rate=1000;voice=array('f',[.015])*4000;zero=array('f',[0])*4000;music=array('f',[.1])*4000
        settings=MixSettings(fade_in_sec=0,fade_out_sec=0)
        output,bed,stats=mix_music(zero,voice,music,settings,2,rate)
        self.assertLessEqual(bed[2000],.015*10**(-22/20)+1e-6)
        loud=array('f',[2])*4000
        output,bed,stats=mix_music(loud,None,music,settings,2,rate)
        self.assertLessEqual(max(abs(v) for v in output),.892)

    def test_disable_trim_fades_and_duration_errors(self):
        rate=1000;zero=array('f',[0])*6000;music=array('f',[.1])*6000
        output,bed,stats=mix_music(zero,None,music,MixSettings(enabled=False),3,rate)
        self.assertEqual(output,zero);self.assertEqual(bed,zero)
        settings=MixSettings(start_sec=.5,end_sec=2.5,fade_in_sec=.2,fade_out_sec=.3)
        output,bed,stats=mix_music(zero,None,music,settings,3,rate)
        self.assertEqual(max(abs(v) for v in bed[:1000]),0);self.assertEqual(max(abs(v) for v in bed[5000:]),0)
        self.assertGreater(abs(bed[2000]),abs(bed[1020]))
        with self.assertRaises(ValueError):mix_music(zero,None,music[:-2],settings,3,rate)
        with self.assertRaises(ValueError):mix_music(zero,array('f',[0])*6002,music,settings,3,rate)
        with self.assertRaises(ValueError):mix_music(zero,None,music,MixSettings(start_sec=4),3,rate)


class MusicBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'source';self.source.mkdir();self.cache=self.root/'cache'
        payload=scene();payload['soundtrack']={'file':'soundtrack.wav','has_narration':False}
        (self.source/'scene.json').write_text(json.dumps(payload),encoding='utf-8')
        (self.source/'content.json').write_text('{"status":"ready"}',encoding='utf-8')
        (self.source/'pixi.min.js').write_text('// fixture',encoding='utf-8')
        (self.source/'secret.env').write_text('do not copy',encoding='utf-8')
        write_wave(self.source/'sound-effects.wav',array('f',[.04,-.04])*192000)
        self.bed=array('f',[.1,-.09])*48000

    def build(self,source=None,**kwargs):
        return compile_bundle(source or self.source,self.root/'output',cache=self.cache,**kwargs)

    def test_edit_gain_reuses_music_and_preserves_stems_and_versions(self):
        original=(self.source/'sound-effects.wav').read_bytes()
        with patch('war_content.music.ambient_bed',return_value=self.bed) as synth:
            first=self.build()
            second=self.build(first,config=MusicConfig(mix=MixSettings(music_gain_db=-30)))
            self.assertEqual(synth.call_count,1)
        for folder in (first,second):
            self.assertFalse((folder/'secret.env').exists());self.assertEqual((folder/'sound-effects.wav').read_bytes(),original)
        self.assertEqual((first/'music-source.wav').read_bytes(),(second/'music-source.wav').read_bytes())
        self.assertNotEqual((first/'soundtrack.wav').read_bytes(),(second/'soundtrack.wav').read_bytes())
        project=json.loads((second/'audio-project.json').read_text(encoding='utf-8'))
        self.assertTrue(project['prepared_music_reused']);self.assertEqual(project['parent_project_sha256'],hashlib.sha256((first/'audio-project.json').read_bytes()).hexdigest())
        self.assertEqual((self.source/'sound-effects.wav').read_bytes(),original)

    def test_file_track_is_portable_and_edit_needs_no_external_decode(self):
        imported=self.root/'my-music.wav';write_wave(imported,self.bed)
        config=MusicConfig(source=MusicSource(kind='file',path=imported.name))
        with patch('war_content.music.decode_track',return_value=self.bed) as decode:
            first=self.build(config=config,config_root=self.root)
            second=self.build(first)
            self.assertEqual(decode.call_count,1)
        self.assertEqual((first/'music-original.wav').read_bytes(),imported.read_bytes())
        self.assertEqual((second/'music-original.wav').read_bytes(),imported.read_bytes())
        self.assertEqual(json.loads((second/'music-config.json').read_text())['source']['path'],'music-original.wav')

    def test_narration_preserved_and_effects_rebuild_keeps_music(self):
        voice=self.root/'voice.wav';write_wave(voice,array('f',[.1,.1])*96000)
        with patch('war_content.music.ambient_bed',return_value=self.bed):first=self.build(narration=voice)
        self.assertEqual((first/'narration.wav').read_bytes(),voice.read_bytes())
        with patch('war_content.music.ambient_bed',side_effect=AssertionError('Do not regenerate music')):
            second,ok=compile_effects(first,SoundConfig(),self.root/'output')
        self.assertTrue(ok);self.assertEqual((first/'music-source.wav').read_bytes(),(second/'music-source.wav').read_bytes())
        self.assertEqual((second/'narration.wav').read_bytes(),voice.read_bytes())
        self.assertTrue(json.loads((second/'scene.json').read_text())['soundtrack']['has_music'])

    def test_missing_stems_tracks_bad_cache_and_cli_errors(self):
        with patch('war_content.music.ambient_bed',return_value=self.bed):first=self.build()
        (first/'music-source.wav').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.build(first)
        missing=MusicConfig(source=MusicSource(kind='file',path='absent.wav'))
        with self.assertRaises(ValueError):self.build(config=missing)
        for folder in (self.root/'output').iterdir():
            if not (folder/'music-report.md').exists():self.assertFalse(ready(folder))
        (self.source/'sound-effects.wav').unlink()
        with self.assertRaises(ValueError):self.build()
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main([str(self.root/'absent')]),1)

    def test_decoder_and_cli_success(self):
        def decoder(args,**kwargs):
            self.assertIn('-t',args);write_wave(args[-1],self.bed);return SimpleNamespace(returncode=0)
        with patch('war_content.music.subprocess.run',side_effect=decoder):self.assertEqual(len(decode_track('track.mp3',2,4)),len(self.bed))
        with patch('war_content.music.subprocess.run',return_value=SimpleNamespace(returncode=1)),self.assertRaises(ValueError):decode_track('bad',0,4)
        with patch('war_content.music.ambient_bed',return_value=self.bed),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.source),'--output',str(self.root/'cli'),'--cache',str(self.cache)]),0)

    def test_global_cache_disable_and_corrupt_cache_fail_explicitly(self):
        with patch('war_content.music.ambient_bed',return_value=self.bed) as synth:
            first=self.build();second=self.build()
            self.assertEqual(synth.call_count,1)
            disabled=self.build(second,config=MusicConfig(mix=MixSettings(enabled=False)))
            self.assertFalse(json.loads((disabled/'scene.json').read_text())['soundtrack']['has_music'])
        project=json.loads((first/'audio-project.json').read_text())
        cached=self.cache/project['source']['cache_key']/'music-source.wav';cached.write_bytes(b'broken')
        with self.assertRaises(ValueError):self.build()

    def test_visual_only_bundle_and_missing_voice_stem(self):
        payload=json.loads((self.source/'scene.json').read_text());payload.pop('soundtrack')
        (self.source/'scene.json').write_text(json.dumps(payload));(self.source/'sound-effects.wav').unlink()
        with patch('war_content.music.ambient_bed',return_value=self.bed):target=self.build()
        self.assertEqual(max(abs(v) for v in read_wave(target/'sound-effects.wav')),0)
        payload['soundtrack']={'file':'soundtrack.wav','has_narration':True}
        (target/'scene.json').write_text(json.dumps(payload))
        with self.assertRaises(ValueError):self.build(target)
