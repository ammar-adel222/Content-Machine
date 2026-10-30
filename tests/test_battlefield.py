import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
from pydantic import ValidationError
from war_content.battlefield import compile_study,main,stream_features,village_features
from war_content.geodata import Battlefield,Bounds,HeightGrid,Layer,Polygon,TacticalFeature
from war_content.play import ready,select_bundle


class BattlefieldTests(unittest.TestCase):
    def test_height_grid_and_tactical_feature_contract(self):
        with self.assertRaises(ValidationError):HeightGrid(columns=2,rows=2,values=[0,1])
        with self.assertRaises(ValidationError):HeightGrid(columns=2,rows=2,values=[0,1,2,float('nan')])
        with self.assertRaises(ValidationError):TacticalFeature(id='a',name='Stream',kind='stream',points=[(0,0)],source='test',period_status='modern_context')
        l=Layer(id='battlefield',title='Test',bounds=Bounds(west=0,south=0,east=1,north=1),width=32,height=32,
            land=[Polygon(rings=[[(0,0),(1,0),(1,1),(0,1),(0,0)]])],relief='relief-battlefield.png',zoom=12)
        feature=TacticalFeature(id='a',name='Stream',kind='stream',points=[(0,0),(1,1)],source='test',period_status='modern_context')
        data=dict(layer=l,heights=HeightGrid(columns=2,rows=2,values=[0,1,2,3]),features=[feature],sources=[],notes=[])
        self.assertEqual(Battlefield(**data).mode,'battlefield')
        with self.assertRaises(ValidationError):Battlefield(**{**data,'features':[feature,feature]})
        with self.assertRaises(ValidationError):Battlefield(**{**data,'features':[feature.model_copy(update={'points':[(2,2),(3,3)]})]})

    def test_stream_clipping_preserves_disconnected_sections(self):
        bounds=Bounds(west=0,south=0,east=1,north=1)
        points=[(0,0),(.2,.3),(4,4),(.5,.5),(1,1)]
        result=stream_features({'elements':[{'id':1,'geometry':[{'lon':x,'lat':y} for x,y in points]}]},bounds)
        self.assertEqual(len(result),2);self.assertNotEqual(result[0].id,result[1].id)
        self.assertTrue(all(f.period_status=='modern_context' for f in result))
        with self.assertRaises(ValueError):stream_features({'elements':[]},bounds)

    def test_cached_study_compilation_and_preview_mode(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache';cache.mkdir()
            identities={'3064307':('49.10187','16.71774'),'3065618':('49.11392','16.72156'),
                '3067716':('49.14106','16.76539'),'3073472':('49.13803','16.73182'),'3067836':('49.15216','16.74229')}
            rows=['\t'.join([id,'Name','','',lat,lon,'P','PPL']+['']*11) for id,(lat,lon) in identities.items()]
            with ZipFile(cache/'CZ.zip','w') as z:z.writestr('CZ.txt','\n'.join(rows))
            stream={'elements':[{'id':42,'geometry':[{'lon':16.72,'lat':49.10},{'lon':16.73,'lat':49.15}]}]}
            (cache/'goldbach-osm.json').write_text(json.dumps(stream))
            self.assertEqual(len(village_features(cache/'CZ.zip')),5)
            def relief(layer,cache,target,height_grid):
                Path(target).write_bytes(b'PNG fixture');height_grid['values']=[200.0]*(height_grid['columns']*height_grid['rows']);return []
            with patch('war_content.battlefield.download',side_effect=lambda url,path,limit:path):
                folder=compile_study(cache,root/'output',render_relief=relief)
            self.assertTrue(ready(folder));self.assertEqual(select_bundle(root/'output',mode='battlefield'),folder)
            with self.assertRaises(ValueError):select_bundle(root/'output',mode='campaign')
            content=json.loads((folder/'content.json').read_text());self.assertFalse(content['publishing_ready'])
            scene=json.loads((folder/'scene.json').read_text(encoding='utf-8'))
            self.assertNotIn('geography',scene);self.assertIn('battlefield',scene)
            self.assertNotIn('forces',scene);self.assertEqual(scene['duration'],40)
            from war_content.geography import compile_bundle
            with self.assertRaises(ValueError):compile_bundle(folder,[],[],'Region',cache,root/'wrong-format')
            with patch('war_content.battlefield.compile_study',return_value=folder),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main([]),0)
            with patch('war_content.battlefield.compile_study',side_effect=ValueError('Invalid data')),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main([]),1)
            (cache/'goldbach-osm.json').unlink()
            with patch('war_content.battlefield.download',side_effect=lambda url,path,limit:path),patch('war_content.battlefield.urlopen',return_value=io.BytesIO(json.dumps(stream).encode())) as request:
                self.assertTrue(compile_study(cache,root/'fresh',render_relief=relief).exists())
                self.assertIn(b'data=',request.call_args.args[0].data)
            (cache/'goldbach-osm.json').unlink()
            with patch('war_content.battlefield.download',side_effect=lambda url,path,limit:path),patch('war_content.battlefield.urlopen',return_value=io.BytesIO(b'x'*5_000_001)),self.assertRaises(ValueError):
                compile_study(cache,root/'oversized',render_relief=relief)
            (cache/'goldbach-osm.json').write_bytes(b'x'*5_000_001)
            with patch('war_content.battlefield.download',side_effect=lambda url,path,limit:path),self.assertRaises(ValueError):compile_study(cache,root/'oversized-cache',render_relief=relief)
            with ZipFile(cache/'CZ.zip','w') as z:z.writestr('CZ.txt','')
            with self.assertRaises(ValueError):village_features(cache/'CZ.zip')
            with patch('war_content.battlefield.Path.is_file',return_value=False),self.assertRaises(ValueError):compile_study(cache,root/'missing-runtime')
