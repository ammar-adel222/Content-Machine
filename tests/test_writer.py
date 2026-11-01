import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError

from war_research.providers import ProviderError
from war_writer.__main__ import main
from war_writer.agent import WritingAgent, WritingError, check_draft, fingerprint, numbers, timing
from war_writer.models import Draft, Phrase, Pronunciation, Review, SceneEdit, Script, WritingRequest
from war_writer.storage import markdown, save, tts_plan
from .writer_helpers import WriterModel, dossier, draft


class WriterModelTests(unittest.TestCase):
    def test_request_defaults_and_boundaries(self):
        self.assertIsNone(WritingRequest().target_seconds)
        for params in ({"target_seconds": 59}, {"target_seconds": 151}, {"max_model_calls": 0},
                       {"scene_id": "s1"}, {"extra": True}):
            with self.subTest(params=params), self.assertRaises(ValidationError):
                WritingRequest(**params)

    def test_phrase_pause_and_pace_limits(self):
        for params in ({"pause_after_ms": -1}, {"pause_after_ms": 2001}, {"pace": "shouting"}):
            with self.subTest(params=params), self.assertRaises(ValidationError):
                Phrase(**{**dict(text="Say this naturally.", pace="normal"), **params})

    def test_scene_count_and_spoken_length(self):
        d = draft().model_dump()
        d["scenes"] = d["scenes"][:2]
        with self.assertRaises(ValidationError):
            Draft(**d)
        with self.assertRaises(ValidationError):
            Phrase(text="x" * 451, pace="normal")


class WriterCheckTests(unittest.TestCase):
    def setUp(self):
        self.dossier = dossier()

    def test_valid_draft_and_estimate(self):
        self.assertEqual(check_draft(draft(), self.dossier, 105), [])
        count, seconds = timing(draft())
        self.assertGreater(count, 200)
        self.assertTrue(89.25 <= seconds <= 120.75)

    def test_weekday_weather_setup_cannot_evade_the_date_opening_check(self):
        value=draft();value.scenes[0].phrases[0].text='On a cold Monday morning, December second, the defenders waited.'
        self.assertTrue(any('before introducing dates' in issue for issue in check_draft(value,self.dossier,105)))

    def test_long_hook_and_padded_pauses_are_rejected(self):
        value=draft();value.scenes[0].phrases[0].text=' '.join(['word']*20)+'.'
        value.scenes[1].phrases[0].pause_after_ms=1500
        issues=check_draft(value,self.dossier,105)
        self.assertTrue(any('16 words' in issue for issue in issues))
        self.assertTrue(any('500ms' in issue for issue in issues))

    def test_pace_and_pause_affect_estimated_time(self):
        normal = draft()
        slow = normal.model_copy(deep=True)
        slow.scenes[0].phrases[0].pace = "measured"
        self.assertGreater(timing(slow)[1], timing(normal)[1])
        slow.scenes[0].phrases[0].pause_after_ms += 1000
        self.assertGreater(timing(slow)[1], timing(normal)[1] + 1)

    def test_numbers_grouping(self):
        self.assertEqual(numbers("1,800 men in 1805; 2.5 hours"), {"1800", "1805", "2.5"})

    def test_spelled_numbers_and_years(self):
        self.assertEqual(numbers("nineteen eighty-two; eight thousand miles; one hundred twenty-seven ships"),
                         {"1982", "8000", "127"})
        self.assertEqual(numbers("twenty-six men; two hundred and fifty-five; one side"), {"26", "255"})
        self.assertEqual(numbers("one million and six hundred thousand; nineteen hundred; and"), {"1600000", "1900"})

    def test_spoken_clocks_match_cited_times_without_becoming_years(self):
        self.assertEqual(numbers('four thirty p m'),numbers('4:30 p.m.'))
        self.assertEqual(numbers('six a m'),numbers('06:00'))
        self.assertEqual(numbers('twelve a.m.; twelve p.m.; nine oh five am'),{'clock:00:00','clock:12:00','clock:09:05'})
        self.assertEqual(numbers('nine thirty-five P.M.'),{'clock:21:35'})
        self.assertEqual(numbers('nineteen eighty-two'),{'1982'})

    def test_clock_mismatch_cannot_be_accepted_as_approximate_troop_count(self):
        self.dossier.findings.claims[4].statement+=' The withdrawal began at 4:30 p.m. with 430 soldiers.'
        d=draft();d.scenes[0].phrases[0].text+=' Around four thirty p m they withdrew.'
        self.assertFalse(any('numeric' in i for i in check_draft(d,self.dossier,105)))
        d.scenes[0].phrases[0].text=d.scenes[0].phrases[0].text.replace('four thirty','four forty')
        self.assertTrue(any('numeric' in i for i in check_draft(d,self.dossier,105)))

    def test_spelled_unsupported_distance_is_flagged(self):
        d = draft()
        d.scenes[0].phrases[0].text += " They sailed eight thousand miles."
        self.assertTrue(any("numeric" in i for i in check_draft(d, self.dossier, 105)))

    def test_explicit_approximation_allows_small_rounding(self):
        self.dossier.findings.claims[4].statement += " The force contained 127 ships."
        d = draft()
        d.scenes[0].phrases[0].text += " About one hundred thirty ships."
        self.assertFalse(any("numeric" in i for i in check_draft(d, self.dossier, 105)))

    def test_approximation_cannot_change_a_date(self):
        self.dossier.findings.claims[1].statement += " The invasion happened in 1982."
        d = draft()
        d.scenes[0].phrases[0].text += " About 127 ships fought in 2000."
        self.assertTrue(any("numeric" in i for i in check_draft(d, self.dossier, 105)))

    def test_duplicate_scenes_and_story_structure(self):
        d = draft()
        d.scenes[1].id = "s1"
        d.scenes[0].role = "context"
        d.scenes[-1].role = "maneuver"
        issues = check_draft(d, self.dossier, 105)
        self.assertTrue(any("unique" in i for i in issues))
        self.assertTrue(any("hook" in i for i in issues))

    def test_date_first_textbook_opening_is_flagged(self):
        d = draft()
        d.scenes[0].phrases[0].text = "In April 1982, the invasion began."
        self.assertTrue(any("dilemma" in i for i in check_draft(d, self.dossier, 105)))

    def test_unknown_citations_and_unsupported_digits(self):
        d = draft()
        d.scenes[0].claim_ids = ["invented"]
        d.scenes[0].phrases[0].text += " There were 90000 troops."
        issues = check_draft(d, self.dossier, 105)
        self.assertTrue(any("unknown research" in i for i in issues))
        self.assertTrue(any("numeric figures" in i for i in issues))

    def test_missing_essential_claims(self):
        d = draft()
        for s in d.scenes:
            s.claim_ids = ["C1"]
        self.assertTrue(any("essential" in i for i in check_draft(d, self.dossier, 105)))

    def test_uncertainty_must_be_spoken(self):
        self.dossier.findings.claims[0].status = "estimate"
        d = draft()
        self.assertTrue(any("uncertainty" in i for i in check_draft(d, self.dossier, 105)))
        for scene in d.scenes:
            scene.phrases[0].text = "Accounts suggest this. " + scene.phrases[0].text
        self.assertFalse(any("uncertainty" in i for i in check_draft(d, self.dossier, 105)))

    def test_stage_directions_are_not_spoken(self):
        for tag in ("[pause]", "<break time='1s'/>"):
            d = draft()
            d.scenes[0].phrases[0].text += tag
            with self.subTest(tag=tag):
                self.assertTrue(any("markup" in i for i in check_draft(d, self.dossier, 105)))

    def test_emphasis_and_glossary_must_match_speech(self):
        d = draft()
        d.scenes[0].phrases[0].emphasis = ["This phrase is absent"]
        d.pronunciations = [Pronunciation(term="Napoleon", say_as="na-POH-lee-un")]
        issues = check_draft(d, self.dossier, 105)
        self.assertTrue(any("emphasis" in i for i in issues))
        self.assertTrue(any("glossary" in i for i in issues))

    def test_emphasis_cannot_match_only_part_of_a_word(self):
        d = draft()
        d.scenes[0].phrases[0].emphasis = ["arm"]
        self.assertTrue(any("emphasis" in i for i in check_draft(d, self.dossier, 105)))

    def test_spoken_glossary_term_is_allowed(self):
        d = draft()
        d.pronunciations = [Pronunciation(term="valley", say_as="VAL-ee")]
        self.assertEqual(check_draft(d, self.dossier, 105), [])

    def test_duration_outside_target_is_flagged(self):
        self.assertTrue(any("duration" in i for i in check_draft(draft(), self.dossier, 150)))


class WriterAgentTests(unittest.TestCase):
    def setUp(self):
        self.dossier, self.model = dossier(), WriterModel()
        self.agent = WritingAgent(self.model)

    def test_generate_and_review(self):
        result = self.agent.write(self.dossier)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(result.dossier_sha256, fingerprint(self.dossier))
        self.assertEqual(result.changed_scene_ids, ["s1", "s2", "s3", "s4"])
        self.assertEqual(len(result.claims), 8)

    def test_war_scope_and_target_reach_prompt(self):
        self.dossier.selected.scope = "war"
        self.agent.write(self.dossier)
        self.assertIn('"scope": "war"', self.model.prompts[0])
        self.assertIn("Target 105 seconds", self.model.prompts[0])

    def test_incomplete_research_refused_before_calls(self):
        self.dossier.readiness = "incomplete"
        with self.assertRaises(WritingError):
            self.agent.write(self.dossier)
        self.assertEqual(self.model.prompts, [])

    def test_blocking_research_refused_even_if_status_edited(self):
        self.dossier.findings.blocking_gaps = ["Missing terrain"]
        with self.assertRaises(WritingError):
            self.agent.write(self.dossier)

    def test_invalid_evidence_refused(self):
        self.dossier.findings.claims[0].evidence[0].quote = "This was not in the source material."
        with self.assertRaisesRegex(WritingError, "evidence"):
            self.agent.write(self.dossier)

    def test_one_local_repair(self):
        bad = draft()
        bad.scenes[0].claim_ids.append("C999")
        self.model.replies = [bad, draft(), Review(issues=[])]
        result = self.agent.write(self.dossier)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.model_calls, 3)

    def test_one_semantic_repair_and_review(self):
        self.model.replies = [draft(), Review(issues=["Make the causal explanation clearer."]), draft(), Review(issues=[])]
        self.assertEqual(self.agent.write(self.dossier).model_calls, 4)

    def test_unresolved_issues_saved_as_needs_revision(self):
        self.model.replies = [draft(), Review(issues=["Unsupported interpretation."]), draft(),
                              Review(issues=["Still unsupported."])]
        result = self.agent.write(self.dossier)
        self.assertEqual(result.status, "needs_revision")
        self.assertIn("Still unsupported.", result.issues)

    def test_budget_one_cannot_skip_review(self):
        result = self.agent.write(self.dossier, WritingRequest(max_model_calls=1))
        self.assertEqual(result.status, "needs_revision")
        self.assertEqual(result.model_calls, 1)

    def test_failed_review_returns_partial_script(self):
        self.model.replies = [draft(), ProviderError("unavailable")]
        result = self.agent.write(self.dossier, WritingRequest(max_model_calls=2))
        self.assertEqual(result.status, "needs_revision")

    def test_failed_repair_preserves_previous_draft(self):
        bad = draft()
        bad.scenes[0].claim_ids = ["bad"]
        self.model.replies = [bad, ProviderError("unavailable")]
        result = self.agent.write(self.dossier)
        self.assertEqual(result.draft, bad)
        self.assertEqual(result.status, "needs_revision")

    def test_initial_provider_failure_is_reported(self):
        self.model.replies = [ProviderError("unavailable"), ProviderError("unavailable")]
        with self.assertRaises(ProviderError):
            self.agent.write(self.dossier)

    def test_initial_schema_failure_can_retry_once(self):
        self.model.replies = [ProviderError("Invalid structured output"), draft(), Review(issues=[])]
        result = self.agent.write(self.dossier)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.model_calls, 3)

    def test_targeted_revision_preserves_other_scenes_and_metadata(self):
        old = self.agent.write(self.dossier)
        changed = old.draft.scenes[1].model_copy(deep=True)
        changed.delivery_notes = "Speak calmly and emphasize the crossing rather than the army."
        self.model.replies = [SceneEdit(scene=changed), Review(issues=[])]
        new = self.agent.write(self.dossier, WritingRequest(scene_id="s2", notes="Calmer delivery."), old)
        self.assertEqual(new.changed_scene_ids, ["s2"])
        self.assertEqual(new.draft.scenes[0], old.draft.scenes[0])
        self.assertEqual(new.draft.title, old.draft.title)
        self.assertEqual(new.parent_script_sha256, fingerprint(old))
        self.assertNotEqual(new.draft.scenes[1], old.draft.scenes[1])

    def test_wrong_target_scene_id_is_not_applied(self):
        old = self.agent.write(self.dossier)
        wrong = SceneEdit(scene=old.draft.scenes[0])
        self.model.replies = [wrong, wrong]
        new = self.agent.write(self.dossier, WritingRequest(scene_id="s2", notes="Change this."), old)
        self.assertEqual(new.draft, old.draft)
        self.assertEqual(new.status, "needs_revision")

    def test_missing_target_scene_or_previous_refused(self):
        for previous in (None, self.agent.write(self.dossier)):
            with self.subTest(previous=previous is None), self.assertRaises(WritingError):
                self.agent.write(self.dossier, WritingRequest(scene_id="s999", notes="Edit."), previous)

    def test_changed_dossier_rejects_stale_revision(self):
        old = self.agent.write(self.dossier)
        self.dossier.selected.angle = "A newly researched angle that changes the story"
        with self.assertRaisesRegex(WritingError, "different research"):
            self.agent.write(self.dossier, previous=old)

    def test_whole_script_revision_keeps_parent_link(self):
        old = self.agent.write(self.dossier)
        new = self.agent.write(self.dossier, WritingRequest(notes="Improve the opening."), old)
        self.assertEqual(new.parent_script_sha256, fingerprint(old))
        self.assertIn("PREVIOUS DRAFT", self.model.prompts[-2])


class WriterStorageTests(unittest.TestCase):
    def setUp(self):
        self.script = WritingAgent(WriterModel()).write(dossier())

    def test_tts_keeps_words_and_style_separate(self):
        plan = tts_plan(self.script)
        chunk = plan["chunks"][0]
        self.assertEqual(chunk["text"], self.script.draft.scenes[0].phrases[0].text)
        self.assertIn("Tone:", chunk["direction"])
        self.assertEqual(chunk["pause_after_ms"], 250)
        self.assertEqual(chunk["id"], "s1.p1")
        self.assertEqual(plan["status"], "ready")

    def test_save_roundtrip_and_versioning(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = save(self.script, root), save(self.script, root)
            self.assertNotEqual(first, second)
            loaded = Script.model_validate_json((first / "script.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded, self.script)
            self.assertEqual(json.loads((first / "tts_plan.json").read_text())["topic"], self.script.topic)
            self.assertTrue((first / "script.md").exists())

    def test_markdown_contains_directions_and_provenance(self):
        self.script.draft.pronunciations = [Pronunciation(term="valley", say_as="VAL-ee")]
        report = markdown(self.script)
        for phrase in ("Voice direction", "pause afterward", "VAL-ee", "SHA-256", "Research claims"):
            self.assertIn(phrase, report)

    def test_slug_stays_inside_output(self):
        with TemporaryDirectory() as tmp:
            self.script.topic = "../../危险"
            self.assertEqual(save(self.script, Path(tmp)).parent, Path(tmp))


class WriterCliTests(unittest.TestCase):
    def invoke(self, root, extras=None, model=None):
        path = root / "dossier.json"
        if not path.exists():
            path.write_text(dossier().model_dump_json(), encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), \
             patch("war_writer.__main__.LanguageModel", return_value=model or WriterModel()), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = main([str(path), "--output", str(root / "writing"), *(extras or [])])
        return code, output.getvalue()

    def test_cli_initial_script(self):
        with TemporaryDirectory() as tmp:
            code, text = self.invoke(Path(tmp))
            self.assertEqual(code, 0)
            self.assertIn("Script ready", text)

    def test_cli_needs_revision_exit_code(self):
        with TemporaryDirectory() as tmp:
            code, _ = self.invoke(Path(tmp), ["--max-model-calls", "1"])
            self.assertEqual(code, 2)

    def test_cli_invalid_request(self):
        with TemporaryDirectory() as tmp:
            code, text = self.invoke(Path(tmp), ["--target-seconds", "151"])
            self.assertEqual(code, 1)
            self.assertIn("Invalid", text)

    def test_cli_provider_failure(self):
        with TemporaryDirectory() as tmp:
            code, _ = self.invoke(Path(tmp), model=WriterModel([ProviderError("unavailable"), ProviderError("unavailable")]))
            self.assertEqual(code, 1)

    def test_cli_targeted_revision(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.invoke(root)
            previous = next((root / "writing").glob("*/script.json"))
            old = Script.model_validate_json(previous.read_text())
            model = WriterModel([SceneEdit(scene=old.draft.scenes[0]), Review(issues=[])])
            code, _ = self.invoke(root, ["--previous", str(previous), "--scene", "s1", "--notes", "Keep a calm tone."], model)
            self.assertEqual(code, 0)

    def test_cli_credentials_and_model_override(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "dossier.json"
            path.write_text(dossier().model_dump_json())
            env = root / ".env"
            env.write_text("OPENROUTER_API_KEY=secret\nGEMINI_API_KEY=other\n")
            with patch.dict(os.environ, {}, clear=True), \
                 patch("war_writer.__main__.LanguageModel", return_value=WriterModel()) as factory, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(path), "--env-file", str(env), "--provider", "openrouter", "--model", "chosen:free",
                                       "--fallback", "gemini", "--output", str(root / "out")]), 0)
                self.assertEqual(factory.call_args.args[0], [("openrouter", "chosen:free", "secret"),
                                                             ("gemini", "gemini-3.8-flash", "other"),
                                                             ("gemini", "gemini-3.5-flash-lite", "other")])


if __name__ == "__main__":
    unittest.main()
