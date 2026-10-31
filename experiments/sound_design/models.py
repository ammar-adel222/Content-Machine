from typing import Literal
import math
from pydantic import Field, model_validator
from war_research.models import Model


class Brief(Model):
    concept: str = Field(pattern=r'^[a-z][a-z0-9_]{1,49}$')
    description: str = Field(min_length=20, max_length=700)
    duration: float = Field(ge=.25, le=12, allow_inf_nan=False)
    loop: bool = False


class Layer(Model):
    name: str = Field(min_length=2,max_length=60)
    source: Literal['noise','sine','triangle']
    start: float = Field(default=0,ge=0,le=12,allow_inf_nan=False)
    duration: float = Field(ge=.02,le=12,allow_inf_nan=False)
    gain_db: float = Field(ge=-50,le=-3,allow_inf_nan=False)
    frequency_start: float = Field(default=120,ge=20,le=12000,allow_inf_nan=False)
    frequency_end: float = Field(default=120,ge=20,le=12000,allow_inf_nan=False)
    highpass: float = Field(default=30,ge=10,le=8000,allow_inf_nan=False)
    lowpass: float = Field(default=12000,ge=50,le=16000,allow_inf_nan=False)
    attack: float = Field(default=.005,ge=.001,le=2,allow_inf_nan=False)
    release: float = Field(default=.02,ge=.002,le=4,allow_inf_nan=False)
    decay: float = Field(default=0,ge=0,le=120,allow_inf_nan=False)
    repeat_every: float = Field(default=0,ge=0,le=12,allow_inf_nan=False)
    jitter: float = Field(default=0,ge=0,le=.2,allow_inf_nan=False)
    tremolo_hz: float = Field(default=0,ge=0,le=35,allow_inf_nan=False)
    tremolo_depth: float = Field(default=0,ge=0,le=1,allow_inf_nan=False)
    pan: float = Field(default=0,ge=-.5,le=.5,allow_inf_nan=False)

    @model_validator(mode='after')
    def useful(self):
        if self.highpass>=self.lowpass:raise ValueError('Highpass must be below lowpass.')
        if self.attack+self.release>self.duration:raise ValueError('Attack plus release must fit layer duration.')
        if 0<self.repeat_every<.06:raise ValueError('Repeated hits must be at least 60ms apart.')
        if not self.repeat_every and self.jitter:raise ValueError('Jitter requires a repeating layer.')
        return self


class Recipe(Model):
    schema_version: Literal['1.0']='1.0'
    label: str = Field(min_length=2,max_length=70)
    explanation: str = Field(min_length=20,max_length=1000)
    duration: float = Field(ge=.25,le=12,allow_inf_nan=False)
    loop: bool
    seed: int = Field(ge=0,le=2147483647)
    layers: list[Layer] = Field(min_length=1,max_length=12)

    @model_validator(mode='after')
    def bounded(self):
        work=0
        for layer in self.layers:
            if layer.start+layer.duration>self.duration+1e-6:raise ValueError('First layer event must fit recipe duration.')
            events=1 if not layer.repeat_every else math.ceil((self.duration-layer.start)/layer.repeat_every)
            work+=events*layer.duration
        if work>80:raise ValueError('Recipe exceeds 80 voice-seconds of synthesis work.')
        return self
