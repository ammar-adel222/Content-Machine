"""Run real authoring agents through LangGraph against synthetic provider responses."""
from copy import deepcopy
import importlib.util
import io
import contextlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from war_workflow.models import Edit, Output
from war_workflow.planner import fingerprint
from war_workflow.store import ProjectStore, BudgetExhausted, WorkflowError
from war_research.models import Selection, Findings as ResearchFindings, Dossier
from war_writer.models import Draft, Review, SceneEdit, Script
from war_director.models import Blueprint, ScenePlan, Plan
from war_reviewer.models import Findings as ReviewFindings, Issue
from war_writer.agent import fingerprint as contract_hash
from .helpers import FakeWeb, candidate, findings
from .writer_helpers import draft
from .director_helpers import blueprint, quality


class Model:
    def __init__(self):
        self.used=[];self.calls=[];self.responses={}

    def generate(self,prompt,schema,consume,**kwargs):
        consume();self.used.append('synthetic:model');self.calls.append((schema,prompt))
        queue=self.responses.get(schema,[])
        if queue:
            value=queue.pop(0)
            if isinstance(value,Exception):raise value
            return deepcopy(value)
        return {Selection:lambda:Selection(candidates=[candidate()]),ResearchFindings:findings,
                Draft:draft,Review:lambda:Review(issues=[]),Blueprint:blueprint,
                ReviewFindings:quality,SceneEdit:lambda:SceneEdit(scene=draft().scenes[0]),
                ScenePlan:lambda:blueprint().scenes[0]}[schema]()


@unittest.skipUnless(importlib.util.find_spec('langgraph'),'Install workflow extra')
class AuthoringTests(unittest.TestCase):
    def setUp(self):
        from war_workflow.authoring import adapters
        from war_workflow.graph import Runner
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=ProjectStore.create(self.root/'project','Example Battle')
        self.model=Model();self.web=FakeWeb()
        self.adapters=adapters(lambda:self.model,lambda:self.web)
        self.runner=Runner(self.store,self.adapters)

    def artifact(self,stage,revision=None):
        revision=revision or self.store.load()
        return self.store.read_artifact(stage,revision.artifacts[stage])

    def test_real_agents_finish_authoring_and_resume_without_requests(self):
        result=self.runner.run()
        self.assertEqual(result.status,'needs_input');self.assertEqual(result.blocked_stage,'narration')
        self.assertEqual(result.executed,['research','writing','script_review','direction','plan_review'])
        research=Dossier.model_validate(self.artifact('research').output.data)
        script=Script.model_validate(self.artifact('writing').output.data)
        plan=Plan.model_validate(self.artifact('direction').output.data)
        self.assertEqual(script.dossier_sha256,contract_hash(research))
        self.assertEqual(plan.script_sha256,contract_hash(script))
        for stage in result.executed:
            artifact=self.artifact(stage)
            self.assertTrue(Path(artifact.output.files['contract']).is_file())
        for stage in ('script_review','plan_review'):
            self.assertEqual(self.artifact(stage).output.review,'pass')
        handoff=json.loads(Path(self.artifact('writing').output.files['tts_plan']).read_text(encoding='utf-8'))
        self.assertIn('Tone:',handoff['chunks'][0]['direction'])
        self.assertEqual(handoff['chunks'][0]['pause_after_ms'],script.draft.scenes[0].phrases[0].pause_after_ms)
        calls=len(self.model.calls);web_calls=len(self.web.calls)
        self.runner.run();self.assertEqual(len(self.model.calls),calls);self.assertEqual(len(self.web.calls),web_calls)
        budgets=self.store.budgets(result.id)
        self.assertEqual(budgets['model_attempts']['used'],calls)
        self.assertEqual(budgets['search_requests']['used'],web_calls)
        self.assertNotIn('mux',result.artifacts);self.assertIsNone(result.approval)

    def test_scene_script_edit_preserves_other_scenes_and_research(self):
        parent=self.runner.run();old=Script.model_validate(self.artifact('writing').output.data)
        changed=old.draft.scenes[0].model_copy(deep=True);changed.tone='Quietly intrigued'
        self.model.responses[SceneEdit]=[SceneEdit(scene=changed)]
        self.store.edit(Edit(parent_revision=parent.id,kind='script',scene_ids=['s1'],notes='Use a quieter delivery.'))
        result=self.runner.run();new=Script.model_validate(self.artifact('writing').output.data)
        self.assertEqual(new.changed_scene_ids,['s1']);self.assertEqual(new.draft.scenes[1:],old.draft.scenes[1:])
        self.assertEqual(result.artifacts['research'],parent.artifacts['research'])
        self.assertIn('scene',self.model.calls[-5][1].lower())

    def test_director_scene_edit_keeps_research_and_script(self):
        parent=self.runner.run();old=Plan.model_validate(self.artifact('direction').output.data)
        changed=old.blueprint.scenes[0].model_copy(deep=True);changed.focus_reason='Explain the narrow crossing more clearly.'
        self.model.responses[ScenePlan]=[changed]
        self.store.edit(Edit(parent_revision=parent.id,kind='route',scene_ids=['s1'],notes='Clarify the crossing.'))
        result=self.runner.run();plan=Plan.model_validate(self.artifact('direction').output.data)
        self.assertEqual(plan.changed_scene_ids,['s1']);self.assertEqual(plan.blueprint.scenes[1:],old.blueprint.scenes[1:])
        self.assertEqual(result.artifacts['writing'],parent.artifacts['writing'])
        self.assertNotIn('writing',result.executed)

    def test_repeated_scene_edit_cannot_restore_an_older_untouched_scene(self):
        self.runner.run()
        for scene_id,tone in [('s1','Curious'),('s2','Restrained'),('s1','Curious')]:
            script=Script.model_validate(self.artifact('writing').output.data)
            changed=next(s for s in script.draft.scenes if s.id==scene_id).model_copy(deep=True)
            changed.tone=tone;self.model.responses[SceneEdit]=[SceneEdit(scene=changed)]
            self.store.edit(Edit(parent_revision=self.store.load().id,kind='script',scene_ids=[scene_id],notes=f'Use a {tone} tone.'))
            self.runner.run()
        final=Script.model_validate(self.artifact('writing').output.data)
        self.assertEqual(final.draft.scenes[0].tone,'Curious')
        self.assertEqual(final.draft.scenes[1].tone,'Restrained')

    def test_script_review_routes_once_to_writer_and_passes(self):
        bad=quality();bad.issues=[Issue(severity='blocking',message='Explain the river crossing more clearly.',scene_id='s1')]
        self.model.responses[ReviewFindings]=[bad,quality()]
        result=self.runner.run()
        self.assertEqual(result.repairs,{'script_review':1});self.assertIn('plan_review',result.artifacts)
        prompts=[p for schema,p in self.model.calls if schema is Draft]
        self.assertEqual(len(prompts),2);self.assertIn('Explain the river crossing',prompts[1])

    def test_repeated_review_failure_is_bounded_and_survives_reopen(self):
        bad=quality();bad.scores.clarity=2
        self.model.responses[ReviewFindings]=[bad,bad,bad]
        result=self.runner.run()
        self.assertEqual(result.blocked_stage,'script_review');self.assertEqual(result.repairs['script_review'],1)
        self.assertNotIn('direction',result.artifacts);self.assertIn('script_review',result.drafts)
        self.assertEqual(sum(s is Draft for s,p in self.model.calls),2)
        # A manual retry may review again; it must never reset the repair allowance.
        result=self.runner.run();self.assertEqual(result.repairs['script_review'],1)
        self.assertEqual(sum(s is Draft for s,p in self.model.calls),2)

    def test_plan_review_repairs_only_director(self):
        bad=quality();bad.scores.visual_logic=2
        # Calls: external script review, director's internal review, external plan review.
        self.model.responses[ReviewFindings]=[quality(),quality(),bad,quality(),quality()]
        result=self.runner.run()
        self.assertEqual(result.repairs,{'plan_review':1})
        self.assertEqual(sum(s is Draft for s,p in self.model.calls),1)
        self.assertEqual(sum(s is Blueprint for s,p in self.model.calls),2)
        self.assertEqual(self.artifact('plan_review').output.review,'pass')

    def test_quota_resume_keeps_discovery_and_web_cache(self):
        revision=self.store.load();self.store.set_limit(revision.id,'model_attempts',1)
        result=self.runner.run();self.assertEqual(result.status,'quota_wait')
        self.assertEqual(sum(s is Selection for s,p in self.model.calls),1)
        web_calls=len(self.web.calls)
        self.store.set_limit(revision.id,'model_attempts',32)
        result=self.runner.run();self.assertIn('plan_review',result.artifacts)
        self.assertEqual(sum(s is Selection for s,p in self.model.calls),1)
        self.assertEqual(len(self.web.calls),web_calls)

    def test_zero_web_budget_makes_no_network_or_model_requests(self):
        self.store.set_limit(self.store.load().id,'search_requests',0)
        result=self.runner.run()
        self.assertEqual(result.status,'quota_wait');self.assertEqual(self.web.calls,[]);self.assertEqual(self.model.calls,[])

    def test_provider_fallback_attempts_reserve_separately(self):
        from war_workflow.authoring import BudgetModel
        from war_workflow.graph import Context
        revision=self.store.load();self.store.set_limit(revision.id,'model_attempts',1)
        ctx=Context(self.store,revision,'research',{},None)
        class Fallback:
            used=[]
            def generate(self,prompt,schema,consume):
                consume();consume();raise AssertionError('Second attempt must not reach transport.')
        with self.assertRaises(BudgetExhausted):BudgetModel(Fallback(),ctx).generate('',Draft,lambda:None)
        self.assertEqual(self.store.budgets(revision.id)['model_attempts']['used'],1)

    def test_failed_draft_is_saved_and_blocks_review(self):
        invalid=draft();invalid.scenes[0].claim_ids=['missing']
        self.model.responses[Draft]=[invalid,invalid]
        result=self.runner.run()
        self.assertEqual(result.blocked_stage,'writing');self.assertIn('writing',result.drafts)
        self.assertNotIn('script_review',result.artifacts)
        retained=self.store.read_artifact('writing',result.drafts['writing'])
        self.assertEqual(retained.output.data['status'],'needs_revision')

    def test_research_revision_notes_are_sent_without_changing_topic(self):
        parent=self.store.load()
        self.store.edit(Edit(parent_revision=parent.id,kind='research',notes='Check conflicting terrain descriptions.'))
        self.runner.run()
        prompts=[p for schema,p in self.model.calls if schema in (Selection,ResearchFindings)]
        self.assertTrue(all('Check conflicting terrain descriptions.' in p for p in prompts))
        self.assertEqual(self.artifact('research').output.data['selected']['topic'],'Example Battle')

    def test_unsupported_scope_fails_before_model_call(self):
        parent=self.runner.run();calls=len(self.model.calls)
        self.store.edit(Edit(parent_revision=parent.id,kind='route',object_ids=['west'],notes='Change this force.'))
        result=self.runner.run();self.assertEqual(result.blocked_stage,'direction')
        self.assertIn('Object-specific',result.issues[0]);self.assertEqual(len(self.model.calls),calls)

    def test_multiple_scene_edits_and_unknown_settings_fail_without_requests(self):
        parent=self.runner.run();calls=len(self.model.calls)
        self.store.edit(Edit(parent_revision=parent.id,kind='script',scene_ids=['s1','s2'],notes='Improve delivery.'))
        result=self.runner.run();self.assertIn('one scene',result.issues[0]);self.assertEqual(len(self.model.calls),calls)
        self.store.edit(Edit(parent_revision=result.id,kind='script',patch={'unknown_option':True},notes='Full rewrite.'))
        result=self.runner.run();self.assertEqual(result.blocked_stage,'writing');self.assertEqual(len(self.model.calls),calls)

    def test_research_changes_reject_stale_targeted_script_and_plan_edits(self):
        from war_workflow.graph import Context
        self.runner.run();revision=self.store.load()
        changed=Dossier.model_validate(self.artifact('research').output.data);changed.warnings.append('Updated evidence context.')
        research=self.store.write_artifact('research',fingerprint('changed-research'),Output(data=changed.model_dump(mode='json')))
        revision.instructions['writing']={'scene_ids':['s1'],'notes':'Clarify the hook.'}
        ctx=Context(self.store,revision,'writing',{'research':research},self.artifact('writing'))
        with self.assertRaisesRegex(WorkflowError,'Research changed'):self.adapters['writing'].run(ctx)
        script=Script.model_validate(self.artifact('writing').output.data);script.model_calls+=1
        writing=self.store.write_artifact('writing',fingerprint('changed-script'),Output(data=script.model_dump(mode='json')))
        revision.instructions['direction']={'scene_ids':['s1'],'notes':'Clarify this scene.'}
        ctx=Context(self.store,revision,'direction',{'research':self.artifact('research'),'writing':writing},self.artifact('direction'))
        with self.assertRaisesRegex(WorkflowError,'Script or research changed'):self.adapters['direction'].run(ctx)

    def test_incomplete_research_retained_and_blocks_writer(self):
        partial=findings();partial.blocking_gaps=['Missing reliable terrain evidence.']
        self.model.responses[ResearchFindings]=[partial,partial]
        result=self.runner.run()
        self.assertEqual(result.blocked_stage,'research');self.assertIn('research',result.drafts)
        self.assertNotIn('writing',result.artifacts)
        self.assertFalse(any(s is Draft for s,p in self.model.calls))

    def test_plan_review_rejects_stale_contract_before_request(self):
        from war_workflow.graph import Context
        self.runner.run();revision=self.store.load();plan=Plan.model_validate(self.artifact('direction').output.data)
        plan.script_sha256='stale'
        bad=self.store.write_artifact('direction',fingerprint('stale-plan'),Output(data=plan.model_dump(mode='json')))
        ctx=Context(self.store,revision,'plan_review',{'research':self.artifact('research'),'writing':self.artifact('writing'),'direction':bad},None)
        calls=len(self.model.calls)
        with self.assertRaisesRegex(WorkflowError,'different research or script'):self.adapters['plan_review'].run(ctx)
        self.assertEqual(len(self.model.calls),calls)

    def test_lazy_factories_and_cli_use_no_keys_for_finished_work(self):
        from war_workflow.authoring import adapters
        from war_workflow.graph import Runner
        from war_workflow.__main__ import main
        self.runner.run()
        def unavailable():raise AssertionError('No client should be initialized.')
        Runner(self.store,adapters(unavailable,unavailable)).run()
        with contextlib.redirect_stdout(io.StringIO()),patch('war_workflow.authoring.adapters',return_value=self.adapters),patch('war_workflow.speech.adapters',return_value={}):
            self.assertEqual(main(['run',str(self.store.root),'--env-file',str(self.root/'absent.env')]),2)

    def test_cached_script_rebinds_current_provenance_without_regeneration(self):
        from war_workflow.graph import Context
        self.runner.run();revision=self.store.load()
        original=self.artifact('research');updated=Dossier.model_validate(original.output.data)
        updated.usage.model_calls+=1
        changed=self.store.write_artifact('research',fingerprint('updated-bookkeeping'),Output(data=updated.model_dump(mode='json')))
        ctx=Context(self.store,revision,'writing',{'research':changed},self.artifact('writing'))
        calls=len(self.model.calls)
        rebound=self.adapters['writing'].rebind(ctx,self.artifact('writing'))
        self.assertEqual(rebound.data['dossier_sha256'],contract_hash(updated))
        self.assertEqual(len(self.model.calls),calls)
        updated.findings.claims[0].evidence[0].quote='Invented unsupported evidence.'
        bad=self.store.write_artifact('research',fingerprint('bad-evidence'),Output(data=updated.model_dump(mode='json')))
        ctx.inputs['research']=bad
        with self.assertRaises(RuntimeError):self.adapters['writing'].rebind(ctx,self.artifact('writing'))

    def test_plan_rebind_preserves_blueprint_with_current_script_hash(self):
        from war_workflow.graph import Context
        self.runner.run();revision=self.store.load();script=Script.model_validate(self.artifact('writing').output.data)
        script.model_calls+=1
        changed=self.store.write_artifact('writing',fingerprint('new-script-bookkeeping'),Output(data=script.model_dump(mode='json')))
        ctx=Context(self.store,revision,'direction',{'research':self.artifact('research'),'writing':changed},self.artifact('direction'))
        rebound=self.adapters['direction'].rebind(ctx,self.artifact('direction'))
        self.assertEqual(rebound.data['script_sha256'],contract_hash(script))
        self.assertEqual(rebound.data['blueprint'],self.artifact('direction').output.data['blueprint'])

    def test_action_edit_keeps_terrain_and_unit_views_reusable(self):
        from war_workflow.authoring import plan_output
        from war_workflow.graph import Context
        self.runner.run();revision=self.store.load();old=self.artifact('direction')
        plan=Plan.model_validate(old.output.data)
        plan.blueprint.scenes[0].actions[0].consequence='The crossing is easier to identify.'
        ctx=Context(self.store,revision,'direction',{},old)
        output=plan_output(ctx,plan)
        self.assertEqual(output.views['spatial'],old.output.views['spatial'])
        self.assertEqual(output.views['units'],old.output.views['units'])
        self.assertNotEqual(output.views['actions'],old.output.views['actions'])


if __name__=='__main__':unittest.main()
