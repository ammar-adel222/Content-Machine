"""Real LangGraph stage routing with durable receipts and explicit adapter boundaries."""
from dataclasses import dataclass
from contextlib import closing
import sqlite3
from typing import Callable, TypedDict
from .models import Artifact, Output, Revision
from .planner import ORDER, SPECS, computation_key, affected
from .store import ProjectStore, WorkflowError, BudgetExhausted


@dataclass
class Context:
    store: ProjectStore
    revision: Revision
    stage: str
    inputs: dict[str,Artifact]
    previous: Artifact | None

    @property
    def params(self):return self.revision.params.get(self.stage,{})

    @property
    def instructions(self):return self.revision.instructions.get(self.stage,{})

    @property
    def output_dir(self):
        path=self.store.root/'work'/self.revision.id/self.stage;path.mkdir(parents=True,exist_ok=True);return path

    def consume(self,kind='model_attempts',amount=1):self.store.consume(self.revision.id,kind,amount)


@dataclass(frozen=True)
class Adapter:
    run: Callable[[Context],Output]
    version: str
    rebind: Callable[[Context,Artifact],Output] | None = None
    cache_context: Callable[[Context],object] | None = None


class GraphState(TypedDict):
    revision_id: str
    next_stage: str
    status: str


class Runner:
    def __init__(self,store,adapters):
        if set(adapters)-set(SPECS):raise ValueError('Unknown adapter stage.')
        if any(not a.version for a in adapters.values()):raise ValueError('Adapters need implementation versions.')
        self.store=store;self.adapters=adapters

    def context(self,revision,stage):
        inputs={s:self.store.read_artifact(s,revision.artifacts[s]) for s in SPECS[stage].inputs}
        previous_id=revision.drafts.get(stage) or revision.artifacts.get(stage)
        previous=self.store.read_artifact(stage,previous_id) if previous_id else None
        return Context(self.store,revision.model_copy(deep=True),stage,inputs,previous)

    def cache_key(self,context,version):
        inputs={s:(a.content_hash if view=='content' else a.view_hashes.get(view,a.content_hash))
                for s,view in SPECS[context.stage].inputs.items() for a in [context.inputs[s]]}
        adapter=self.adapters.get(context.stage)
        if adapter and adapter.cache_context:
            from .planner import fingerprint
            inputs['__adapter_context__']=fingerprint(adapter.cache_context(context))
        return computation_key(context.stage,version,context.params,context.instructions,inputs)

    def _prepare(self,state):
        revision=self.store.load(state['revision_id'])
        if revision.status!='approved':
            revision.status='running';revision.blocked_stage=None;revision.issues=[];self.store.save(revision)
        return {'status':revision.status}

    def _route(self,state):
        revision=self.store.load(state['revision_id'])
        if revision.status!='approved' and self.store.metadata()['head']!=revision.id:
            revision.status='superseded';revision.issues=['A newer revision is current; completed work remains reusable.'];self.store.save(revision)
        if revision.status in ('needs_input','quota_wait','approved','superseded'):
            return {'next_stage':'__end__','status':revision.status}
        ready=[]
        for stage in ORDER:
            if stage not in revision.dirty:continue
            parents=set(SPECS[stage].inputs)|set(SPECS[stage].gates)
            if any(s in revision.dirty or s not in revision.artifacts for s in parents):continue
            ready.append(stage)
        if ready:
            # Finish connected independent branches before reporting a missing adapter.
            stage=next((s for s in ready if s in self.adapters),ready[0])
            return {'next_stage':stage,'status':'running'}
        if revision.dirty:
            revision.status='needs_input';revision.issues=['Pending work has unavailable prerequisites.']
        else:revision.status='awaiting_review'
        self.store.save(revision);return {'next_stage':'__human__' if not revision.dirty else '__end__','status':revision.status}

    def _execute(self,stage,state):
        revision=self.store.load(state['revision_id'])
        try:
            for gate in SPECS[stage].gates:
                artifact=self.store.read_artifact(gate,revision.artifacts[gate])
                if artifact.output.review!='pass':raise WorkflowError(f'{gate} has no passing review.')
            ctx=self.context(revision,stage);adapter=self.adapters.get(stage)
            version=adapter.version if adapter else ctx.previous.version if ctx.previous else None
            if version is None:raise WorkflowError(f'No adapter is connected for {stage}.')
            key=self.cache_key(ctx,version);cached=self.store.cached(stage,key)
            if cached:
                artifact=self.store.write_artifact(stage,key,adapter.rebind(ctx,cached),version) if adapter and adapter.rebind else cached
            else:
                if adapter is None:raise WorkflowError(f'No adapter is connected for {stage}.')
                output=Output.model_validate(adapter.run(ctx))
                if output.issues or (SPECS[stage].review and output.review!='pass'):
                    draft=self.store.write_artifact(stage,key,output,version,cache=False)
                    revision.drafts[stage]=draft.id
                    owner={'script_review':'writing','plan_review':'direction'}.get(stage)
                    if owner and output.review=='revise' and revision.repairs.get(stage,0)<1:
                        revision.repairs[stage]=revision.repairs.get(stage,0)+1
                        revision.instructions.setdefault(owner,{})['review_feedback']=output.issues or ['Address the saved review findings.']
                        revision.dirty=affected(set(revision.dirty)|{owner})
                        self.store.save(revision)
                        return {'status':'running'}
                    revision.status='needs_input';revision.blocked_stage=stage
                    revision.issues=output.issues or ['This review has not passed.'];self.store.save(revision)
                    return {'status':revision.status}
                artifact=self.store.write_artifact(stage,key,output,version)
            if artifact.output.issues or (SPECS[stage].review and artifact.output.review!='pass'):
                raise WorkflowError('Cached output has no valid passing review.')
            revision=self.store.load(revision.id)
            revision.artifacts[stage]=artifact.id;revision.dirty.remove(stage)
            revision.drafts.pop(stage,None)
            history=revision.reused if cached else revision.executed
            if stage not in history:history.append(stage)
            self.store.save(revision)
            return {'status':'running'}
        except (RuntimeError,ValueError,OSError,KeyError) as error:
            revision=self.store.load(revision.id);revision.status='quota_wait' if isinstance(error,BudgetExhausted) else 'needs_input'
            revision.blocked_stage=stage
            # Provider adapters should return actionable redacted issues in Output.
            # Do not checkpoint arbitrary exception bodies or client credentials.
            revision.issues=[str(error) if isinstance(error,WorkflowError) else f'{stage} failed ({type(error).__name__}); completed work is retained.']
            self.store.save(revision);return {'status':revision.status}

    def _human(self,state):
        from langgraph.types import interrupt
        revision=self.store.load(state['revision_id'])
        media=self.store.read_artifact('mux',revision.artifacts['mux'])
        if 'video' not in media.file_hashes:
            revision.status='needs_input';revision.blocked_stage='mux';revision.issues=['A final video is required for human review.']
            self.store.save(revision);return {'status':revision.status}
        decision=interrupt({'revision':revision.id,'video':media.output.files['video'],
                            'video_sha256':media.file_hashes['video'],'action':'Review this exact final version.'})
        if not isinstance(decision,dict) or decision.get('approve') is not True or decision.get('video_sha256')!=media.file_hashes['video']:
            raise WorkflowError('Approval must name the exact reviewed video hash.')
        revision=self.store.approve(revision.id)
        return {'status':revision.status}

    def build(self,checkpointer):
        from langgraph.graph import StateGraph,START,END
        builder=StateGraph(GraphState)
        builder.add_node('prepare_run',self._prepare);builder.add_node('route',self._route)
        builder.add_node('human_review',self._human);builder.add_edge('human_review',END)
        builder.add_edge(START,'prepare_run');builder.add_edge('prepare_run','route')
        for stage in ORDER:
            def execute(state,selected=stage):return self._execute(selected,state)
            builder.add_node(stage,execute);builder.add_edge(stage,'route')
        builder.add_conditional_edges('route',lambda state:state['next_stage'],{s:s for s in ORDER}|{'__end__':END,'__human__':'human_review'})
        return builder.compile(checkpointer=checkpointer)

    def run(self,revision_id=None):
        try:from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError:raise WorkflowError('Install the optional workflow dependencies first.') from None
        revision_id=revision_id or self.store.metadata()['head'];self.store.load(revision_id)
        with self.store.run_lock(),closing(sqlite3.connect(self.store.root/'checkpoints.sqlite',check_same_thread=False)) as connection:
            graph=self.build(SqliteSaver(connection))
            config={'configurable':{'thread_id':self.store.metadata()['id']+':'+revision_id},'recursion_limit':100}
            # Restart routing from persisted receipts after a controlled failure.
            # Completed stage work is reused even after a checkpoint-write crash.
            graph.invoke({'revision_id':revision_id,'next_stage':'','status':'running'},config)
        return self.store.load(revision_id)

    def approve(self,revision_id=None):
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            from langgraph.types import Command
        except ImportError:raise WorkflowError('Install the optional workflow dependencies first.') from None
        revision_id=revision_id or self.store.metadata()['head'];revision=self.store.load(revision_id)
        if revision.status=='approved':return self.store.approve(revision_id)
        if revision.status!='awaiting_review':raise WorkflowError('Run this revision to its review gate first.')
        media=self.store.read_artifact('mux',revision.artifacts['mux'])
        with self.store.run_lock(),closing(sqlite3.connect(self.store.root/'checkpoints.sqlite',check_same_thread=False)) as connection:
            graph=self.build(SqliteSaver(connection));config={'configurable':{'thread_id':self.store.metadata()['id']+':'+revision_id}}
            if 'human_review' not in graph.get_state(config).next:raise WorkflowError('No persisted approval interrupt exists for this revision.')
            graph.invoke(Command(resume={'approve':True,'video_sha256':media.file_hashes['video']}),config)
        return self.store.load(revision_id)
