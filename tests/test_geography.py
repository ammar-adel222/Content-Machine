import contextlib
import io
import json
import math
import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
from pydantic import ValidationError
from war_content.geodata import Bounds,Geography,Layer,Place,Placement,Polygon,extract_land,project,unproject
from war_content.geography import compile_bundle,decode_height,digest,download,gazetteer,main,relief,source,tile_keys,validate_placements
from war_writer.agent import fingerprint

RING=[(0,0),(1,0),(1,1),(0,1),(0,0)]


def layer():
    return Layer(id='overview',title='Test map',bounds=Bounds(west=0,south=0,east=1,north=1),width=32,height=32,
        land=[Polygon(rings=[RING])],relief='relief-overview.png',zoom=2)


class GeographyTests(unittest.TestCase):
    def test_contracts_projection_and_geometry(self):
        l=layer()
        for lon,lat in ((0,0),(.3,.7),(1,1)):
            x,y=project(lon,lat,l.bounds,300,500)
            actual=unproject(x,y,l.bounds,300,500)
            self.assertAlmostEqual(actual[0],lon);self.assertAlmostEqual(actual[1],lat)
        for bounds in ((0,0,0,1),(1,0,0,1),(-180,0,180,1),(0,80,1,90)):
            with self.assertRaises(ValidationError):Bounds(**dict(zip(('west','south','east','north'),bounds)))
        for ring in (RING[:-1],[(0,0)]*4,[(0,0),(1,0),(2,0),(0,0)]):
            with self.assertRaises(ValidationError):Polygon(rings=[ring])
        with self.assertRaises(ValidationError):Polygon(rings=[RING*20_001])
        polygon={'type':'Polygon','coordinates':[RING]}
        self.assertEqual(len(extract_land(polygon,l.bounds)),1)
        self.assertEqual(len(extract_land({'type':'FeatureCollection','features':[{'geometry':{'type':'MultiPolygon','coordinates':[[RING]]}}]},l.bounds)),1)
        with self.assertRaises(ValueError):extract_land({'type':'Point','coordinates':[0,0]},l.bounds)
        with self.assertRaises(ValueError):extract_land(polygon,Bounds(west=3,south=3,east=4,north=4))
        geo=Geography(region='Test',parent_scene_sha256='hash',layers=[l],sources=[],omitted_actions=[],notes=[])
        payload=geo.model_dump();payload['layers'].append(l.model_dump())
        with self.assertRaises(ValidationError):Geography.model_validate(payload)
        self.assertGreater(len(tile_keys(l.bounds,2)),0)
        with self.assertRaises(ValueError):tile_keys(l.bounds,11,maximum=1)
        self.assertEqual(decode_height((128,5,128)),5.5)
        with self.assertRaises(ValidationError):l.model_copy().model_validate({**l.model_dump(),'relief':'../secret.png'})

    def test_download_cache_limits_and_source_hash(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'cache.bin'
            with patch('war_content.geography.urlopen',return_value=io.BytesIO(b'abc')) as call:
                self.assertEqual(download('https://example.org/data',p,3),p)
                download('https://example.org/data',p,3);self.assertEqual(call.call_count,1)
            self.assertEqual(len(source(p,'url','role','license')['sha256']),64)
            with self.assertRaises(ValueError):download('url',p,2)
            with patch('war_content.geography.urlopen',return_value=io.BytesIO(b'long')),self.assertRaises(ValueError):download('https://example.org/data',Path(tmp)/'too-big',2)

    def test_gazetteer_uses_ids_and_keeps_coordinates(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'places.zip'
            columns=['42','Stanley','Stanley','','-51.69','-57.85','P','PPLC']+['']*11
            with ZipFile(p,'w') as z:z.writestr('FK.txt','\t'.join(columns))
            place=gazetteer(p,['42'])[0]
            self.assertEqual(place.name,'Stanley');self.assertEqual(place.lon,-57.85)
            with self.assertRaises(ValueError):gazetteer(p,['missing'])

    @unittest.skipUnless(importlib.util.find_spec('PIL'),'Requires optional geography dependencies')
    def test_relief_from_height_data_and_bad_tiles(self):
        from PIL import Image
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            def fetch(url,path,limit):
                path=Path(path)
                im=Image.new('RGB',(256,256));im.putdata([(128,(x//2+y//2),0) for y in range(256) for x in range(256)])
                im.save(path);return path
            grid={'columns':3,'rows':4}
            l=layer();records=relief(l,root,root/'relief.png',fetch,height_grid=grid)
            self.assertEqual(len(grid['values']),12);self.assertTrue(all(math.isfinite(v) for v in grid['values']))
            self.assertTrue(records);self.assertTrue((root/'relief.png').exists());self.assertGreater(l.max_height,0)
            with Image.open(root/'relief.png') as im:self.assertGreater(len(set(im.tobytes())),1)
            def wrong(url,path,limit):
                Image.new('RGB',(16,16)).save(path);return path
            with self.assertRaises(ValueError):relief(layer(),root,root/'wrong.png',wrong)
            def void(url,path,limit):
                Image.new('RGB',(256,256),(0,0,0)).save(path);return path
            with self.assertRaises(ValueError):relief(layer(),root,root/'void.png',void)
            with patch.dict('sys.modules',{'PIL':None}),self.assertRaises(RuntimeError):relief(layer(),root,root/'absent.png')

    def test_compiler_keeps_parent_and_discards_schematic_routes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'old';bundle.mkdir()
            scene={'schema_version':'1.0','topic':'Test','assets':{'x':{}},'scenes':[{'scene_id':'s1'}],
                'blueprint':{'forces':[{'id':'a','claim_ids':['C1']}],'scenes':[{'actions':[{'id':'move1','kind':'move'}]}]}}
            build={'status':'ready','manifest':{'bindings':[{'object_id':'a','claim_id':'C1','evidence_quote':'The garrison was in Stanley.'}]}}
            (bundle/'content.json').write_text(json.dumps(build));(bundle/'scene.json').write_text(json.dumps(scene));(bundle/'pixi.min.js').write_text('// fixture')
            l=layer();l.places=[Place(id='stanley',name='Stanley',lon=.5,lat=.5,kind='settlement',source='test')]
            binding=Placement(unit_id='a',place_id='stanley',scene_ids=['s1'],claim_ids=['C1'],note='Area-level marker only.')
            def render(layer,cache,target):Path(target).write_bytes(b'PNG fixture');return []
            folder=compile_bundle(bundle,[l],[],'Region',root,root/'new',placements=[binding],render_relief=render)
            compiled=json.loads((folder/'scene.json').read_text(encoding='utf-8'))
            self.assertEqual(compiled['geography']['parent_scene_sha256'],digest(scene))
            self.assertEqual(compiled['geography']['omitted_actions'],['move1'])
            self.assertNotIn('geography',json.loads((bundle/'scene.json').read_text(encoding='utf-8')))
            self.assertTrue((folder/'geography.mjs').exists());self.assertTrue((folder/'relief-overview.png').exists())
            geo=Geography.model_validate(compiled['geography'])
            self.assertEqual(json.loads((folder/'content.json').read_text(encoding='utf-8'))['geography_sha256'],fingerprint(geo))
            for changes in ({'unit_id':'unknown'},{'scene_ids':['s2']},{'claim_ids':['C2']},{'place_id':'unknown'}):
                bad=geo.model_copy(deep=True);bad.placements=[binding.model_copy(update=changes)]
                with self.assertRaises(ValueError):validate_placements(bad,scene,build)
            badbuild={'manifest':{'bindings':[]}}
            with self.assertRaises(ValueError):validate_placements(geo,scene,badbuild)
            with self.assertRaises(ValueError):compile_bundle(root/'missing',[l],[],'Region',root,root/'bad',render_relief=render)

    def test_cli_custom_map_and_input_failures(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'land.geojson';p.write_text(json.dumps({'type':'Polygon','coordinates':[RING]}))
            with patch('war_content.geography.ready',return_value=True),patch('war_content.geography.compile_bundle',return_value=root) as compile,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['bundle','--geojson',str(p),'--bbox','0','0','1','1']),0)
                self.assertEqual(compile.call_args.args[3],'land')
                self.assertEqual(main(['bundle','--geojson',str(p)]),1)
                self.assertEqual(main(['bundle','--bbox','0','0','1','1']),1)
            with patch('war_content.geography.ready',return_value=False),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main(['missing']),1)

    def test_falklands_profile_is_source_selected_and_builds_area_callouts(self):
        from war_content.geography import falklands,COUNTRIES
        with TemporaryDirectory() as tmp:
            root=Path(tmp);countries=root/'countries.json';names=root/'FK.zip'
            ring=[[-61.5,-52.5],[-57.4,-52.5],[-57.4,-51],[-61.5,-51],[-61.5,-52.5]]
            countries.write_text(json.dumps({'features':[{'properties':{'ADM0_A3':'FLK'},'geometry':{'type':'Polygon','coordinates':[ring]}}]}))
            names.write_bytes(b'fixture zip')
            place=Place(id='3426691',name='Stanley',lon=-57.85,lat=-51.69,kind='settlement',source='fixture')
            with patch('war_content.geography.download',side_effect=lambda url,*args:countries if url==COUNTRIES else names),patch('war_content.geography.gazetteer',return_value=[place]):
                layers,sources=falklands(root)
            self.assertEqual(len(layers),2);self.assertEqual(len(sources),2);self.assertEqual(layers[1].zoom,10)
            scene={'topic':'Falklands War','scenes':[{'scene_id':'s1'}],
                'blueprint':{'forces':[{'id':'a','kind':'infantry','claim_ids':['C1']},{'id':'fleet','kind':'fleet','claim_ids':['C2']}],
                             'scenes':[{'scene_id':'s3','actions':[{'unit_id':'fleet'}]}]}}
            (root/'scene.json').write_text(json.dumps(scene));(root/'content.json').write_text(json.dumps({'manifest':{'bindings':[{'brief':{'category':'unit'},'object_id':'a','claim_id':'C1','evidence_quote':'The garrison at Stanley.'}]}}))
            with patch('war_content.geography.ready',return_value=True),patch('war_content.geography.falklands',return_value=(layers,sources)),patch('war_content.geography.compile_bundle',return_value=root) as compile,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(root)]),0)
                bindings=compile.call_args.kwargs['placements'];self.assertEqual(bindings[0].place_id,'3426691');self.assertIsNone(bindings[1].place_id)
                overrides=root/'placements.json';overrides.write_text('[]')
                self.assertEqual(main([str(root),'--placements',str(overrides)]),0)
                scene['topic']='Battle of Austerlitz';(root/'scene.json').write_text(json.dumps(scene))
                self.assertEqual(main([str(root)]),1)
