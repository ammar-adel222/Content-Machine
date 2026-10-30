"""Synthetic evidence: tests never use API keys, the network, or historical assertions."""

from copy import deepcopy

from war_research.models import Candidate, Findings, REQUIRED_SECTIONS, Scores, Selection


QUOTES = {
    "context": "The two opposing kingdoms fought over control of the valley.",
    "dates": "The battle began on the first day of the summer campaign.",
    "duration": "The fighting continued for three days before the retreat.",
    "location": "The battlefield lay in the valley north of the old town.",
    "forces": "The western army deployed infantry and cavalry under Commander A.",
    "terrain": "A narrow river crossing restricted the eastern army's advance.",
    "events": "The western cavalry crossed upstream and attacked the eastern flank.",
    "outcome": "The eastern army withdrew and the western army held the crossing.",
}
TEXT = " ".join(QUOTES.values())


def candidate(topic="Example Battle", scope="battle", score=4):
    return Candidate(topic=topic, scope=scope, angle="How the river crossing decided the engagement",
        reason="Terrain and documented movements offer a clear explanation.", source_ids=["D1"],
        scores=Scores(**{name: score for name in ("story", "visual", "evidence", "format_fit", "novelty")}))


def findings():
    return Findings(era="ancient", ongoing=False, recommended_seconds=105,
        summary="The river crossing constrained the advance, and a flank attack forced a withdrawal.",
        claims=[dict(id=f"C{i}", section=section, statement=QUOTES[section], status="documented",
                     evidence=[dict(source_id="S2" if section == "outcome" else "S1",
                                    passage_id="S2:P1" if section == "outcome" else "S1:P1", quote=QUOTES[section])])
                for i, section in enumerate(REQUIRED_SECTIONS, 1)],
        terrain=[dict(name="River crossing", description="A narrow crossing.",
                      tactical_effect="Restricted the advance.", spatial_relation="In the valley.", claim_ids=["C6"])],
        events=[dict(order=1, title="Flank attack", time=None, actors=["Western cavalry"],
                     location="Upstream crossing", action=QUOTES["events"], reason="Unknown.",
                     consequence=QUOTES["outcome"], claim_ids=["C7", "C8"])],
        essential_claim_ids=["C1", "C6", "C7", "C8"], optional_claim_ids=["C2", "C3", "C4", "C5"], gaps=[])


class FakeWeb:
    def __init__(self):
        self.calls = []
        self.fail_search = self.fail_wiki = self.fail_extract = False

    def search(self, query):
        from war_research.providers import ProviderError
        self.calls.append(("search", query))
        if self.fail_search:
            raise ProviderError("Search unavailable")
        return [dict(url="https://museum.example/battle", title="Campaign history", content=TEXT),
                dict(url="https://archive.example/battle", title="Historical account", content=TEXT)]

    def wikipedia(self, topic):
        from war_research.providers import ProviderError
        self.calls.append(("wiki", topic))
        if self.fail_wiki:
            raise ProviderError("Wikipedia unavailable")
        return [dict(url="https://en.wikipedia.org/wiki/Example", title=topic, content=TEXT, full_text=True)]

    def extract(self, urls):
        from war_research.providers import ProviderError
        self.calls.append(("extract", urls))
        if self.fail_extract:
            raise ProviderError("Extraction unavailable")
        return {url: TEXT for url in urls}


class FakeModel:
    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.used = []
        self.prompts = []

    def generate(self, prompt, schema, consume, **kwargs):
        consume()
        self.prompts.append(prompt)
        self.used.append("fake:test-model")
        if self.replies:
            return deepcopy(self.replies.pop(0))
        return Selection(candidates=[candidate()]) if schema is Selection else findings()
