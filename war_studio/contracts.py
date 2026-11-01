"""Studio request contracts; credentials are never accepted from the browser."""
from typing import Literal
from pydantic import Field
from war_research.models import Model

Platform=Literal['youtube','instagram','tiktok']
PLATFORMS=('youtube','instagram','tiktok')
PUBLISH_POLICY='instagram-temp-https-tiktok-inbox-no-label-v2'


class NewVideo(Model):
    topic: str = Field(default='',max_length=300)
    kind: Literal['battle','war']='battle'
    format: Literal['portrait','landscape']='portrait'
    terrain: Literal['battlefield','schematic']='battlefield'
    seconds: int = Field(default=105,ge=90,le=120)


class EditVideo(Model):
    revision: str
    kind: Literal['research','script','narration','route','terrain','unit_design','camera','caption','sound_effect','music_track','music_mix','mix_levels']
    notes: str = Field(min_length=1,max_length=5000)
    patch: dict = Field(default_factory=dict)
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')


class Post(Model):
    title: str = Field(default='',max_length=300)
    description: str = Field(default='',max_length=5000)
    hashtags: str = Field(default='',max_length=1000)


class Metadata(Model):
    revision: str
    posts: dict[Platform,Post]
    selected: list[Platform] = Field(max_length=3)
    youtube_privacy: Literal['private','unlisted','public']='private'
    tiktok_privacy: str = Field(default='',max_length=50)
    disable_comment: bool=True
    disable_duet: bool=True
    disable_stitch: bool=True


class Confirm(Model):
    ticket: str = Field(pattern=r'^[a-f0-9]{32}$')
    consent: Literal[True]


class RevisionRequest(Model):
    revision: str
