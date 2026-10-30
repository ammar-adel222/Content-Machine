"""Geographic contracts and small, dependency-free projection helpers."""
import math
from typing import Annotated, Literal
from pydantic import Field,model_validator
from war_research.models import Model

Number=Annotated[float,Field(allow_inf_nan=False)]
Lon=Annotated[float,Field(ge=-180,le=180,allow_inf_nan=False)]
Lat=Annotated[float,Field(ge=-80,le=80,allow_inf_nan=False)]


class Bounds(Model):
    west: Lon
    south: Lat
    east: Lon
    north: Lat

    @model_validator(mode='after')
    def ordered(self):
        if not 0<self.east-self.west<=30 or not 0<self.north-self.south<=30:
            raise ValueError('Use a local, non-antimeridian extent of at most 30 degrees per axis.')
        return self


class Polygon(Model):
    rings: list[list[tuple[Lon,Lat]]] = Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def closed(self):
        if sum(map(len,self.rings))>100_000:
            raise ValueError('Polygon is too detailed for this renderer.')
        for ring in self.rings:
            if len(ring)<4 or ring[0]!=ring[-1] or len(set(ring))<3:
                raise ValueError('Geographic rings need three vertices and a closing vertex.')
            if abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:])))<1e-12:
                raise ValueError('Geographic ring must enclose an area.')
        return self


class Place(Model):
    id: str
    name: str
    lon: Lon
    lat: Lat
    kind: Literal['settlement','island','peak','water']
    source: str


class Layer(Model):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,30}$')
    title: str
    bounds: Bounds
    width: int = Field(ge=16,le=1600)
    height: int = Field(ge=16,le=1200)
    land: list[Polygon] = Field(min_length=1,max_length=1000)
    places: list[Place] = Field(default_factory=list,max_length=30)
    relief: str = Field(pattern=r'^relief-[a-z0-9_-]+\.png$')
    zoom: int = Field(ge=1,le=13)
    min_height: Number = 0.0
    max_height: Number = 0.0


class Placement(Model):
    unit_id: str
    place_id: str | None = None
    scene_ids: list[str] = Field(min_length=1)
    claim_ids: list[str] = Field(min_length=1)
    note: str = Field(min_length=8)


class HeightGrid(Model):
    columns: int = Field(ge=2,le=200)
    rows: int = Field(ge=2,le=200)
    values: list[Annotated[float,Field(ge=-500,le=9000,allow_inf_nan=False)]] = Field(max_length=40_000)

    @model_validator(mode='after')
    def complete(self):
        if len(self.values)!=self.columns*self.rows:raise ValueError('Height grid dimensions do not match its samples.')
        return self


class TacticalFeature(Model):
    id: str
    name: str
    kind: Literal['stream','village','ridge']
    points: list[tuple[Lon,Lat]] = Field(min_length=1,max_length=5000)
    source: str
    period_status: Literal['modern_context','historic_feature_modern_position']

    @model_validator(mode='after')
    def geometry(self):
        if self.kind=='stream' and len(self.points)<2:raise ValueError('Stream needs at least two positions.')
        return self


class Battlefield(Model):
    schema_version: Literal['1.0']='1.0'
    mode: Literal['battlefield']='battlefield'
    layer: Layer
    heights: HeightGrid
    features: list[TacticalFeature] = Field(max_length=100)
    exaggeration: float = Field(default=5.0,ge=1,le=8,allow_inf_nan=False)
    sources: list[dict]
    notes: list[str]

    @model_validator(mode='after')
    def features_in_bounds(self):
        b=self.layer.bounds
        if len({f.id for f in self.features})!=len(self.features):raise ValueError('Duplicate terrain feature IDs.')
        if any(not b.west<=lon<=b.east or not b.south<=lat<=b.north for f in self.features for lon,lat in f.points):
            raise ValueError('Terrain features must stay within the battlefield extent.')
        return self


class Geography(Model):
    schema_version: Literal['1.0']='1.0'
    projection: Literal['local_equirectangular']='local_equirectangular'
    region: str
    parent_scene_sha256: str
    layers: list[Layer] = Field(min_length=1,max_length=2)
    placements: list[Placement] = Field(default_factory=list,max_length=30)
    sources: list[dict]
    omitted_actions: list[str]
    notes: list[str]

    @model_validator(mode='after')
    def unique_layers(self):
        if len({l.id for l in self.layers})!=len(self.layers) or len({l.relief for l in self.layers})!=len(self.layers):
            raise ValueError('Geographic layer IDs and relief filenames must be unique.')
        return self


def projection(bounds,width,height):
    cos=math.cos(math.radians((bounds.north+bounds.south)/2))
    span_x=(bounds.east-bounds.west)*cos
    span_y=bounds.north-bounds.south
    scale=min(width/span_x,height/span_y)
    return cos,scale,(width-span_x*scale)/2,(height-span_y*scale)/2


def project(lon,lat,bounds,width,height):
    cos,scale,x,y=projection(bounds,width,height)
    return x+(lon-bounds.west)*cos*scale,y+(bounds.north-lat)*scale


def unproject(x,y,bounds,width,height):
    cos,scale,dx,dy=projection(bounds,width,height)
    return bounds.west+(x-dx)/(cos*scale),bounds.north-(y-dy)/scale


def tile_position(lon,lat,zoom):
    n=2**zoom
    return (lon+180)/360*n,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n


def extract_land(geojson,bounds):
    """Keep intersecting polygons intact; rendering clips them at the viewport."""
    features=geojson.get('features',[]) if geojson.get('type')=='FeatureCollection' else [geojson]
    polygons=[]
    for feature in features:
        geometry=feature.get('geometry',feature)
        if geometry.get('type') not in ('Polygon','MultiPolygon'):
            raise ValueError('Coastline input must contain Polygon or MultiPolygon geometry.')
        ringsets=[geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
        for rings in ringsets:
            polygon=Polygon(rings=rings)
            ring=polygon.rings[0]
            xs,ys=zip(*ring)
            if max(xs)>=bounds.west and min(xs)<=bounds.east and max(ys)>=bounds.south and min(ys)<=bounds.north:
                polygons.append(polygon)
    if not polygons:
        raise ValueError('No land polygons intersect the requested map extent.')
    return polygons
