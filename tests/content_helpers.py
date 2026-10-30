from copy import deepcopy
from war_content.models import Asset, Binding, Brief, Design, DesignReview, Manifest, ManifestReview, Primitive
from war_director.agent import DirectorAgent
from war_writer.agent import fingerprint
from .director_helpers import DirectorModel, inputs


def ready():
    dossier,script=inputs()
    return dossier,script,DirectorAgent(DirectorModel()).direct(dossier,script)


def manifest(dossier,plan):
    claims={c.id:c.statement for c in dossier.findings.claims}
    return Manifest(bindings=[Binding(object_id=item.id,
        brief=Brief(category=category,concept=concept,description=description),
        claim_id=item.claim_ids[0],evidence_quote=claims[item.claim_ids[0]])
        for category,concept,description,items in (
            ('unit','infantry','Generic top-down infantry with a round head and body.',plan.blueprint.forces),
            ('terrain','river','Simple repeatable parallel water ripple motif.',plan.blueprint.terrain)) for item in items])


def design():
    return Design(label='Infantry marker',explanation='A minimal top-down head and body silhouette.',
        primitives=[Primitive(kind='ellipse',width=.8,height=.8),Primitive(kind='rect',x=-.3,width=.5,height=.6)])


def passing():
    return DesignReview(recognizable=True,consistent_style=True,supported_by_brief=True,issues=[])


def asset(brief):
    return Asset(brief=brief,design=design(),design_sha256=fingerprint(design()),review=passing(),models_used=['fake:designer'])


class ContentModel:
    def __init__(self,requirements=None,replies=None):
        self.used,self.prompts=[],[]
        self.requirements,self.replies=requirements,list(replies or [])

    def generate(self,prompt,schema,consume,**kwargs):
        consume();self.used.append('fake:designer');self.prompts.append(prompt)
        if self.replies:
            response=self.replies.pop(0)
            if isinstance(response,Exception):raise response
            return deepcopy(response)
        return deepcopy(self.requirements) if schema is Manifest else ManifestReview(issues=[]) if schema is ManifestReview else passing() if schema is DesignReview else design()
