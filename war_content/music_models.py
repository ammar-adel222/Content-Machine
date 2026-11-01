"""Portable source selection and independently editable audio mix controls."""
from typing import Literal
from pathlib import Path
from pydantic import Field, model_validator
from war_research.models import Model


class MusicSource(Model):
    kind: Literal['ambient','file']='ambient'
    arrangement: Literal['ambient','pulse']='ambient'
    path: str | None = None
    title: str = Field(default='Quiet atlas ambient bed',min_length=1,max_length=150)
    attribution: str = Field(default='Original demonstration bed, generated locally.',min_length=1,max_length=1000)
    offset_sec: float = Field(default=0,ge=0,le=7200,allow_inf_nan=False)
    loop: bool = True
    crossfade_sec: float = Field(default=1,ge=.01,le=5,allow_inf_nan=False)

    @model_validator(mode='after')
    def selected(self):
        if self.kind=='file' and self.arrangement!='ambient':raise ValueError('File tracks do not accept a synthesized arrangement.')
        if self.kind=='file' and not self.path:raise ValueError('File music needs a local track path.')
        if self.kind=='ambient' and self.path:raise ValueError('Ambient music does not use a file path.')
        if self.kind=='file':
            if self.title=='Quiet atlas ambient bed':self.title=Path(self.path).stem
            if self.attribution=='Original demonstration bed, generated locally.':self.attribution='User-supplied local track.'
        return self


class MixSettings(Model):
    enabled: bool = True
    music_gain_db: float = Field(default=-22,ge=-60,le=-6,allow_inf_nan=False)
    narration_gain_db: float = Field(default=0,ge=-24,le=12,allow_inf_nan=False)
    effects_gain_db: float = Field(default=0,ge=-40,le=6,allow_inf_nan=False)
    start_sec: float = Field(default=0,ge=0,le=150,allow_inf_nan=False)
    end_sec: float | None = Field(default=None,gt=0,le=150,allow_inf_nan=False)
    fade_in_sec: float = Field(default=2,ge=0,le=30,allow_inf_nan=False)
    fade_out_sec: float = Field(default=3,ge=0,le=30,allow_inf_nan=False)
    voice_duck_db: float = Field(default=-10,ge=-30,le=0,allow_inf_nan=False)
    effects_duck_db: float = Field(default=-6,ge=-24,le=0,allow_inf_nan=False)
    voice_threshold_dbfs: float = Field(default=-42,ge=-60,le=-20,allow_inf_nan=False)
    effects_threshold_dbfs: float = Field(default=-26,ge=-45,le=-10,allow_inf_nan=False)
    voice_margin_db: float = Field(default=22,ge=12,le=40,allow_inf_nan=False)
    attack_sec: float = Field(default=.04,ge=.005,le=1,allow_inf_nan=False)
    release_sec: float = Field(default=.6,ge=.05,le=3,allow_inf_nan=False)

    @model_validator(mode='after')
    def ordered(self):
        if self.end_sec is not None and self.end_sec<=self.start_sec:raise ValueError('Music end must follow its start.')
        return self


class MusicConfig(Model):
    schema_version: Literal['1.0']='1.0'
    source: MusicSource = Field(default_factory=MusicSource)
    mix: MixSettings = Field(default_factory=MixSettings)
