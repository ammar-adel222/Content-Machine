from copy import deepcopy

from war_research.agent import ResearchAgent
from war_research.models import ResearchRequest
from war_writer.models import Draft, Review, Scene, Phrase
from .helpers import FakeModel, FakeWeb


SPEECH = ("The armies faced each other across a narrow valley. The crossing limited their movement "
          "and made the ground important. One side watched the route while the other prepared to move. "
          "A change in position could expose the flank and decide who held the crossing. The result "
          "depended on how those movements unfolded. That made this small position worth understanding.")


def dossier():
    agent = ResearchAgent(FakeWeb(), FakeModel())
    return agent.research(agent.discover(ResearchRequest()))


def draft():
    return Draft(title="The crossing that decided the battle", caption="A short tactical explanation.",
        narrator_style="Conversational documentary narrator. Clear, restrained and interested.",
        scenes=[Scene(id=f"s{i}", role=role, claim_ids=[f"C{n}" for n in range(1, 9)],
                      visual_intent="Explain how the crossing restricted army movement.", tone="Thoughtful",
                      delivery_notes="Let the key idea land naturally; avoid theatrical shouting.",
                      phrases=[Phrase(text=SPEECH, pace="normal", emphasis=["crossing"], pause_after_ms=250)])
                for i, role in enumerate(("hook", "context", "maneuver", "outcome"), 1)],
        pronunciations=[])


class WriterModel:
    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.used, self.prompts = [], []

    def generate(self, prompt, schema, consume, **kwargs):
        consume()
        self.prompts.append(prompt)
        self.used.append("fake:writer")
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return deepcopy(reply)
        return Review(issues=[]) if schema is Review else draft()
