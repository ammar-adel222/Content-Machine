"""Live narration and deterministic timing adapters; no visual or sound regeneration."""
import os
from pathlib import Path
from war_narration.agent import generate, save, audio_timing, alignment, verify, atomic
from war_narration.models import Narration, NarrationRequest
from war_narration.provider import GeminiSpeech, SpeechQuotaError
from war_narration.timing import align_plan, srt
from war_writer.models import Script
from war_writer.agent import fingerprint as contract_hash
from war_director.models import Plan
from war_research.models import Dossier
from war_reviewer.models import QualityReview
from .graph import Adapter
from .models import Output
from .planner import fingerprint
from .store import WorkflowError, BudgetExhausted


def config(ctx,script):
    previous=ctx.previous.output.data.get('narration',{}).get('request',{}) if ctx.previous else {}
    edit=ctx.revision.edit
    values={'model':os.environ.get('GEMINI_TTS_MODEL','gemini-3.8-flash-tts'),
            'voice':os.environ.get('GEMINI_TTS_VOICE','Charon')}|previous
    applied_settings=ctx.previous.output.data.get('request_settings',{}) if ctx.previous else {}
    patch={key:value for key,value in ctx.params.items() if key not in applied_settings or applied_settings[key]!=value}
    values|=patch
    scenes=ctx.instructions.get('scene_ids',[]);phrases=ctx.instructions.get('object_ids',[])
    if (scenes or phrases) and edit and edit.kind=='narration' and {'voice','model','notes'}&set(edit.patch):
        raise WorkflowError('Voice/model/global style settings need an unscoped narration edit.')
    chunks=[(s.id,f'{s.id}.p{i}') for s in script.draft.scenes for i,p in enumerate(s.phrases,1)]
    if set(scenes)-{s for s,p in chunks} or set(phrases)-{p for s,p in chunks}:
        raise WorkflowError('Narration edit references an unknown scene or phrase.')
    already=ctx.previous.output.data.get('applied_edit') if ctx.previous else None
    notes=ctx.instructions.get('notes','') if edit and edit.kind=='narration' and edit.request_id!=already else ''
    if not notes:return NarrationRequest.model_validate(values)
    if scenes or phrases:
        if not notes:raise WorkflowError('Scoped narration edits need delivery notes; voice/model settings apply globally.')
        overrides=dict(values.get('phrase_notes',{}))
        for scene,phrase in chunks:
            if scene in scenes or phrase in phrases:overrides[phrase]=notes
        values['phrase_notes']=overrides
    elif notes:values['notes']=' '.join(filter(None,[values.get('notes',''),notes]))
    return NarrationRequest.model_validate(values)


def output(ctx,narration,script):
    verify(narration,script)
    manifest=save(narration,ctx.output_dir)
    measured=audio_timing(narration)
    path=ctx.output_dir/('audio-timing-'+fingerprint(measured)+'.json');atomic(path,measured.model_dump_json(indent=2).encode())
    edit=ctx.revision.edit
    applied=edit.request_id if edit and edit.kind=='narration' else ctx.previous.output.data.get('applied_edit') if ctx.previous else None
    return Output(data={'narration':narration.model_dump(mode='json'),'duration':narration.frames/narration.sample_rate,'present':True,'applied_edit':applied,'request_settings':dict(ctx.params)},
        files={'wave':narration.wave,'manifest':str(manifest),'audio_timing':str(path)}|
              {c.phrase_id:c.file for c in narration.clips},
        views={'waveform':narration.sha256,'timing':{'audio':measured.model_dump(mode='json'),'alignment':alignment(narration)}})


def adapters(provider_factory=None):
    provider_factory=provider_factory or (lambda:GeminiSpeech(os.environ.get('GEMINI_API_KEY','')))
    defaults={'model':os.environ.get('GEMINI_TTS_MODEL','gemini-3.8-flash-tts'),
              'voice':os.environ.get('GEMINI_TTS_VOICE','Charon')}
    def narrate(ctx):
        script=Script.model_validate(ctx.inputs['writing'].output.data)
        try:narration=generate(script,ctx.output_dir,ctx.store.root/'speech-cache',provider_factory,
                               config(ctx,script),lambda:ctx.consume('tts_requests'))
        except SpeechQuotaError as error:raise BudgetExhausted(str(error)) from None
        return output(ctx,narration,script)
    def rebind(ctx,cached):
        script=Script.model_validate(ctx.inputs['writing'].output.data)
        narration=Narration.model_validate(cached.output.data['narration']).model_copy(update={
            'script_sha256':contract_hash(script),'requests':0,'reused':len(cached.output.data['narration']['clips'])})
        return output(ctx,narration,script)
    def timing(ctx):
        if ctx.params or ctx.instructions:raise WorkflowError('Timing is measured automatically; edit the script, delivery or action anchors instead.')
        script=Script.model_validate(ctx.inputs['writing'].output.data)
        narration=Narration.model_validate(ctx.inputs['narration'].output.data['narration'])
        plan=Plan.model_validate(ctx.inputs['direction'].output.data)
        dossier=Dossier.model_validate(ctx.inputs['research'].output.data)
        reviewed=QualityReview.model_validate(ctx.store.read_artifact('plan_review',ctx.revision.artifacts['plan_review']).output.data)
        if reviewed.status!='pass' or reviewed.artifact_sha256!=contract_hash(plan.blueprint):
            raise WorkflowError('Timing needs the current passing blueprint review.')
        plan=plan.model_copy(update={'review':reviewed})
        timed,clock=align_plan(dossier,script,plan,narration)
        path=ctx.output_dir/('timed-plan-'+fingerprint(timed)+'.json');atomic(path,timed.model_dump_json(indent=2).encode())
        subtitle=ctx.output_dir/('captions-'+fingerprint(clock['phrases'])+'.srt');atomic(subtitle,srt(clock['phrases']).encode())
        return Output(data=clock|{'plan':timed.model_dump(mode='json')},files={'plan':str(path),'captions':str(subtitle)},
            views={'duration':clock['duration'],'visual':{'phrases':clock['phrases'],'scenes':clock['scenes'],'actions':clock['actions']},
                   'effects':{'duration':clock['duration'],'actions':clock['actions']}},issues=timed.issues)
    return {'narration':Adapter(narrate,'gemini-speech-v2-'+fingerprint(defaults)[:16],rebind,
                               lambda ctx:config(ctx,Script.model_validate(ctx.inputs['writing'].output.data)).model_dump(mode='json')),
            'timing':Adapter(timing,'measured-clock-v2-reviewed-plan')}
