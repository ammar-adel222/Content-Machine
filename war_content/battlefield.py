"""Source-based tactical terrain study, separate from a publishable battle script."""
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from .geodata import Battlefield,Bounds,HeightGrid,Layer,Polygon,TacticalFeature
from .geography import download,relief,source
from .play import WEB

ATLAS='https://dhc.westpoint.edu/atlases/'
MAP='https://wpvip.westpoint.edu/dhc/wp-content/uploads/sites/6/2025/01/Nap23-01.jpg'
NAMES='https://download.geonames.org/export/dump/CZ.zip'
OVERPASS='https://overpass-api.de/api/interpreter'
QUERY='[out:json][timeout:30];way["waterway"]["name"~"Říčka|Goldbach"](49.09,16.69,49.19,16.82);out geom;'


def stream_features(data,bounds):
    features=[]
    for way in data.get('elements',[]):
        current=[];part=0
        for vertex in way.get('geometry',[])+[{'lon':180,'lat':80}]:
            lon,lat=vertex['lon'],vertex['lat']
            if bounds.west<=lon<=bounds.east and bounds.south<=lat<=bounds.north:
                current.append((lon,lat));continue
            if len(current)>=2:
                features.append(TacticalFeature(id=f"stream-{way['id']}-{part}",name='Goldbach / Ricka',kind='stream',
                    points=current,source='https://www.openstreetmap.org/way/'+str(way['id']),period_status='modern_context'))
                part+=1
            current=[]
    if not features:raise ValueError('No source stream geometry in the battlefield extent.')
    return features


def village_features(path):
    identities={'3064307':'Telnitz','3065618':'Sokolnitz','3067716':'Pratzen','3073472':'Kobelnitz','3067836':'Puntowitz'}
    features=[]
    with ZipFile(path) as archive:
        info=archive.getinfo('CZ.txt')
        if info.file_size>30_000_000:raise ValueError('Gazetteer exceeds its size budget.')
        for row in archive.read(info).decode('utf-8').splitlines():
            c=row.split('\t')
            if c[0] in identities:
                features.append(TacticalFeature(id='village-'+c[0],name=identities[c[0]],kind='village',points=[(float(c[5]),float(c[4]))],
                    source='https://www.geonames.org/'+c[0]+'/',period_status='historic_feature_modern_position'))
    if len(features)!=len(identities):raise ValueError('Required battlefield villages are absent from the gazetteer.')
    return features


def compile_study(cache,root,render_relief=relief):
    pixi=Path(__file__).resolve().parents[1]/'renderer/node_modules/pixi.js/dist/pixi.min.js'
    if not pixi.is_file():raise ValueError('Install renderer dependencies before compiling the study.')
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    names=download(NAMES,cache/'CZ.zip',15_000_000)
    stream=cache/'goldbach-osm.json'
    if not stream.exists():
        request=Request(OVERPASS,data=urlencode({'data':QUERY}).encode(),headers={'User-Agent':'ContentMachine/0.5'})
        with urlopen(request,timeout=60) as response:data=response.read(5_000_001)
        if len(data)>5_000_000:raise ValueError('Stream data exceeds its size budget.')
        stream.write_bytes(data)
    if stream.stat().st_size>5_000_000:raise ValueError('Cached stream data exceeds its size budget.')
    bounds=Bounds(west=16.705,south=49.092,east=16.795,north=49.188)
    land=Polygon(rings=[[(bounds.west,bounds.south),(bounds.east,bounds.south),(bounds.east,bounds.north),(bounds.west,bounds.north),(bounds.west,bounds.south)]])
    layer=Layer(id='battlefield',title='Pratzen Heights and Goldbach valley',bounds=bounds,width=1100,height=1200,land=[land],relief='relief-battlefield.png',zoom=12)
    features=stream_features(json.loads(stream.read_text(encoding='utf-8')),bounds)+village_features(names)
    # The heightfield, not a decorative mountain icon, represents the ridge.
    features.append(TacticalFeature(id='pratzen-heights',name='Pratzen Heights',kind='ridge',points=[(16.762,49.128)],
        source=ATLAS,period_status='historic_feature_modern_position'))
    sources=[source(names,NAMES,'village coordinates','GeoNames CC BY; historical labels checked against West Point atlas'),
        source(stream,OVERPASS,'modern stream geometry','OpenStreetMap contributors, ODbL; https://www.openstreetmap.org/copyright'),
        {'role':'historical terrain reference','url':MAP,'atlas':ATLAS,'use':'Reference only; source map is not embedded or redistributed.'}]
    sources[1]['query']=QUERY
    directory=Path(root)/uuid4().hex;directory.mkdir(parents=True)
    grid={'columns':129,'rows':161}
    sources.extend(render_relief(layer,cache,directory/layer.relief,height_grid=grid))
    for record in sources:
        if record.get('role')=='elevation':record['license']+='; Europe: modified Copernicus EU-DEM; https://github.com/tilezen/joerd/blob/master/docs/attribution.md'
    battlefield=Battlefield(layer=layer,heights=HeightGrid(**grid),features=features,sources=sources,
        notes=['Terrain study only: not a reconstructed battle or publishable script.',
               'Tilted measured terrain; 5x vertical exaggeration for visibility.',
               'Stream course is modern context, not a verified 1805 channel.',
               'Village glyphs are symbols at modern centers, not 1805 footprints.',
               'No unverified formations, crossings, woods or ponds are invented.',
               'The full-frame camera stays within the measured terrain extent.'])
    captions=[('Heights and slopes','Raised ground must read as raised ground. The Pratzen surface is built from measured elevation.'),
        ('Stream and low ground','The blue stream shows the modern Goldbach / Ricka course. Exact 1805 banks and crossings still require period verification.'),
        ('Villages and approaches','Sokolnitz and Telnitz anchor the local view. Village markers show settlement locations; their shapes are illustrative.'),
        ('Terrain before choreography','Troop movement needs researched deployments and crossing locations. This preview concentrates on the ground those formations would traverse.')]
    scene={'schema_version':'1.0','purpose':'battlefield_terrain_study','topic':'Austerlitz','duration':40,
        'timing_basis':'study','battlefield':battlefield.model_dump(mode='json'),
        'scenes':[{'scene_id':f's{i+1}','start':i*10,'end':(i+1)*10,'labels':[title]} for i,(title,_) in enumerate(captions)],
        'captions':[{'start':i*10,'end':(i+1)*10,'text':text} for i,(_,text) in enumerate(captions)]}
    for p in WEB.iterdir():
        if p.is_file():shutil.copyfile(p,directory/p.name)
    shutil.copyfile(pixi,directory/'pixi.min.js')
    (directory/'scene.json').write_text(json.dumps(scene,indent=2,ensure_ascii=False),encoding='utf-8')
    (directory/'content.json').write_text(json.dumps({'status':'preview','purpose':'battlefield_terrain_study','publishing_ready':False}),encoding='utf-8')
    (directory/'battlefield.json').write_text(battlefield.model_dump_json(indent=2),encoding='utf-8')
    (directory/'report.md').write_text('# Austerlitz tactical terrain study\n\n'+
        '\n'.join('- '+n for n in battlefield.notes)+'\n\nSources: West Point atlas, GeoNames, OpenStreetMap contributors (ODbL), Mapzen/USGS/NOAA and modified Copernicus EU-DEM.\n'+
        '\n'.join(r['url'] for r in sources)+'\n',encoding='utf-8')
    return directory


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,default=Path('output/tactical/cache'))
    p.add_argument('--output',type=Path,default=Path('output/content'))
    args=p.parse_args(argv)
    try:
        print('Tactical terrain study:',compile_study(args.cache,args.output));return 0
    except (ValueError,OSError,RuntimeError) as error:
        print('Tactical study failed:',str(error));return 1


if __name__=='__main__':raise SystemExit(main())
