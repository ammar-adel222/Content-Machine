import unittest
import io
import json
import contextlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from war_content.benchmark import TRUTH, candidates, evaluate, report, vision_score
from war_content.models import Design
from war_research.providers import ProviderError
from .content_helpers import design


class BenchModel:
    def __init__(self,fail=False):self.used=[];self.fail=fail
    def generate(self,prompt,schema,consume,**kwargs):
        consume()
        if self.fail:raise ProviderError('Unavailable')
        self.used.append('fake:bench')
        return design() if schema is Design else TRUTH


class BenchmarkTests(unittest.TestCase):
    def test_free_catalog_filter_and_modalities(self):
        result=candidates([{'id':'dots-studio/dots-3-note-preview:free','pricing':{'prompt':'0','completion':'0'},'architecture':{'input_modalities':['image','text']}},
            {'id':'minimax/minimax-m3:free','pricing':{'prompt':'.1','completion':'0'}}])
        dots=next(r for r in result if 'dots-' in r['model']);self.assertTrue(dots['vision']);self.assertNotIn('skip',dots)
        self.assertIn('skip',next(r for r in result if 'minimax' in r['model']))

    def test_evaluate_valid_invalid_and_text_only(self):
        candidate={'provider':'gemini','model':'fake','vision':True}
        result=evaluate(candidate,BenchModel(),[('image/png','fake')])
        self.assertEqual(result['attempts'],3);self.assertEqual(result['vision']['correct'],8)
        self.assertEqual(vision_score(TRUTH),8)
        self.assertIn('2/2',report([result]))
        failed=evaluate(candidate,BenchModel(fail=True),[])
        self.assertEqual(failed['vision']['status'],'failed');self.assertIn('failed',report([failed]))
        candidate['vision']=False;result=evaluate(candidate,BenchModel(),[])
        self.assertEqual(result['attempts'],2);self.assertEqual(result['vision']['status'],'unsupported')
        self.assertIn('Skipped',report([{**candidate,'skip':'No free route.'}]))

    def test_cli_checkpoint_resume_missing_keys_and_input_changes(self):
        from war_content.benchmark import main
        class Client(BenchModel):
            def __init__(self,*args):super().__init__()
        with TemporaryDirectory() as tmp:
            root=Path(tmp);probes=root/'probes';probes.mkdir()
            for name in ('control.png','problem.png'):(probes/name).write_bytes(b'image-fixture')
            env=root/'env';env.write_text('GEMINI_API_KEY=fake\n',encoding='utf-8')
            args=['--output',str(root/'results'),'--probes',str(probes),'--env-file',str(env)]
            with patch.dict('os.environ',{'GEMINI_API_KEY':'fake','GROQ_API_KEY':'','OPENROUTER_API_KEY':''}),patch('war_content.benchmark.request_json',return_value={'data':[]}),patch('war_content.benchmark.LanguageModel',Client) as client,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args),0)
                first=json.loads((root/'results/results.json').read_text())
                self.assertEqual(main(args+['--resume']),0)
                second=json.loads((root/'results/results.json').read_text())
                self.assertEqual(first['results'],second['results'])
                (probes/'control.png').write_bytes(b'changed')
                with self.assertRaises(ValueError):main(args+['--resume'])
