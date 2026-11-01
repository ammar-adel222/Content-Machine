from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from war_narration.agent import generate
from war_narration.words import WordCue,estimate_words,align_words,validate_words
from .director_helpers import inputs
from .test_narration import Speech


class WordCueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        _,script=inputs()
        self.voice=generate(script,self.root/'voice',self.root/'cache',lambda:Speech(1))
        self.local=estimate_words(self.voice)

    def test_local_estimates_preserve_script_and_measured_phrase_bounds(self):
        self.assertEqual(self.local.basis,'local_estimate')
        self.assertEqual(validate_words(self.local,self.voice),self.local)
        for clip in self.voice.clips:
            words=self.local.phrases[clip.phrase_id]
            self.assertEqual([w.text for w in words],clip.text.split())
            self.assertGreaterEqual(words[0].start,clip.start_frame/24000)
            self.assertLessEqual(words[-1].end,(clip.start_frame+clip.frames)/24000)

    def observed(self):
        return [{'word':w.text,'start':w.start,'end':w.end} for words in self.local.phrases.values() for w in words]

    def test_imported_timestamps_match_exact_script_and_preserve_original_spelling(self):
        observed=self.observed();observed[0]['word']='THE'
        words=align_words(self.voice,observed)
        self.assertEqual(words.basis,'asr_word');self.assertEqual(words.matched_fraction,1)
        self.assertEqual(words.phrases,self.local.phrases)
        observed[3]['word']='uncertain_name'
        repaired=align_words(self.voice,observed)
        self.assertEqual([w.text for w in repaired.phrases[self.voice.clips[0].phrase_id]],self.voice.clips[0].text.split())

    def test_stale_or_modified_cues_are_rejected(self):
        for field,value in [('source_sha256','0'*64),('script_sha256','0'*64),('duration',149)]:
            wrong=self.local.model_copy(update={field:value})
            with self.assertRaises(ValueError):validate_words(wrong,self.voice)
        wrong=self.local.model_copy(deep=True);wrong.phrases.pop(self.voice.clips[0].phrase_id)
        with self.assertRaises(ValueError):validate_words(wrong,self.voice)
        wrong=self.local.model_copy(deep=True);wrong.phrases[self.voice.clips[0].phrase_id][0].text='Changed'
        with self.assertRaises(ValueError):validate_words(wrong,self.voice)
        wrong=self.local.model_copy(deep=True);wrong.phrases[self.voice.clips[0].phrase_id][0].start=100
        with self.assertRaises(ValueError):validate_words(wrong,self.voice)

    def test_bad_or_unrelated_transcription_is_rejected(self):
        with self.assertRaises(ValueError):align_words(self.voice,[])
        with self.assertRaises(ValueError):align_words(self.voice,[{'word':'unrelated','start':0,'end':1}])
        with self.assertRaises(ValueError):align_words(self.voice,list(reversed(self.observed())))
        wrong=self.observed();wrong[-1]['end']=149
        with self.assertRaises(ValueError):align_words(self.voice,wrong)
        with self.assertRaises(ValueError):WordCue(text='Bad',start=1,end=.5)

    def test_small_asr_timestamp_jitter_keeps_script_order(self):
        observed=self.observed();observed[1]['start']=max(0,observed[0]['start']-.1)
        words=align_words(self.voice,observed)
        self.assertEqual(validate_words(words,self.voice),words)
