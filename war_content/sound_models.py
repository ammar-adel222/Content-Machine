"""Editable, versioned sound cues independent of visual assets and TTS."""
from typing import Literal
from pydantic import Field, model_validator
from war_research.models import Model

Movement = Literal['footsteps', 'heavy_steps', 'hooves', 'tracks', 'wheels', 'none']
Effect = Literal['footsteps', 'heavy_steps', 'hooves', 'tracks', 'wheels', 'cannon', 'musket', 'rifle', 'clash']


class SoundProfile(Model):
    movement: Movement
    gain_db: float = Field(default=-14, ge=-40, le=-6, allow_inf_nan=False)


class SpotSound(Model):
    action_id: str
    time: float = Field(ge=0, le=150, allow_inf_nan=False)
    effect: Literal['cannon', 'musket', 'rifle', 'clash']
    gain_db: float = Field(default=-18, ge=-40, le=-6, allow_inf_nan=False)


class Sample(Model):
    path: str = Field(min_length=1)
    attribution: str = Field(min_length=1, max_length=500)


class SoundConfig(Model):
    profiles: dict[str, SoundProfile] = Field(default_factory=dict)
    spots: list[SpotSound] = Field(default_factory=list, max_length=100)
    samples: dict[Effect, Sample] = Field(default_factory=dict)


class SoundCue(Model):
    unit_id: str
    action_id: str
    effect: Effect
    start: float = Field(ge=0, le=150, allow_inf_nan=False)
    end: float = Field(gt=0, le=150, allow_inf_nan=False)
    gain_db: float = Field(ge=-50, le=-6, allow_inf_nan=False)
    pan_start: float = Field(ge=-.5, le=.5, allow_inf_nan=False)
    pan_end: float = Field(ge=-.5, le=.5, allow_inf_nan=False)
    seed: int = Field(ge=0)
    subgroup: int = Field(ge=0, le=11)
    loop: bool = True

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Sound cue must have positive duration.')
        return self


class SoundPlan(Model):
    schema_version: Literal['1.0'] = '1.0'
    scene_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    duration: float = Field(gt=0, le=150, allow_inf_nan=False)
    cues: list[SoundCue] = Field(default_factory=list, max_length=1200)
    unresolved_units: list[str] = Field(default_factory=list)
    omitted_actions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def bounded(self):
        if any(c.end > self.duration + 1e-8 for c in self.cues):
            raise ValueError('Sound cue extends beyond the video.')
        return self
