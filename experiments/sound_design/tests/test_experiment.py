from array import array
import contextlib
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from experiments.sound_design.agent import design, identity
from experiments.sound_design.models import Brief, Layer, Recipe
from experiments.sound_design.render import measure, render
from experiments.sound_design.compare import gallery, level_match, main as compare_main
from experiments.sound_design.__main__ import main
from war_content.agent import OfflineModel
from war_content.sound_render import read_wave
from war_research.providers import ProviderError
from experiments.sound_design.serve import Handler, main as serve_main
from functools import partial
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import MagicMock


def brief():
    return Brief(concept='new_wooden_unit',description='Wooden wheels creaking over uneven dry ground.',duration=.5,loop=False)


def recipe():
    return Recipe(label='Wooden friction',explanation='Filtered noise texture and a restrained structural resonance.',
        duration=.5,loop=False,seed=7,layers=[
            Layer(name='Wood friction',source='noise',duration=.5,gain_db=-12,highpass=100,lowpass=2500),
            Layer(name='Body',source='triangle',duration=.3,start=.1,gain_db=-22,frequency_start=280,frequency_end=90)])


class Model:
    def __init__(self,replies):self.replies=list(replies);self.used=[];self.prompts=[]
    def generate(self,prompt,schema,consume):
        consume();self.prompts.append(prompt)
        item=self.replies.pop(0)
        if isinstance(item,Exception):raise item
        self.used.append('fake:recipe-author');return item


class ContractTests(unittest.TestCase):
    def test_invalid_sources_numbers_filters_envelopes_and_repeat_rates(self):
        base=recipe().layers[0].model_dump()
        for values in ({'source':'eval'}, {'gain_db':float('nan')}, {'frequency_start':24000},
                       {'highpass':5000,'lowpass':1000}, {'duration':.1,'attack':.2},
                       {'repeat_every':.01}, {'jitter':.1}):
            with self.subTest(values=values),self.assertRaises(ValidationError):Layer(**(base|values))
        with self.assertRaises(ValidationError):Layer(**(base|{'code':'print(1)'}))

    def test_work_budget_extent_layer_count_and_invalid_brief(self):
        data=recipe().model_dump()
        data['layers'][0]['start']=.3
        with self.assertRaises(ValidationError):Recipe.model_validate(data)
        data=recipe().model_dump();data['layers']*=7
        with self.assertRaises(ValidationError):Recipe.model_validate(data)
        heavy=Layer(name='Excess work',source='noise',duration=12,gain_db=-12,repeat_every=.06)
        with self.assertRaises(ValidationError):Recipe(label='Too much',explanation='This asks for an excessive synthesis workload.',duration=12,loop=True,seed=0,layers=[heavy])
        with self.assertRaises(ValidationError):Brief(concept='../escape',description='An invalid concept should not become a path.',duration=6)


class RenderTests(unittest.TestCase):
    def test_repeatable_finite_stereo_duration_and_click_free_edges(self):
        a,m=render(recipe(),8000);b,n=render(recipe(),8000)
        self.assertEqual(a,b);self.assertEqual(m,n);self.assertEqual(len(a),8000)
        self.assertTrue(m['technical_pass']);self.assertTrue(all(math.isfinite(v) for v in a))
        self.assertEqual(a[:2],array('f',[0,0]));self.assertEqual(a[-2:],array('f',[0,0]))
        self.assertLessEqual(max(abs(v) for v in a),.892)
        changed=recipe().model_copy(update={'seed':8});self.assertNotEqual(a,render(changed,8000)[0])

    def test_repeated_jittered_hits_pan_and_all_sources(self):
        for source in ('noise','sine','triangle'):
            r=recipe();r.layers=[Layer(name='Individual knocks',source=source,start=.1,duration=.06,gain_db=-6,
                attack=.002,release=.01,decay=12,repeat_every=.1,jitter=.2,pan=.5,tremolo_hz=9,tremolo_depth=.5)]
            audio,metrics=render(r,8000)
            self.assertEqual(max(abs(v) for v in audio[:800]),0)
            left=sum(v*v for v in audio[::2]);right=sum(v*v for v in audio[1::2]);self.assertGreater(right,left)
            self.assertGreater(metrics['rms_dbfs'],-60)

    def test_silence_excess_gain_and_invalid_rate_are_not_approved(self):
        weak=recipe();weak.layers=[Layer(name='Barely audible',source='noise',duration=.5,gain_db=-50,highpass=30,lowpass=50)]
        self.assertFalse(render(weak,8000)[1]['technical_pass'])
        loud=recipe();loud.layers=[Layer(name='Overlapping tones',source='sine',duration=.5,gain_db=-3)]*12
        audio,metrics=render(loud,8000);self.assertFalse(metrics['technical_pass']);self.assertLess(metrics['headroom_scale'],.4)
        with self.assertRaises(ValueError):render(recipe(),4000)
        with self.assertRaises(ValueError):measure(array('f',[float('nan'),0]))
        with self.assertRaises(ValueError):measure(array('f'))


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_generate_save_and_cache_remain_explicitly_unapproved(self):
        root,result=design(brief(),Model([recipe()]),self.root/'runs',cache=self.root/'cache')
        self.assertEqual(result['status'],'technical_pass_listening_pending');self.assertFalse(result['listening_approved'])
        self.assertEqual(result['model_calls'],1);self.assertTrue((root/'candidate.wav').exists())
        cached,reused=design(brief(),OfflineModel(),self.root/'runs',cache=self.root/'cache',reuse=True)
        self.assertTrue(reused['reused']);self.assertEqual(reused['model_calls'],0)
        self.assertEqual((root/'candidate.wav').read_bytes(),(cached/'candidate.wav').read_bytes())
        entry=json.loads(next((self.root/'cache').glob('*.json')).read_text());self.assertFalse(entry['listening_approved'])

    def test_repairs_failed_provider_and_quiet_recipe_with_bounded_calls(self):
        model=Model([ProviderError('Bad JSON'),recipe()])
        root,result=design(brief(),model,self.root/'runs')
        self.assertEqual(result['model_calls'],2);self.assertEqual(result['issues'],[]);self.assertIn('Repair',model.prompts[1])
        weak=recipe();weak.layers=[Layer(name='Quiet',source='noise',duration=.5,gain_db=-50,lowpass=50)]
        model=Model([weak,recipe()]);root,result=design(brief(),model,self.root/'runs')
        self.assertEqual(result['issues'],[]);self.assertIn('REPAIR TECHNICAL',model.prompts[1])
        root,failed=design(brief(),Model([weak]),self.root/'runs',max_model_calls=1,cache=self.root/'empty')
        self.assertEqual(failed['status'],'needs_revision');self.assertFalse((self.root/'empty').exists())

    def test_wrong_identity_failed_generation_and_no_implicit_offline_design(self):
        wrong=recipe().model_copy(update={'duration':.6})
        root,result=design(brief(),Model([wrong,wrong]),self.root/'runs')
        self.assertFalse((root/'candidate.wav').exists());self.assertEqual(result['status'],'needs_revision')
        root,result=design(brief(),OfflineModel(),self.root/'runs');self.assertEqual(result['status'],'needs_revision')
        with self.assertRaises(ValueError):design(brief(),OfflineModel(),self.root,max_model_calls=0)

    def test_cache_tampering_and_changed_brief_identity(self):
        design(brief(),Model([recipe()]),self.root/'runs',cache=self.root/'cache')
        path=next((self.root/'cache').glob('*.json'));entry=json.loads(path.read_text());entry['recipe']['label']='Tampered'
        path.write_text(json.dumps(entry))
        with self.assertRaises(ValueError):design(brief(),OfflineModel(),self.root/'runs',cache=self.root/'cache',reuse=True)
        self.assertNotEqual(identity(brief()),identity(brief().model_copy(update={'description':'A different supported sound description.'})))

    def test_offline_recipe_cli_and_invalid_inputs(self):
        b=self.root/'brief.json';r=self.root/'recipe.json';b.write_text(brief().model_dump_json());r.write_text(recipe().model_dump_json())
        args=[str(b),'--recipe',str(r),'--output',str(self.root/'out'),'--cache',str(self.root/'cache'),'--env-file',str(self.root/'absent.env')]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args),0);r.write_text('{}');self.assertEqual(main(args),1)
            self.assertEqual(main([str(self.root/'missing.json')]),1)

    def test_comparison_matching_gallery_and_reveal_labels(self):
        r=recipe();b=brief().model_copy(update={'concept':'armored_tracks'})
        run,result=design(b,Model([r]),self.root/'runs')
        folder=gallery([run],self.root/'gallery')
        data=json.loads((folder/'comparison.json').read_text());self.assertFalse(data[0]['listening_approved'])
        self.assertEqual(len(data[0]['sources']),2)
        clips=[read_wave(folder/'0-armored_tracks'/f'{label}.wav') for label in ('A','B')]
        rms=[math.sqrt(sum(v*v for v in c)/len(c)) for c in clips];self.assertAlmostEqual(rms[0],rms[1],places=4)
        self.assertIn('Reveal sources',(folder/'index.html').read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):level_match([array('f',[0,0])])
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(compare_main([str(self.root/'missing'),'--output',str(self.root/'bad-gallery')]),1)

    def test_generation_failure_is_visible_in_gallery_without_fabricated_audio(self):
        run,result=design(brief(),Model([ProviderError('Unavailable')]*2),self.root/'runs')
        folder=gallery([run],self.root/'failed-gallery')
        markup=(folder/'index.html').read_text(encoding='utf-8')
        self.assertIn('No candidate audio',markup);self.assertEqual(list(folder.glob('**/*.wav')),[])


class GalleryServerTests(unittest.TestCase):
    def test_wav_ranges_and_unknown_paths(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'index.html').write_text('Listening comparison',encoding='utf-8')
            raw=b'0123456789';(root/'sample.wav').write_bytes(raw)
            with ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root))) as server:
                worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                base=f'http://127.0.0.1:{server.server_port}'
                try:
                    with urlopen(base) as response:self.assertIn(b'Listening comparison',response.read())
                    for value,expected in [('bytes=2-4',b'234'),('bytes=7-',b'789'),('bytes=-2',b'89')]:
                        with urlopen(Request(base+'/sample.wav',headers={'Range':value})) as response:
                            self.assertEqual(response.status,206);self.assertEqual(response.read(),expected)
                    with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/sample.wav',headers={'Range':'bytes=100-'}))
                    self.assertEqual(error.exception.code,416)
                    with self.assertRaises(HTTPError):urlopen(base+'/%2e%2e/secret.env')
                finally:server.shutdown();worker.join()

    def test_local_server_cli_and_invalid_root(self):
        with TemporaryDirectory() as tmp:
            server=MagicMock();server.server_port=8765;server.__enter__.return_value=server
            server.serve_forever.side_effect=KeyboardInterrupt
            with patch('experiments.sound_design.serve.ThreadingHTTPServer',return_value=server),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(serve_main(['--root',tmp,'--port','0']),0)
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):serve_main(['--root',str(Path(tmp)/'missing')])


if __name__=='__main__':unittest.main()
