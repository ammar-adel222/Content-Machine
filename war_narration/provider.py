"""Single-speaker REST adapter; transcript and style use distinct API fields."""
import base64
import binascii
from war_research.providers import ProviderError, request_json


class SpeechQuotaError(ProviderError):pass


class GeminiSpeech:
    def __init__(self,key,transport=None):
        if not key:raise ValueError('GEMINI_API_KEY is required for uncached narration.')
        self.key=key
        # No hidden retry: each submitted TTS request gets its own reservation.
        self.transport=transport or (lambda *args:request_json(*args,retries=0))

    def synthesize(self,text,direction,model,voice):
        try:return self._synthesize(text,direction,model,voice)
        except ProviderError as error:
            if str(error)=='Provider HTTP 429.':raise SpeechQuotaError('Gemini TTS quota reached; wait for provider quota reset, then resume.') from None
            raise

    def _synthesize(self,text,direction,model,voice):
        result=self.transport('https://generativelanguage.googleapis.com/v1beta/interactions',{
            'model':model,'store':False,
            'input':[{'type':'user_input','content':[{'type':'text','text':text,
                'annotations':[{'type':'speech_metadata','style':direction}]}]}],
            'response_format':{'type':'audio','mime_type':'audio/wav','sample_rate':24000},
            'generation_config':{'speech_config':[{'voice':voice}]}},
            {'x-goog-api-key':self.key})
        try:
            blocks=[part for step in result.get('steps',[]) if step.get('type')=='model_output'
                    for part in step.get('content',[]) if part.get('type')=='audio']
        except (TypeError,AttributeError):raise ProviderError('TTS returned an invalid response structure.') from None
        if result.get('status')!='completed' or len(blocks)!=1:
            raise ProviderError('TTS did not return one completed audio clip.')
        block=blocks[0]
        if block.get('mime_type','audio/wav')!='audio/wav':raise ProviderError('TTS returned an unsupported audio format.')
        encoded=block.get('data','')
        if not isinstance(encoded,str) or len(encoded)>8_000_000:raise ProviderError('TTS audio payload is invalid or too large.')
        try:return base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):raise ProviderError('TTS returned invalid audio encoding.') from None
