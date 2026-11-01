"""Small adapters around the independent research, writer, director and reviewer APIs."""
import os
from .graph import Adapter
from .models import Output
from .planner import fingerprint
from .store import WorkflowError
from war_research.agent import ResearchAgent, validate_evidence
from war_research.models import Discovery, Dossier, ResearchRequest
from war_research.providers import LanguageModel, Web, model_routes
from war_research.storage import Cache
from war_writer.agent import WritingAgent, check_draft, fingerprint as contract_hash
from war_writer.models import Script, WritingRequest
from war_writer.storage import tts_plan
from war_director.agent import DirectorAgent, check_plan, context, validate_inputs
from war_director.models import Plan, DirectionRequest
from war_reviewer.agent import ReviewerAgent


class BudgetModel:
    """Reserve each provider attempt, including fallbacks, before sending it."""
    def __init__(self, model, ctx):self.model,self.ctx=model,ctx

    @property
    def used(self):return self.model.used

    def generate(self, prompt, schema, consume, **kwargs):
        def reserve():
            consume()
            self.ctx.consume()
        return self.model.generate(prompt,schema,reserve,**kwargs)


class BudgetWeb:
    def __init__(self, web, ctx):self.web,self.ctx=web,ctx
    def search(self, query):
        self.ctx.consume('search_requests');return self.web.search(query)
    def wikipedia(self, topic):
        self.ctx.consume('search_requests');return self.web.wikipedia(topic)
    def extract(self, urls):
        if not urls:return {}
        self.ctx.consume('search_requests');return self.web.extract(urls)


def load(ctx, stage, schema):return schema.model_validate(ctx.inputs[stage].output.data)


def notes(ctx):
    parts=[ctx.params.get('notes',''),ctx.instructions.get('notes','')]
    parts.extend(ctx.instructions.get('review_feedback',[]))
    text='\n'.join(p for p in parts if p)
    if len(text)>5000:raise WorkflowError('Revision and review notes exceed 5000 characters; shorten the request.')
    if ctx.instructions.get('object_ids'):
        raise WorkflowError('Object-specific authoring edits are not supported yet; use a scene or full-plan edit.')
    return text


def request(ctx, schema):
    values=dict(ctx.params)
    values['notes']=notes(ctx)
    scenes=ctx.instructions.get('scene_ids',[])
    if len(scenes)>1:raise WorkflowError('Authoring accepts one scene per edit; submit separate scene edits.')
    if scenes:values['scene_id']=scenes[0]
    return schema.model_validate(values)


def saved(ctx, contract, **kwargs):
    data=contract.model_dump(mode='json')
    path=ctx.output_dir/(ctx.stage+'-'+fingerprint(data)+'.json')
    if not path.exists():path.write_text(contract.model_dump_json(indent=2),encoding='utf-8')
    return Output(data=data,files={'contract':str(path)},**kwargs)


def research_views(dossier):
    # Exclude run bookkeeping, never evidence, readiness or editorial context.
    data=dossier.model_dump(mode='json',exclude={'created_at','usage','models_used'})
    return {'claims':data,'geography':data}


def script_output(ctx, script):
    draft=script.draft.model_dump(mode='json')
    speech={k:draft[k] for k in ('narrator_style','pronunciations')}
    speech['scenes']=[{'id':s.id,'tone':s.tone,'delivery_notes':s.delivery_notes,
                      'phrases':[p.model_dump(mode='json') for p in s.phrases]} for s in script.draft.scenes]
    output=saved(ctx,script,views={'visual':draft,'speech':speech,
        'phrases':speech['scenes'],'captions':[{'id':s.id,'text':[p.text for p in s.phrases]} for s in script.draft.scenes]},
        issues=script.issues if script.status=='ready' else script.issues or ['Script requires revision.'])
    import json
    handoff=tts_plan(script)
    path=ctx.output_dir/('tts-plan-'+fingerprint(handoff)+'.json')
    if not path.exists():path.write_text(json.dumps(handoff,ensure_ascii=False,indent=2),encoding='utf-8')
    output.files['tts_plan']=str(path)
    return output


def plan_output(ctx, plan):
    b=plan.blueprint.model_dump(mode='json')
    return saved(ctx,plan,views={'spatial':{k:b[k] for k in ('terrain','scale','layout_kind','layout_note')},
        'units':b['forces'],'actions':{'scenes':b['scenes'],'forces':b['forces']},
        'sound_profiles':{'forces':[{k:f[k] for k in ('id','kind','subgroups','side','position')} for f in b['forces']],
            'actions':[{k:a[k] for k in ('id','kind','unit_id','target_id','route','formation','stagger','claim_ids')}
                       for s in b['scenes'] for a in s['actions']]}},
        issues=plan.issues if plan.status=='ready' else plan.issues or ['Direction requires revision.'])


def adapters(model_factory=None, web_factory=None):
    """Factories are lazy: cached work/audio edits need no model keys or web client."""
    model_factory=model_factory or (lambda:LanguageModel(model_routes()))
    web_factory=web_factory or (lambda:Web(os.environ.get('TAVILY_API_KEY','')))
    def model(ctx):return BudgetModel(model_factory(),ctx)

    def research(ctx):
        values=dict(ctx.params)
        values.setdefault('mode','specific' if values.get('topic') else 'auto')
        values.setdefault('as_of',ctx.revision.created_at.date())
        # Notes steer collection, but cannot silently replace the selected topic.
        extra=notes(ctx)
        values.pop('notes',None)
        req=ResearchRequest.model_validate(values)
        if ctx.instructions.get('scene_ids'):raise WorkflowError('Research edits apply to the full dossier.')
        client=model(ctx)
        if extra:
            base=client
            class RequestedModel:
                used=base.used
                def generate(self,prompt,schema,consume,**kwargs):
                    return base.generate(prompt+'\nPROJECT RESEARCH REQUEST: '+extra,schema,consume,**kwargs)
            client=RequestedModel()
        agent=ResearchAgent(BudgetWeb(web_factory(),ctx),client,Cache(ctx.store.root/'web-cache'))
        # A discovery is reusable across a quota stop; the receipt verifies its integrity.
        key=fingerprint({'discovery':req.model_dump(mode='json'),'notes':extra,'version':1})
        receipt=ctx.store.cached('research',key)
        discovery=Discovery.model_validate(receipt.output.data) if receipt else agent.discover(req)
        if not receipt:ctx.store.write_artifact('research',key,saved(ctx,discovery),'discovery-v1')
        dossier=agent.research(discovery)
        validate_evidence(dossier.findings,dossier.sources)
        return saved(ctx,dossier,views=research_views(dossier),
            issues=dossier.findings.blocking_gaps if dossier.readiness=='ready' else dossier.findings.blocking_gaps or ['Research is incomplete.'])

    def writing(ctx):
        dossier=load(ctx,'research',Dossier);req=request(ctx,WritingRequest)
        previous=Script.model_validate(ctx.previous.output.data) if ctx.previous else None
        if previous and previous.dossier_sha256!=contract_hash(dossier):
            if req.scene_id:raise WorkflowError('Research changed; create a full script before editing a scene.')
            previous=None
        return script_output(ctx,WritingAgent(model(ctx)).write(dossier,req,previous))

    def rebind_script(ctx,cached):
        dossier=load(ctx,'research',Dossier);script=Script.model_validate(cached.output.data)
        validate_evidence(dossier.findings,dossier.sources)
        if dossier.readiness!='ready' or dossier.findings.blocking_gaps:raise WorkflowError('Research is incomplete.')
        if script.topic!=dossier.selected.topic or script.scope!=dossier.selected.scope:raise WorkflowError('Cached script topic differs from research.')
        issues=check_draft(script.draft,dossier,script.target_seconds)
        if issues:raise WorkflowError('Cached script fails current validation; request a full rewrite.')
        used={i for s in script.draft.scenes for i in s.claim_ids}
        script=script.model_copy(update={'dossier_sha256':contract_hash(dossier),
            'claims':[c for c in dossier.findings.claims if c.id in used]})
        return script_output(ctx,script)

    def direction(ctx):
        dossier=load(ctx,'research',Dossier);script=load(ctx,'writing',Script);req=request(ctx,DirectionRequest)
        previous=Plan.model_validate(ctx.previous.output.data) if ctx.previous else None
        if (previous and previous.status=='ready' and previous.dossier_sha256==contract_hash(dossier)
                and previous.script_sha256!=contract_hash(script) and ctx.revision.edit
                and ctx.revision.edit.kind!='route' and not req.scene_id
                and not ctx.instructions.get('review_feedback')):
            # Retain valid choreography after wording edits; the independent plan
            # review still checks the new script and can route a repair back here.
            try:return rebind_plan(ctx,ctx.previous)
            except WorkflowError:pass
        if previous and (previous.dossier_sha256!=contract_hash(dossier) or previous.script_sha256!=contract_hash(script)):
            if req.scene_id:raise WorkflowError('Script or research changed; create a full plan before editing a scene.')
            previous=None
        return plan_output(ctx,DirectorAgent(model(ctx)).direct(dossier,script,req,previous))

    def rebind_plan(ctx,cached):
        dossier=load(ctx,'research',Dossier);script=load(ctx,'writing',Script)
        validate_inputs(dossier,script)
        plan=Plan.model_validate(cached.output.data)
        issues,timeline=check_plan(plan.blueprint,dossier,script)
        if issues:raise WorkflowError('Cached direction fails current validation; request a new plan.')
        plan=plan.model_copy(update={'dossier_sha256':contract_hash(dossier),'script_sha256':contract_hash(script),'timeline':timeline})
        return plan_output(ctx,plan)

    def review(ctx):
        dossier=load(ctx,'research',Dossier);script=load(ctx,'writing',Script)
        validate_inputs(dossier,script)
        artifact=script.draft
        local=check_draft(script.draft,dossier,script.target_seconds)
        if ctx.stage=='plan_review':
            plan=load(ctx,'direction',Plan)
            if plan.dossier_sha256!=contract_hash(dossier) or plan.script_sha256!=contract_hash(script):
                raise WorkflowError('Direction references different research or script versions.')
            artifact=plan.blueprint
            local+=check_plan(artifact,dossier,script)[0]
        # Fail local checks before spending a review request.
        if local:return Output(data={'local_issues':local},review='revise',issues=local[:30])
        result=ReviewerAgent(model(ctx)).review(artifact,context(dossier,script),lambda:None)
        issues=result.local_issues+[i.message for i in result.findings.issues if i.severity=='blocking']
        return saved(ctx,result,review=result.status,issues=issues[:30])

    def edit_context(ctx):
        # Edits are based on the previous whole artifact, including preserved scenes.
        return ctx.previous.content_hash if ctx.previous and (ctx.instructions or ctx.params.get('scene_id') or ctx.params.get('notes')) else None
    return {'research':Adapter(research,'authoring-research-v1'),
            'writing':Adapter(writing,'authoring-writing-v1',rebind_script,edit_context),
            'script_review':Adapter(review,'authoring-review-v1'),
            'direction':Adapter(direction,'authoring-direction-v1',rebind_plan,edit_context),
            'plan_review':Adapter(review,'authoring-review-v1')}
