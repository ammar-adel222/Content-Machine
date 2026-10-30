import unittest
from unittest.mock import patch
from war_research.providers import LanguageModel, ProviderError, model_routes
from war_writer.agent import WritingAgent
from war_writer.models import Draft
from .writer_helpers import dossier, draft


class ModelPolicyTests(unittest.TestCase):
    def test_defaults_explicit_models_and_provider_order(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'g','GROQ_API_KEY':'q'},clear=True):
            self.assertEqual(model_routes(),[('gemini','gemini-3.8-flash','g'),('gemini','gemini-3.5-flash-lite','g')])
            self.assertEqual(len(model_routes(fallback='groq')),3)
            self.assertEqual(len(model_routes(model='gemini-3.5-flash-lite')),1)
            self.assertEqual(len(model_routes(fallback='gemini')),2)
            self.assertEqual(model_routes('groq','custom'),[('groq','custom','q')])
        with patch.dict('os.environ',{'GEMINI_MODEL':'custom-gemini'},clear=True):
            self.assertEqual(model_routes()[0][1],'custom-gemini')

    def test_writer_finishes_within_budget_when_stronger_model_unavailable(self):
        requests=[]
        def transport(url,payload,headers,**kwargs):
            requests.append(url)
            if 'gemini-3.8-flash' in url:raise ProviderError('Provider HTTP 503.')
            schema=payload['generationConfig']['responseJsonSchema']
            response=draft().model_dump_json() if 'scenes' in schema['properties'] else '{"issues":[]}'
            return {'candidates':[{'content':{'parts':[{'text':response}]}}]}
        with patch.dict('os.environ',{'GEMINI_API_KEY':'fake'},clear=True):
            model=LanguageModel(model_routes(),transport)
            result=WritingAgent(model).write(dossier())
        self.assertEqual(result.status,'ready');self.assertEqual(result.model_calls,4)
        self.assertEqual(result.models_used,['gemini:gemini-3.5-flash-lite'])
        self.assertEqual(len(requests),4)
