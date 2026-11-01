from typing import Literal, Annotated
from pydantic import Field
from war_research.models import Model


class NarrationRequest(Model):
    model: Literal['gemini-3.8-flash-tts','gemini-3.8-flash-lite-tts']='gemini-3.8-flash-tts'
    voice: str = Field(default='Charon',pattern=r'^[A-Za-z]{2,40}$')
    trim_silence: bool = False
    notes: str = Field(default='',max_length=3000)
    phrase_notes: dict[str,Annotated[str,Field(max_length=3000)]] = Field(default_factory=dict)
    max_requests: int = Field(default=20,ge=1,le=60)


class Clip(Model):
    phrase_id: str
    scene_id: str
    text: str
    direction: str
    key: str
    file: str
    sha256: str
    frames: int = Field(gt=0)
    pause_frames: int = Field(ge=0)
    start_frame: int = Field(ge=0)


class Narration(Model):
    schema_version: Literal['1.0']='1.0'
    script_sha256: str
    request: NarrationRequest
    sample_rate: Literal[24000]=24000
    clips: list[Clip]
    frames: int = Field(gt=0)
    wave: str
    sha256: str
    requests: int = Field(ge=0)
    reused: int = Field(ge=0)
    warnings: list[str]
