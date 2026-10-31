from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import Field, JsonValue, model_validator
from war_research.models import Model

Stage = Literal['research','writing','script_review','direction','plan_review','narration',
                'terrain','assets','timing','effects','music_source','mix','visual_review',
                'audio_review','picture','mux','final_review']
EditKind = Literal['research','script','narration','route','terrain','unit_design',
                   'camera','caption','format','sound_effect','music_track','music_mix','mix_levels']


class Limits(Model):
    model_attempts: int = Field(default=32,ge=0,le=500)
    search_requests: int = Field(default=12,ge=0,le=500)
    tts_requests: int = Field(default=20,ge=0,le=500)


class Edit(Model):
    request_id: str = Field(default_factory=lambda:uuid4().hex,pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    parent_revision: str
    kind: EditKind
    patch: dict[str,JsonValue] = Field(default_factory=dict)
    notes: str = Field(default='',max_length=5000)
    scene_ids: list[str] = Field(default_factory=list,max_length=20)
    object_ids: list[str] = Field(default_factory=list,max_length=30)

    @model_validator(mode='after')
    def meaningful(self):
        if not self.patch and not self.notes:raise ValueError('An edit needs settings or revision notes.')
        return self


class Output(Model):
    data: dict[str,JsonValue]
    views: dict[str,JsonValue] = Field(default_factory=dict)
    files: dict[str,str] = Field(default_factory=dict)
    review: Literal['pass','revise'] | None = None
    issues: list[str] = Field(default_factory=list,max_length=30)


class Artifact(Model):
    id: str = Field(pattern=r'^[a-f0-9]{64}$')
    stage: Stage
    version: str = Field(min_length=1,max_length=100)
    key: str = Field(pattern=r'^[a-f0-9]{64}$')
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    output: Output
    view_hashes: dict[str,str]
    file_hashes: dict[str,str]


class Revision(Model):
    id: str = Field(default_factory=lambda:uuid4().hex)
    parent: str | None = None
    created_at: datetime = Field(default_factory=lambda:datetime.now(timezone.utc))
    edit: Edit | None = None
    params: dict[Stage,dict[str,JsonValue]] = Field(default_factory=dict)
    instructions: dict[Stage,dict[str,JsonValue]] = Field(default_factory=dict)
    artifacts: dict[Stage,str] = Field(default_factory=dict)
    drafts: dict[Stage,str] = Field(default_factory=dict)
    dirty: list[Stage] = Field(default_factory=list)
    status: Literal['pending','running','needs_input','quota_wait','awaiting_review','approved','superseded']='pending'
    blocked_stage: Stage | None = None
    issues: list[str] = Field(default_factory=list)
    executed: list[Stage] = Field(default_factory=list)
    reused: list[Stage] = Field(default_factory=list)
    repairs: dict[Stage,int] = Field(default_factory=dict)
    approval: dict[str,str] | None = None
