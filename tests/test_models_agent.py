import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from pydantic import ValidationError

from war_research.agent import ResearchAgent, ResearchError, canonical_url, excerpt, normalized, prune_unsupported, validate_evidence
from war_research.models import ResearchRequest, Selection, Source
from war_research.storage import Cache
from .helpers import FakeModel, FakeWeb, TEXT, candidate, findings


class ModelTests(unittest.TestCase):
    def test_request_defaults(self):
        r = ResearchRequest()
        self.assertEqual((r.mode, r.target_seconds), ("auto", 105))

    def test_modes_require_topic(self):
        for mode in ("specific", "direction"):
            with self.subTest(mode=mode), self.assertRaises(ValidationError):
                ResearchRequest(mode=mode, topic=" ")

    def test_duration_and_budget_boundaries(self):
        for value in (59, 151):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ResearchRequest(target_seconds=value)
        for name in ("max_searches", "max_model_calls"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                ResearchRequest(**{name: 0})
        self.assertEqual(ResearchRequest(max_extract_urls=0).max_extract_urls, 0)

    def test_unknown_fields_and_scope_rejected(self):
        for args in ({"scope": "campaign"}, {"secret_key": "nope"}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                ResearchRequest(**args)

    def test_era_and_unbounded_recommendation_rejected(self):
        for key, value in (("era", "fiction"), ("recommended_seconds", 200)):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                type(findings())(**{**findings().model_dump(), key: value})

    def test_scores_are_computed(self):
        self.assertEqual(candidate().scores.total, 20)

    def test_canonical_url_and_topic_normalization(self):
        self.assertEqual(canonical_url("HTTPS://Museum.Example/battle/#section"), "https://museum.example/battle")
        self.assertEqual(normalized("Battle-of EXAMPLE!"), normalized("battle of example"))

    def test_excerpt_selects_relevant_passages_within_budget(self):
        text = "Page header.\n\n" + "Unrelated introduction. " * 100 + "\n\nTroop strength was disputed.\n\nA river restricted the advance."
        result = excerpt(text)
        self.assertIn("Troop strength", result)
        self.assertIn("river restricted", result)
        self.assertLessEqual(len(result), 1600)
        self.assertEqual(excerpt(""), "")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.sources = [Source(id=f"S{i}", url=f"https://source{i}.example", title="Evidence", text=TEXT)
                        for i in (1, 2)]

    def test_supported_quotes(self):
        validate_evidence(findings(), self.sources)

    def test_whitespace_variation_allowed(self):
        f = findings()
        f.claims[0].evidence[0].quote = f.claims[0].evidence[0].quote.replace(" ", "\n")
        validate_evidence(f, self.sources)

    def test_invented_quote_or_source_rejected(self):
        for field, value in (("quote", "An invented quotation with no source."), ("source_id", "S999"),
                             ("quote", "!!!!!!!!!!!!!!!!!")):
            f = findings()
            setattr(f.claims[0].evidence[0], field, value)
            with self.subTest(field=field, value=value), self.assertRaises(ResearchError):
                validate_evidence(f, self.sources)

    def test_duplicate_claim_ids_rejected(self):
        f = findings()
        f.claims[1].id = f.claims[0].id
        with self.assertRaises(ResearchError):
            validate_evidence(f, self.sources)

    def test_unknown_structured_references_rejected(self):
        for target in ("terrain", "events", "essential", "optional"):
            f = findings()
            if target in ("terrain", "events"):
                getattr(f, target)[0].claim_ids = ["C999"]
            else:
                setattr(f, f"{target}_claim_ids", ["C999"])
            with self.subTest(target=target), self.assertRaises(ResearchError):
                validate_evidence(f, self.sources)

    def test_overlapping_handoff_rejected(self):
        f = findings()
        f.optional_claim_ids.append("C1")
        with self.assertRaises(ResearchError):
            validate_evidence(f, self.sources)

    def test_duplicate_event_orders_rejected(self):
        f = findings()
        f.events.append(f.events[0].model_copy())
        with self.assertRaises(ResearchError):
            validate_evidence(f, self.sources)

    def test_pruning_removes_claims_and_dependent_visuals(self):
        f = findings()
        f.claims[5].evidence[0].quote = "This is an unsupported terrain description."
        cleaned = prune_unsupported(f, self.sources)
        self.assertNotIn("C6", [c.id for c in cleaned.claims])
        self.assertEqual(cleaned.terrain, [])
        self.assertNotIn("C6", cleaned.essential_claim_ids)
        self.assertTrue(cleaned.gaps)
        self.assertNotEqual(cleaned.summary, f.summary)
        validate_evidence(cleaned, self.sources)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.web, self.model = FakeWeb(), FakeModel()
        self.agent = ResearchAgent(self.web, self.model)

    def run_agent(self, **kwargs):
        discovery = self.agent.discover(ResearchRequest(**kwargs))
        return self.agent.research(discovery)

    def test_end_to_end_ready(self):
        result = self.run_agent()
        self.assertEqual(result.readiness, "ready")
        self.assertEqual(result.usage.model_calls, 2)
        self.assertEqual(result.usage.searches, 5)
        self.assertEqual(result.selected.topic, "Example Battle")
        self.assertTrue(result.selection_sources[0].id.startswith("D"))
        self.assertTrue(result.sources[0].id.startswith("S"))

    def test_specific_can_repeat_previously_covered_topic(self):
        result = self.run_agent(mode="specific", topic="Example Battle", excluded_topics=["Example Battle"])
        self.assertEqual(result.selected.topic, "Example Battle")

    def test_specific_cannot_silently_change_topic(self):
        with self.assertRaisesRegex(ResearchError, "matched"):
            self.run_agent(mode="specific", topic="Another Battle")

    def test_auto_excludes_previous_topics(self):
        with self.assertRaises(ResearchError):
            self.run_agent(excluded_topics=["Example Battle"])

    def test_rank_dedupe_and_scope_filter(self):
        self.model.replies = [Selection(candidates=[candidate("War", "war", 5),
                              candidate("Other Battle", score=2), candidate("Other Battle", score=4)])]
        discovery = self.agent.discover(ResearchRequest(scope="battle"))
        self.assertEqual(len(discovery.selection.candidates), 1)
        self.assertEqual(discovery.selection.candidates[0].topic, "Other Battle")

    def test_candidates_sorted_by_score(self):
        self.model.replies = [Selection(candidates=[candidate("Lower", score=1), candidate("Higher", score=5)])]
        self.assertEqual(self.agent.discover(ResearchRequest()).selection.candidates[0].topic, "Higher")

    def test_invented_candidate_citation_rejected(self):
        c = candidate()
        c.source_ids = ["D999"]
        self.model.replies = [Selection(candidates=[c])]
        with self.assertRaises(ResearchError):
            self.run_agent()

    def test_no_discovery_evidence_fails(self):
        self.web.fail_search = True
        with self.assertRaisesRegex(ResearchError, "No usable sources"):
            self.run_agent()

    def test_war_uses_strategic_queries(self):
        self.model.replies = [Selection(candidates=[candidate("Example War", "war")]), findings()]
        result = self.run_agent(mode="direction", topic="modern wars", scope="war")
        self.assertEqual(result.selected.scope, "war")
        self.assertTrue(any("fronts campaigns" in str(call) for call in self.web.calls))

    def test_ongoing_cutoff_preserved(self):
        f = findings()
        f.ongoing = True
        self.model.replies = [Selection(candidates=[candidate()]), f]
        result = self.run_agent(as_of="2026-10-30")
        self.assertEqual(str(result.request.as_of), "2026-10-30")
        self.assertTrue(result.findings.ongoing)
        self.assertIn("2026-10-30", self.model.prompts[-1])

    def test_missing_sections_make_specific_incomplete(self):
        f = findings()
        f.claims = [c for c in f.claims if c.section != "duration"]
        f.optional_claim_ids.remove("C3")
        self.model.replies = [Selection(candidates=[candidate()]), f]
        result = self.run_agent(mode="specific", topic="Example Battle", max_model_calls=2)
        self.assertEqual(result.readiness, "incomplete")
        self.assertIn("Missing evidence for duration.", result.findings.gaps)

    def test_missing_director_and_writer_data_flagged(self):
        f = findings()
        f.terrain, f.events, f.essential_claim_ids = [], [], []
        self.model.replies = [Selection(candidates=[candidate()]), f]
        result = self.run_agent(max_model_calls=2)
        self.assertEqual(result.readiness, "incomplete")
        self.assertEqual(len(result.findings.gaps), 3)

    def test_single_domain_is_not_corroboration(self):
        f = findings()
        for c in f.claims:
            c.evidence[0].source_id = "S1"
            c.evidence[0].passage_id = "S1:P1"
        self.model.replies = [Selection(candidates=[candidate()]), f]
        self.assertEqual(self.run_agent(max_model_calls=2).readiness, "incomplete")

    def test_one_evidence_repair(self):
        bad = findings()
        bad.claims[0].evidence[0].passage_id = "S999:P1"
        self.model.replies = [Selection(candidates=[candidate()]), bad, findings()]
        self.assertEqual(self.run_agent().usage.model_calls, 3)

    def test_model_quotes_are_replaced_by_original_passages(self):
        f = findings()
        f.claims[0].evidence[0].quote = "The model invented this quotation."
        self.model.replies = [Selection(candidates=[candidate()]), f]
        result = self.run_agent()
        self.assertEqual(result.findings.claims[0].evidence[0].quote, TEXT)

    def test_invented_passage_id_is_removed_after_failed_repair(self):
        bad = findings()
        bad.claims[0].evidence[0].passage_id = "P999"
        self.model.replies = [Selection(candidates=[candidate()]), bad, bad]
        result = self.run_agent(max_model_calls=3)
        self.assertEqual(result.readiness, "incomplete")
        self.assertNotIn("C1", [c.id for c in result.findings.claims])

    def test_invalid_repair_is_not_accepted(self):
        bad = findings()
        bad.claims[0].evidence[0].passage_id = "S999:P1"
        self.model.replies = [Selection(candidates=[candidate()]), bad, bad]
        result = self.run_agent(max_model_calls=3)
        self.assertEqual(result.readiness, "incomplete")
        self.assertNotIn("C1", [c.id for c in result.findings.claims])

    def test_model_budget_bounds_repair(self):
        bad = findings()
        bad.claims[0].evidence[0].passage_id = "S999:P1"
        self.model.replies = [Selection(candidates=[candidate()]), bad]
        result = self.run_agent(max_model_calls=2)
        self.assertEqual(result.usage.model_calls, 2)
        self.assertEqual(result.readiness, "incomplete")

    def test_search_and_extraction_budgets(self):
        f = findings()
        for claim in f.claims:
            claim.evidence[0].source_id = "S1"
            claim.evidence[0].passage_id = "S1:P1"
        self.model.replies = [Selection(candidates=[candidate()]), f]
        result = self.run_agent(max_searches=1, max_extract_urls=0)
        self.assertEqual(result.usage.searches, 1)
        self.assertEqual(result.usage.extracted_urls, 0)
        self.assertTrue(any("budget" in w for w in result.warnings))

    def test_extraction_failure_preserves_snippets(self):
        self.web.fail_extract = True
        result = self.run_agent()
        self.assertTrue(any("extraction failed" in w for w in result.warnings))
        self.assertFalse(result.sources[1].full_text)

    def test_partial_extraction_warns(self):
        self.web.extract = lambda urls: {}
        result = self.run_agent()
        self.assertTrue(any("could not be extracted" in w for w in result.warnings))

    def test_wikipedia_failure_uses_web(self):
        self.web.fail_wiki = True
        self.assertEqual(self.run_agent().readiness, "ready")

    def test_search_failure_during_research_warns(self):
        discovery = self.agent.discover(ResearchRequest())
        self.web.fail_search = True
        f = findings()
        for c in f.claims:
            c.evidence[0].source_id = "S1"
            c.evidence[0].passage_id = "S1:P1"
        self.model.replies = [f]
        result = self.agent.research(discovery)
        self.assertEqual(result.readiness, "incomplete")
        self.assertTrue(any("web search failed" in w for w in result.warnings))

    def test_empty_research_fails(self):
        discovery = self.agent.discover(ResearchRequest())
        self.web.search = lambda _: []
        self.web.wikipedia = lambda _: []
        with self.assertRaisesRegex(ResearchError, "No candidate"):
            self.agent.research(discovery)

    def test_no_research_sources_when_budget_exhausted(self):
        discovery = self.agent.discover(ResearchRequest(max_searches=1))
        self.web.wikipedia = lambda _: []
        with self.assertRaises(ResearchError):
            self.agent.research(discovery)

    def test_new_gap_sources_are_visible_in_bounded_context(self):
        self.agent._reset(ResearchRequest())
        self.agent._add([dict(url=f"https://source{i}.example", content=TEXT) for i in range(12)])
        packet = self.agent._packet()
        self.assertEqual(len(packet), 8)
        self.assertEqual(packet[-1]["id"], "D12")

    def test_ancient_modern_battle_and_war_matrix(self):
        for era in ("ancient", "modern"):
            for scope in ("battle", "war"):
                f = findings()
                f.era = era
                self.model.replies = [Selection(candidates=[candidate(scope=scope)]), f]
                with self.subTest(era=era, scope=scope):
                    result = self.run_agent(scope=scope)
                    self.assertEqual(result.findings.era, era)
                    self.assertEqual(result.selected.scope, scope)

    def test_auto_tries_next_candidate(self):
        incomplete = findings()
        incomplete.gaps = ["Need better evidence."]
        incomplete.blocking_gaps = incomplete.gaps.copy()
        self.model.replies = [Selection(candidates=[candidate("First"), candidate("Second")]), incomplete,
                              incomplete, findings()]
        result = self.run_agent()
        self.assertEqual(result.selected.topic, "Second")
        self.assertEqual(result.usage.searches, 10)
        self.assertLessEqual(result.usage.extracted_urls, 5)
        self.assertTrue(any("next candidate" in w for w in result.warnings))

    def test_targeted_gap_search_can_complete_same_topic(self):
        incomplete = findings()
        incomplete.gaps = ["Need evidence for the upstream crossing."]
        incomplete.blocking_gaps = incomplete.gaps.copy()
        self.model.replies = [Selection(candidates=[candidate()]), incomplete, findings()]
        result = self.run_agent()
        self.assertEqual(result.readiness, "ready")
        self.assertEqual(result.usage.searches, 6)
        self.assertTrue(any("upstream crossing" in str(call) for call in self.web.calls))

    def test_budget_stops_candidate_retry(self):
        f = findings()
        f.gaps = ["Missing evidence"]
        f.blocking_gaps = f.gaps.copy()
        self.model.replies = [Selection(candidates=[candidate("First"), candidate("Second")]), f]
        self.assertEqual(self.run_agent(max_searches=5).selected.topic, "First")

    def test_cache_reuses_web_without_reusing_llm(self):
        with TemporaryDirectory() as tmp:
            self.agent.cache = Cache(Path(tmp))
            self.run_agent()
            first = len(self.web.calls)
            self.run_agent()
            self.assertEqual(len(self.web.calls), first)
            self.assertEqual(len(self.model.prompts), 4)

    def test_nonessential_uncertainties_do_not_block_handoff(self):
        f = findings()
        f.gaps = ["The exact clock time is unknown."]
        self.model.replies = [Selection(candidates=[candidate()]), f]
        result = self.run_agent()
        self.assertEqual(result.readiness, "ready")
        self.assertEqual(result.findings.gaps, f.gaps)
        self.assertEqual(result.usage.searches, 5)

    def test_add_skips_bad_and_duplicate_results(self):
        self.agent._reset(ResearchRequest())
        self.agent._add([{}, dict(url="not a URL", content=TEXT), dict(url="https://valid.example/", content=" "),
                         dict(url="https://valid.example/", content=TEXT),
                         dict(url="https://valid.example/#fragment", content=TEXT)])
        self.assertEqual(len(self.agent.sources), 1)
        self.assertEqual(len(self.agent.warnings), 2)

    def test_research_can_resume_in_new_agent(self):
        discovery = self.agent.discover(ResearchRequest())
        other = ResearchAgent(FakeWeb(), FakeModel())
        self.assertEqual(other.research(discovery).readiness, "ready")


if __name__ == "__main__":
    unittest.main()
