"""Compile real coastlines and DEM relief into a new, source-tracked playback bundle."""
import argparse
import hashlib
import json
import math
import shutil
from array import array
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from uuid import uuid4
from zipfile import ZipFile
from war_writer.agent import fingerprint
from .geodata import Bounds,Geography,Layer,Place,Placement,extract_land,project,projection,tile_position,unproject
from .play import WEB,ready

COUNTRIES='https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries.geojson'
GAZETTEER='https://download.geonames.org/export/dump/FK.zip'
DEM='https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def download(url,path,limit=50_000_000):
    path=Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        with urlopen(Request(url,headers={'User-Agent':'ContentMachine/0.4'}),timeout=60) as response:
            data=response.read(limit+1)
        if len(data)>limit:
            raise ValueError('Geographic source exceeds the download limit.')
        temporary=path.with_name(uuid4().hex+'.tmp')
        try:
            temporary.write_bytes(data);temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if path.stat().st_size>limit:
        raise ValueError('Cached geographic source exceeds the size limit.')
    return path


def source(path,url,role,license):
    return {'role':role,'url':url,'license':license,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'retrieved_at':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()}


def gazetteer(path,ids):
    wanted=set(ids);result=[]
    with ZipFile(path) as archive:
        info=archive.getinfo('FK.txt')
        if info.file_size>10_000_000:raise ValueError('Gazetteer is too large.')
        for row in archive.read(info).decode('utf-8').splitlines():
            c=row.split('\t')
            if c[0] not in wanted:continue
            kind={'P':'settlement','H':'water'}.get(c[6],'island' if c[7]=='ISL' else 'peak')
            result.append(Place(id=c[0],name=c[1],lon=float(c[5]),lat=float(c[4]),kind=kind,
                                source='https://www.geonames.org/'+c[0]+'/'))
    if {p.id for p in result}!=wanted:raise ValueError('Required gazetteer places are missing.')
    return result


def tile_keys(bounds,zoom,maximum=64):
    left,top=tile_position(bounds.west,bounds.north,zoom)
    right,bottom=tile_position(bounds.east,bounds.south,zoom)
    keys=[(x,y) for x in range(int(left),int(right)+1) for y in range(int(top),int(bottom)+1)]
    if len(keys)>maximum:raise ValueError('Elevation tile budget exceeded; use a smaller extent or lower zoom.')
    return keys


def decode_height(rgb):
    return rgb[0]*256+rgb[1]+rgb[2]/256-32768


def relief(layer,cache,target,fetch=download,height_grid=None):
    try:
        from PIL import Image,ImageFilter
    except ImportError:
        raise RuntimeError('Install geography support: python -m pip install -e ".[geography]"') from None
    keys=tile_keys(layer.bounds,layer.zoom)
    def get(key):
        x,y=key;url=DEM.format(z=layer.zoom,x=x,y=y)
        path=fetch(url,Path(cache)/f'terrarium-{layer.zoom}-{x}-{y}.png',2_000_000)
        with Image.open(path) as original:
            if original.size!=(256,256):raise ValueError('Unexpected elevation tile dimensions.')
            image=original.convert('RGB')
        return key,image,source(path,url,'elevation','Mapzen Terrain Tiles; USGS SRTM/GMTED2010 and NOAA ETOPO1; see attribution')
    with ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(get,keys))
    pixels={key:image.load() for key,image,_ in records}
    width,height=layer.width,layer.height
    heights=array('f',[0])*(width*height)
    lon_samples=[unproject(x+.5,0,layer.bounds,width,height)[0] for x in range(width)]
    x_samples=[tile_position(lon,0,layer.zoom)[0]*256 for lon in lon_samples]
    minimum,maximum=0,0
    for y in range(height):
        lat=unproject(0,y+.5,layer.bounds,width,height)[1]
        if not layer.bounds.south<=lat<=layer.bounds.north:continue
        py=tile_position(0,lat,layer.zoom)[1]*256;ty=int(py)//256;iy=int(py)%256
        for x,px in enumerate(x_samples):
            if not layer.bounds.west<=lon_samples[x]<=layer.bounds.east:continue
            elevation=decode_height(pixels[int(px)//256,ty][int(px)%256,iy])
            if elevation<=-32767:raise ValueError('Elevation data contains a void; do not invent relief.')
            heights[y*width+x]=elevation;minimum=min(minimum,elevation);maximum=max(maximum,elevation)
    image=Image.new('RGB',(width,height));out=image.load()
    _,scale,_,_=projection(layer.bounds,width,height)
    meters=111320/scale
    # NW light, real height gradients. Exaggeration improves low relief readability.
    for y in range(height):
        for x in range(width):
            index=y*width+x;h=heights[index]
            dx=(heights[y*width+min(width-1,x+1)]-heights[y*width+max(0,x-1)])/(2*meters)
            dy=(heights[min(height-1,y+1)*width+x]-heights[max(0,y-1)*width+x])/(2*meters)
            nx,ny=-dx*2.5,-dy*2.5
            illumination=(-.5*nx-.5*ny+.7071)/math.sqrt(nx*nx+ny*ny+1)
            shade=max(.48,min(1.16,.7+.42*illumination))
            high=min(1,max(0,h)/750)
            base=(222-65*high,219-62*high,183-46*high)
            out[x,y]=tuple(round(max(0,min(255,value*shade))) for value in base)
    image.filter(ImageFilter.GaussianBlur(.65)).save(target)
    layer.min_height=float(round(minimum,1));layer.max_height=float(round(maximum,1))
    if height_grid is not None:
        columns,rows=height_grid['columns'],height_grid['rows']
        values=[]
        for row in range(rows):
            for column in range(columns):
                lon=layer.bounds.west+(layer.bounds.east-layer.bounds.west)*column/(columns-1)
                lat=layer.bounds.north-(layer.bounds.north-layer.bounds.south)*row/(rows-1)
                px,py=project(lon,lat,layer.bounds,width,height)
                ix=max(0,min(width-1,int(px)));iy=max(0,min(height-1,int(py)))
                values.append(round(heights[iy*width+ix],1))
        height_grid['values']=values
    return [record for _,_,record in records]


def validate_placements(geography,scene,build):
    places={p.id:p for layer in geography.layers for p in layer.places}
    forces={f['id']:set(f['claim_ids']) for f in scene['blueprint']['forces']}
    scenes={s['scene_id'] for s in scene['scenes']}
    for placement in geography.placements:
        if placement.unit_id not in forces or not set(placement.scene_ids)<=scenes:
            raise ValueError('Geographic placement references unknown units/scenes.')
        if not set(placement.claim_ids)<=forces[placement.unit_id]:
            raise ValueError('Geographic placement claims must come from the original force.')
        if placement.place_id and placement.place_id not in places:
            raise ValueError('Geographic placement references an unknown place.')
        if placement.place_id:
            quotes=[b['evidence_quote'] for b in build['manifest']['bindings'] if b['object_id']==placement.unit_id and b['claim_id'] in placement.claim_ids]
            if not any(places[placement.place_id].name.casefold() in quote.casefold() for quote in quotes):
                raise ValueError('No supplied evidence links the force to that named place.')


def compile_bundle(bundle,layers,sources,region,cache,root,placements=None,render_relief=relief):
    bundle=Path(bundle)
    if not ready(bundle):raise ValueError('Choose a ready generated scene bundle.')
    scene=json.loads((bundle/'scene.json').read_text(encoding='utf-8'))
    build=json.loads((bundle/'content.json').read_text(encoding='utf-8'))
    if 'blueprint' not in scene or 'manifest' not in build:
        raise ValueError('Geographic compilation needs an agent-generated scene; terrain studies use a separate format.')
    geography=Geography(region=region,parent_scene_sha256=digest(scene),layers=layers,sources=sources,
        placements=placements or [],omitted_actions=[a['id'] for s in scene['blueprint']['scenes'] for a in s['actions'] if a['kind'] in ('move','withdraw')],
        notes=['Coastlines are generalized geographic data, not a survey.',
               'Relief uses measured elevation, NW lighting and 2.5× shading exaggeration.',
               'Modern coast/height data is background context, not a reconstruction of 1982 roads or positions.',
               'Legacy schematic terrain and troop routes are not drawn on the geographic map.',
               'Place-linked force symbols are area callouts, not exact deployment coordinates.'])
    validate_placements(geography,scene,build)
    directory=Path(root)/uuid4().hex;directory.mkdir(parents=True)
    for layer in geography.layers:
        geography.sources.extend(render_relief(layer,cache,directory/layer.relief))
    scene['geography']=geography.model_dump(mode='json')
    build['geography_sha256']=fingerprint(geography)
    for path in WEB.iterdir():
        if path.is_file():shutil.copyfile(path,directory/path.name)
    shutil.copyfile(bundle/'pixi.min.js',directory/'pixi.min.js')
    (directory/'scene.json').write_text(json.dumps(scene,indent=2,ensure_ascii=False),encoding='utf-8')
    (directory/'content.json').write_text(json.dumps(build,indent=2,ensure_ascii=False),encoding='utf-8')
    (directory/'geography.json').write_text(geography.model_dump_json(indent=2),encoding='utf-8')
    (directory/'report.md').write_text('# Geographic map preview\n\n'+region+'\n\n'+
        '\n'.join('- '+note for note in geography.notes)+'\n\n## Sources\n\n'+
        '\n'.join('- '+r['role']+': '+r['url'] for r in geography.sources)+
        '\n\nCredits: Natural Earth; GeoNames (CC BY); Mapzen Terrain Tiles; USGS; NOAA.\n',encoding='utf-8')
    return directory


def falklands(cache):
    cache=Path(cache)
    countries=download(COUNTRIES,cache/'natural-earth-countries-v5.1.2.geojson')
    data=json.loads(countries.read_text(encoding='utf-8'))
    coast={'type':'FeatureCollection','features':[f for f in data['features'] if f['properties'].get('ADM0_A3')=='FLK']}
    names=download(GAZETTEER,cache/'FK.zip',5_000_000)
    places=gazetteer(names,['3426691','3426652','3426669','3426908','3426730','3426739','3426638','3427061'])
    bounds=Bounds(west=-61.55,south=-52.55,east=-57.35,north=-50.95)
    detail=Bounds(west=-58.2,south=-51.79,east=-57.65,north=-51.61)
    layers=[Layer(id='overview',title='Falkland Islands',bounds=bounds,width=1200,height=850,
        land=extract_land(coast,bounds),places=[p for p in places if p.id in ('3426691','3426652','3426739','3426638','3427061')],relief='relief-overview.png',zoom=8),
        Layer(id='stanley',title='Stanley and surrounding hills',bounds=detail,width=1200,height=500,
        land=extract_land(coast,detail),places=[p for p in places if p.id in ('3426691','3426669','3426908','3426730')],relief='relief-stanley.png',zoom=10)]
    sources=[source(countries,COUNTRIES,'coastline','Natural Earth public domain; 1:10 million; v5.1.2'),
             source(names,GAZETTEER,'place coordinates','GeoNames CC BY; gazetteer entries, not troop locations')]
    return layers,sources


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    p.add_argument('--cache',type=Path,default=Path('output/geography/cache'))
    p.add_argument('--output',type=Path,default=Path('output/content'))
    p.add_argument('--geojson',type=Path,help='Use a custom local GeoJSON coast/land file instead of the Falklands example')
    p.add_argument('--bbox',type=float,nargs=4,metavar=('WEST','SOUTH','EAST','NORTH'))
    p.add_argument('--name',help='Map title; defaults to the example region or custom filename')
    p.add_argument('--zoom',type=int,default=8,help='DEM zoom for a custom map')
    p.add_argument('--placements',type=Path,help='Optional source-checked force/place callouts as a JSON list')
    args=p.parse_args(argv)
    try:
        if not ready(args.bundle):raise ValueError('Choose a ready generated scene bundle.')
        region=args.name or (args.geojson.stem if args.geojson else 'Falkland Islands')
        if args.geojson:
            if not args.bbox:raise ValueError('Custom geography requires --bbox WEST SOUTH EAST NORTH.')
            bounds=Bounds(**dict(zip(('west','south','east','north'),args.bbox)))
            data=json.loads(args.geojson.read_text(encoding='utf-8'))
            layers=[Layer(id='overview',title=region,bounds=bounds,width=1200,height=850,
                land=extract_land(data,bounds),relief='relief-overview.png',zoom=args.zoom)]
            sources=[source(args.geojson,args.geojson.resolve().as_uri(),'user-supplied land','User-supplied data; verify its license')]
        else:
            if args.bbox:raise ValueError('--bbox requires a custom --geojson file.')
            scene=json.loads((args.bundle/'scene.json').read_text(encoding='utf-8'))
            if 'falkland' not in scene.get('topic','').lower():raise ValueError('The example profile is for the Falklands; supply --geojson for another region.')
            layers,sources=falklands(args.cache)
        placements=[Placement.model_validate(p) for p in json.loads(args.placements.read_text(encoding='utf-8'))] if args.placements else []
        if not args.geojson and not args.placements:
            scene=json.loads((args.bundle/'scene.json').read_text(encoding='utf-8'))
            build=json.loads((args.bundle/'content.json').read_text(encoding='utf-8'))
            for force in scene['blueprint']['forces']:
                binding=next((b for b in build['manifest']['bindings'] if b['brief']['category']=='unit' and b['object_id']==force['id'] and 'stanley' in b['evidence_quote'].lower()),None)
                if binding:
                    placements.append(Placement(unit_id=force['id'],place_id='3426691',scene_ids=[scene['scenes'][0]['scene_id']],claim_ids=[binding['claim_id']],note='Invasion / garrison: Stanley area callouts'))
                elif force['kind']=='fleet':
                    ids=[s['scene_id'] for s in scene['blueprint']['scenes'] if any(a['unit_id']==force['id'] for a in s['actions'])]
                    if ids:placements.append(Placement(unit_id=force['id'],scene_ids=ids,claim_ids=force['claim_ids'],note='Naval dispatch narrated; exact track not supplied'))
        directory=compile_bundle(args.bundle,layers,sources,region,args.cache,args.output,placements=placements)
        print(f'Geographic map: {directory}',flush=True)
        return 0
    except (OSError,ValueError,RuntimeError) as error:
        print('Geography failed:',str(error));return 1


if __name__=='__main__':raise SystemExit(main())
