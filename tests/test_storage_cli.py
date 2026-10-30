import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from war_research.__main__ import main, parser
from war_research.agent import ResearchAgent
from war_research.models import Discovery, Dossier, ResearchRequest
from war_research.storage import Cache, markdown, past_topics, save
from .helpers import FakeModel, FakeWeb, candidate, findings


class StorageTests(unittest.TestCase):
    def setUp(self):
        agent = ResearchAgent(FakeWeb(), FakeModel())
        self.discovery = agent.discover(ResearchRequest())
        self.dossier = agent.research(self.discovery)

    def test_unique_versioned_outputs_round_trip(self):
        with TemporaryDirectory() as tmp:
            first, second = [save(self.dossier, Path(tmp)) for _ in range(2)]
            self.assertNotEqual(first, second)
            loaded = Dossier.model_validate_json((first / "dossier.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded, self.dossier)
            self.assertTrue((first / "report.md").exists())

    def test_discovery_can_be_loaded_independently(self):
        with TemporaryDirectory() as tmp:
            directory = save(self.discovery, Path(tmp))
            loaded = Discovery.model_validate_json((directory / "discovery.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded, self.discovery)
            self.assertFalse((directory / "report.md").exists())

    def test_markdown_includes_director_writer_and_evidence(self):
        report = markdown(self.dossier)
        for phrase in ("Terrain for the director", "Event sequence", "Writer handoff", "Evidence excerpts",
                       "Information cutoff", "https://museum.example", "Reason:", "Consequence:"):
            self.assertIn(phrase, report)

    def test_markdown_empty_sections(self):
        d = self.dossier.model_copy(deep=True)
        d.findings.claims, d.findings.terrain, d.findings.events = [], [], []
        d.findings.essential_claim_ids, d.findings.optional_claim_ids = [], []
        self.assertIn("None", markdown(d))

    def test_markdown_preserves_alternative_topics(self):
        self.dossier.alternatives = [candidate("Alternative Battle")]
        self.assertIn("Alternative Battle", markdown(self.dossier))

    def test_history_only_ready_and_skips_corrupt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(self.dossier, root)
            incomplete = self.dossier.model_copy(update={"readiness": "incomplete"})
            incomplete.selected = incomplete.selected.model_copy(update={"topic": "Incomplete Battle"})
            save(incomplete, root)
            corrupt = root / "corrupt"
            corrupt.mkdir()
            (corrupt / "dossier.json").write_text("not json")
            self.assertEqual(past_topics(root), ["Example Battle"])

    def test_slug_cannot_escape_output(self):
        with TemporaryDirectory() as tmp:
            self.dossier.selected.topic = "../../危险/CON"
            path = save(self.dossier, Path(tmp))
            self.assertEqual(path.parent, Path(tmp))

    def test_cache_hits_misses_expiry_and_corruption(self):
        with TemporaryDirectory() as tmp:
            cache, call = Cache(Path(tmp)), Mock(return_value={"public": "data"})
            self.assertEqual(cache.get_or_call("search", "topic", call), {"public": "data"})
            cache.get_or_call("search", "topic", call)
            self.assertEqual(call.call_count, 1)
            path = next(Path(tmp).glob("*.json"))
            os.utime(path, (0, 0))
            cache.get_or_call("search", "topic", call)
            self.assertEqual(call.call_count, 2)
            path.write_text("broken")
            cache.get_or_call("search", "topic", call)
            self.assertEqual(call.call_count, 3)

    def test_cache_does_not_save_failures(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                Cache(Path(tmp)).get_or_call("search", "topic", Mock(side_effect=ValueError("failed")))
            self.assertEqual(list(Path(tmp).iterdir()), [])


class CliTests(unittest.TestCase):
    def invoke(self, args, **kwargs):
        with patch.dict(os.environ, {}, clear=True), patch("war_research.__main__.Web", return_value=FakeWeb()), \
             patch("war_research.__main__.LanguageModel", return_value=FakeModel()), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = main(args, **kwargs)
        return code, stdout.getvalue()

    def test_specific_cli_saves_both_stages(self):
        with TemporaryDirectory() as tmp:
            code, text = self.invoke(["--topic", "Example Battle", "--output", tmp, "--no-cache"])
            self.assertEqual(code, 0)
            self.assertIn("Research ready", text)
            self.assertEqual(len(list(Path(tmp).glob("*/discovery.json"))), 1)
            self.assertEqual(len(list(Path(tmp).glob("*/report.md"))), 1)

    def test_discover_then_resume(self):
        with TemporaryDirectory() as tmp:
            code, _ = self.invoke(["--output", tmp, "--discover-only"])
            self.assertEqual(code, 0)

    def test_resume_allows_explicit_budget_override(self):
        with TemporaryDirectory() as tmp:
            self.invoke(["--output", tmp, "--discover-only", "--max-searches", "1"])
            discovery = next(Path(tmp).glob("*/discovery.json"))
            code, _ = self.invoke(["--selection-file", str(discovery), "--output", tmp, "--max-searches", "5"])
            self.assertEqual(code, 0)
            dossier = json.loads(next(Path(tmp).glob("*/dossier.json")).read_text())
            self.assertEqual(dossier["request"]["max_searches"], 5)

    def test_incomplete_cli_has_distinct_exit_code(self):
        from war_research.models import Selection
        incomplete = findings()
        incomplete.gaps = ["More evidence needed."]
        incomplete.blocking_gaps = incomplete.gaps.copy()
        model = FakeModel([Selection(candidates=[candidate()]), incomplete])
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
             patch("war_research.__main__.Web", return_value=FakeWeb()), \
             patch("war_research.__main__.LanguageModel", return_value=model), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--output", tmp, "--max-model-calls", "2"]), 2)
            discovery = next(Path(tmp).glob("*/discovery.json"))
            code, _ = self.invoke(["--selection-file", str(discovery), "--output", tmp])
            self.assertEqual(code, 0)

    def test_direction_and_date(self):
        with TemporaryDirectory() as tmp:
            code, _ = self.invoke(["--direction", "ancient battles", "--as-of", "2026-10-30", "--output", tmp])
            self.assertEqual(code, 0)

    def test_invalid_request_is_clean_error(self):
        with TemporaryDirectory() as tmp:
            code, text = self.invoke(["--target-seconds", "999", "--output", tmp])
            self.assertEqual(code, 1)
            self.assertIn("Invalid structured input", text)

    def test_missing_selection_file_is_error(self):
        code, _ = self.invoke(["--selection-file", "missing-discovery.json"])
        self.assertEqual(code, 1)

    def test_provider_models_and_env_configuration(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
             patch("war_research.__main__.Web", return_value=FakeWeb()) as web, \
             patch("war_research.__main__.LanguageModel", return_value=FakeModel()) as model, \
             contextlib.redirect_stdout(io.StringIO()):
            env = Path(tmp) / ".env"
            env.write_text("TAVILY_API_KEY=search-secret\nGEMINI_API_KEY=gemini-secret\nGROQ_API_KEY=groq-secret\nGROQ_MODEL=custom-model\n")
            self.assertEqual(main(["--env-file", str(env), "--provider", "groq", "--fallback", "gemini",
                                   "--model", "override", "--discover-only", "--output", tmp]), 0)
            web.assert_called_once_with("search-secret")
            self.assertEqual(model.call_args.args[0], [("groq", "override", "groq-secret"),
                                                       ("gemini", "gemini-3.8-flash", "gemini-secret"),
                                                       ("gemini", "gemini-3.5-flash-lite", "gemini-secret")])
            self.assertNotIn("secret", next(Path(tmp).glob("*/discovery.json")).read_text())

    def test_actual_missing_credentials_fail_without_network(self):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(["--env-file", "missing.env"]), 1)
        self.assertIn("TAVILY_API_KEY", stdout.getvalue())

    def test_topic_modes_are_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(["--topic", "one", "--direction", "two"])


if __name__ == "__main__":
    unittest.main()
