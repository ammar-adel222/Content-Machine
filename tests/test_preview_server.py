import contextlib
import io
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch,MagicMock
from war_content.play import PreviewHandler,main,ready,select_bundle


class PreviewServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.bundle=self.root/'ready';self.bundle.mkdir()
        (self.bundle/'content.json').write_text('{"status":"ready"}',encoding='utf-8')
        (self.bundle/'scene.json').write_text('{"schema_version":"1.0","assets":{"x":{}},"scenes":[{}]}',encoding='utf-8')
        (self.bundle/'pixi.min.js').write_text('// test runtime',encoding='utf-8')

    def test_select_ready_and_reject_template_incomplete_or_broken(self):
        self.assertTrue(ready(self.bundle));self.assertEqual(select_bundle(self.root),self.bundle)
        self.assertEqual(select_bundle(self.root,self.bundle),self.bundle)
        empty=self.root/'incomplete';empty.mkdir()
        (empty/'content.json').write_text('{"status":"needs_revision"}',encoding='utf-8')
        self.assertEqual(select_bundle(self.root),self.bundle)
        with self.assertRaises(ValueError):select_bundle(self.root,empty)
        for content in ('broken','[]','{"status":"needs_revision"}'):
            (self.bundle/'content.json').write_text(content,encoding='utf-8')
            self.assertFalse(ready(self.bundle))
        with self.assertRaises(ValueError):select_bundle(self.root)

    def test_server_serves_current_player_and_only_selected_scene(self):
        (self.bundle/'secret.env').write_text('do not serve',encoding='utf-8')
        with ThreadingHTTPServer(('127.0.0.1',0),partial(PreviewHandler,bundle=self.bundle)) as server:
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                for path,expected in (('/','boot.js'),('/boot.js','preview.cmd'),('/scene.json','schema_version'),('/pixi.min.js','test runtime'),('/player.mjs','renderAt')):
                    with urlopen(base+path) as response:
                        self.assertIn(expected,response.read().decode());self.assertEqual(response.headers['Cache-Control'],'no-store')
                for path in ('/secret.env','/content.json','/../AGENTS.md','/%2e%2e/AGENTS.md'):
                    with self.assertRaises(HTTPError) as error:urlopen(base+path)
                    self.assertEqual(error.exception.code,404)
            finally:
                server.shutdown();worker.join()

    def test_cli_launch_no_browser_interrupt_and_bad_inputs(self):
        server=MagicMock();server.server_port=8765
        server.__enter__.return_value=server;server.serve_forever.side_effect=KeyboardInterrupt
        with patch('war_content.play.ThreadingHTTPServer',return_value=server),patch('war_content.play.webbrowser.open') as browser,contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main([str(self.bundle)]),0)
            browser.assert_called_once_with('http://127.0.0.1:8765/')
            self.assertIn('Map preview:',stdout.getvalue());browser.reset_mock()
            self.assertEqual(main([str(self.bundle),'--no-browser']),0);browser.assert_not_called()
            self.assertEqual(main(['--port','-1']),1)
            self.assertEqual(main(['--root',str(self.root/'missing')]),1)
        with patch('war_content.play.ThreadingHTTPServer',side_effect=OSError('Port unavailable')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.bundle)]),1)
