import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from war_content.agent import ContentError, Library
from war_content.animation_study import build_study, main
from war_content.geodata import Battlefield, Bounds, HeightGrid, Layer, Polygon, TacticalFeature
from war_content.models import Brief
from war_content.play import ready
from .content_helpers import asset


class AnimationStudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.terrain=self.root/'terrain';self.terrain.mkdir()
        layer=Layer(id='battlefield',title='Synthetic terrain',bounds=Bounds(west=0,south=0,east=1,north=1),
                    width=32,height=32,land=[Polygon(rings=[[(0,0),(1,0),(1,1),(0,1),(0,0)]])],relief='relief-battlefield.png',zoom=12)
        feature=TacticalFeature(id='ridge',name='Test ridge',kind='ridge',points=[(.5,.5)],source='fixture',period_status='modern_context')
        self.field=Battlefield(layer=layer,heights=HeightGrid(columns=2,rows=2,values=[0,1,2,3]),features=[feature],sources=[],notes=[])
        (self.terrain/'scene.json').write_text(json.dumps({'battlefield':self.field.model_dump(mode='json')}),encoding='utf-8')
        for name in ('pixi.min.js','relief-battlefield.png'):(self.terrain/name).write_bytes(b'fixture')
        self.library=Library(self.root/'library')
        for name in ('tank','war_elephant'):
            a=asset(Brief(category='unit',concept=name,description='A generic top-down unit silhouette.'))
            a.review_basis='rendered_image';a.review_version=2;self.library.put(a)

    def build(self, **kwargs):
        return build_study(self.terrain,self.library.root,self.root/'output',**kwargs)

    def test_offline_study_is_explicit_preview_with_portable_runtime(self):
        target=self.build()
        self.assertTrue(ready(target))
        scene=json.loads((target/'scene.json').read_text(encoding='utf-8'))
        self.assertEqual(scene['purpose'],'unit_animation_study');self.assertEqual(scene['duration'],24)
        self.assertEqual(len(scene['blueprint']['forces']),2)
        self.assertEqual(scene['battlefield'],self.field.model_dump(mode='json'))
        self.assertTrue((target/'units.mjs').is_file())
        content=json.loads((target/'content.json').read_text(encoding='utf-8'))
        self.assertFalse(content['publishing_ready'])
        self.assertIn('not a historical battle', (target/'report.md').read_text(encoding='utf-8'))

    def test_missing_and_old_assets_and_bad_concept_count(self):
        with self.assertRaises(ContentError):self.build(concepts=['tank','missing_unit'])
        with self.assertRaises(ValueError):self.build(concepts=['tank'])
        record=self.library.get(Brief.model_validate(self.library.briefs()[0]))
        record.review_version=1;self.library.put(record)
        with self.assertRaises(ContentError):self.build()

    def test_missing_resources_invalid_field_and_path_escape(self):
        (self.terrain/'pixi.min.js').unlink()
        with self.assertRaises(ContentError):self.build()
        (self.terrain/'scene.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(KeyError):self.build()
        data=self.field.model_dump(mode='json');data['layer']['relief']='../relief-escape.png'
        (self.terrain/'scene.json').write_text(json.dumps({'battlefield':data}),encoding='utf-8')
        with self.assertRaises(ValueError):self.build()

    def test_cli_success_and_failure(self):
        with patch('war_content.animation_study.build_study',return_value=self.terrain),patch('war_content.animation_study.select_bundle',return_value=self.terrain),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]),0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--terrain',str(self.root/'missing')]),1)
