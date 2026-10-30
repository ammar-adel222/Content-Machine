from copy import deepcopy
from war_director.models import Action, Blueprint, Cue, Force, Point, ScenePlan, Terrain
from war_reviewer.models import Findings, Scores
from war_writer.agent import WritingAgent
from .writer_helpers import WriterModel, dossier


def inputs():
    research = dossier()
    return research, WritingAgent(WriterModel()).write(research)


def blueprint():
    return Blueprint(scale="tactical", layout_note="Schematic layout only; positions are not surveyed coordinates.",
        terrain=[Terrain(id="river", label="River crossing", kind="river", shape="polygon",
            points=[Point(x=.45,y=.4),Point(x=.55,y=.4),Point(x=.55,y=.6),Point(x=.45,y=.6)],
            passability="blocked", tactical_effect="Restricts movement to a crossing.", claim_ids=["C6"])],
        forces=[Force(id="west", name="Western infantry", side="west", kind="infantry", position=Point(x=.2,y=.2), introduced_at=Cue(phrase_id="s1.p1"), introduction_reason="Present at the initial deployment.", subgroups=4, claim_ids=["C5"]),
                Force(id="east", name="Eastern army", side="east", kind="infantry", position=Point(x=.7,y=.7), introduced_at=Cue(phrase_id="s1.p1"), introduction_reason="Present at the initial deployment.", subgroups=4, claim_ids=["C1"])],
        scenes=[ScenePlan(scene_id=f"s{i}", focus=Point(x=.5,y=.5), view_width=1, focus_reason="Explain the position and the crossing.", labels=["River crossing"],
            actions=[Action(id=f"a{i}", kind="highlight", unit_id="west", start=Cue(phrase_id=f"s{i}.p1",fraction=0),
                end=Cue(phrase_id=f"s{i}.p1",fraction=1), formation="line", reason="Introduce the force mentioned in narration.",
                consequence="The viewer can identify the force.", claim_ids=["C5"])]) for i in range(1,5)])


def quality():
    return Findings(scores=Scores(accuracy=4, clarity=4, visual_logic=4, voice=4, readability=4), issues=[])


class DirectorModel:
    def __init__(self, replies=None):
        self.replies, self.used, self.prompts = list(replies or []), [], []

    def generate(self, prompt, schema, consume, **kwargs):
        consume()
        self.used.append("fake:director-reviewer")
        self.prompts.append(prompt)
        if self.replies:
            result = self.replies.pop(0)
            if isinstance(result, Exception):
                raise result
            return deepcopy(result)
        return quality() if schema is Findings else blueprint()
