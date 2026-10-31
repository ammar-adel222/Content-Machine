import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from war_content.agent import ContentError, Library, OfflineModel
from war_content.models import Brief
from war_content.units import UnitDesigner, save_unit
from war_research.providers import ProviderError
from .content_helpers import ContentModel, asset, design, passing


class UnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = Library(self.root / 'library')
        self.brief = Brief(category='unit', concept='war_elephant',
                           description='Top-down elephant silhouette with broad ears and a forward trunk.')

    def designer(self, model=None):
        return UnitDesigner(model or ContentModel(), self.library, preview=lambda d: b'png')

    def test_unknown_unit_creates_reusable_asset_without_fixed_catalog(self):
        model = ContentModel()
        result = self.designer(model).create(self.brief)
        self.assertIsNotNone(result.asset)
        self.assertEqual(result.asset.brief, self.brief)
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(result.asset.review_version, 2)
        self.assertIn('war_elephant', model.prompts[0])
        self.assertIn('24/32/40px', model.prompts[1])
        cached = self.designer(OfflineModel()).create(self.brief)
        self.assertTrue(cached.reused)
        self.assertEqual(cached.model_calls, 0)

    def test_old_review_rechecked_without_redesigning(self):
        old = asset(self.brief)
        old.review_basis = 'rendered_image'
        self.library.put(old)
        model = ContentModel()
        result = self.designer(model).create(self.brief)
        self.assertEqual(result.model_calls, 1)
        self.assertEqual(result.asset.review_version, 2)
        self.assertEqual(len(model.prompts), 1)

    def test_repair_and_rejection_preserve_draft_without_caching(self):
        rejected = passing().model_copy(update={'recognizable': False, 'issues': ['Trunk disappears.']})
        model = ContentModel(replies=[design(), rejected, design(), rejected])
        result = self.designer(model).create(self.brief)
        self.assertIsNone(result.asset)
        self.assertIsNotNone(result.draft)
        self.assertIn('Trunk', result.issues[0])
        self.assertIsNone(self.library.get(self.brief))
        self.assertIn('REPAIR', model.prompts[2])
        root = save_unit(result, self.root / 'rejected', lambda d: b'png')
        self.assertEqual((root / 'preview.png').read_bytes(), b'png')
        self.assertIn('needs_revision', (root / 'report.md').read_text(encoding='utf-8'))

    def test_budget_provider_offline_and_invalid_brief(self):
        self.assertIsNone(self.designer().create(self.brief, max_model_calls=1).asset)
        model = ContentModel(replies=[ProviderError('Offline'), ProviderError('Offline')])
        self.assertEqual(self.designer(model).create(self.brief).issues, ['Offline'])
        self.assertIsNone(self.designer(OfflineModel()).create(self.brief).asset)
        for budget in (0, 13):
            with self.assertRaises(ValueError): self.designer().create(self.brief, max_model_calls=budget)
        with self.assertRaises(ValueError):
            self.designer().create(self.brief.model_copy(update={'category': 'terrain'}))

    def test_success_report_and_cli(self):
        from war_content.unit_cli import main
        source = self.root / 'brief.json'
        source.write_text(self.brief.model_dump_json(), encoding='utf-8')
        args = [str(source), '--library', str(self.root / 'cli-library'), '--output', str(self.root / 'output'),
                '--env-file', str(self.root / 'absent.env')]
        with patch.dict('os.environ', {'GROQ_API_KEY': 'fixture'}), \
             patch('war_content.unit_cli.LanguageModel', return_value=ContentModel()), \
             patch('war_content.unit_cli.render_preview', return_value=b'png'), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
            folder = next((self.root / 'output').iterdir())
            self.assertIsNotNone(json.loads((folder / 'result.json').read_text(encoding='utf-8'))['asset'])
            self.assertTrue((folder / 'design.json').exists())
            source.write_text('{}', encoding='utf-8')
            self.assertEqual(main(args), 1)

    def test_corrupt_cache_preview_failure_and_changed_asset_cannot_pass(self):
        engine = UnitDesigner(ContentModel(), self.library, preview=lambda d: (_ for _ in ()).throw(ContentError('Renderer unavailable.')))
        failed = engine.create(self.brief)
        self.assertIsNone(failed.asset)
        self.assertIsNotNone(failed.draft)
        self.assertEqual(failed.issues, ['Renderer unavailable.'])
        result = self.designer().create(self.brief)
        result.asset.design.label = 'Changed after review'
        with self.assertRaises(ContentError):
            save_unit(result, self.root / 'tampered', lambda d: b'png')
        path = next(self.library.root.glob('*.json'))
        path.write_text('{broken', encoding='utf-8')
        self.assertIsNone(self.designer().create(self.brief).asset)

    def test_changed_description_has_its_own_identity(self):
        self.designer().create(self.brief)
        changed = self.brief.model_copy(update={'description': 'Top-down elephant with clearly separated tusks and a forward trunk.'})
        result = self.designer().create(changed)
        self.assertFalse(result.reused)
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(len(self.library.briefs()), 2)
