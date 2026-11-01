import contextlib
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from war_studio.__main__ import Handler,byte_range,main


class StudioTests(unittest.TestCase):
    def test_byte_ranges_and_invalid_requests(self):
        for header,expected in [('bytes=0-2',(0,2)),('bytes=4-',(4,9)),('bytes=-3',(7,9)),('bytes=-20',(0,9)),('bytes=8-100',(8,9))]:
            self.assertEqual(byte_range(header,10),expected)
        for header,size in [('bytes=-',10),('bytes=20-',10),('bytes=5-2',10),('bytes=-0',10),('bytes=0-1,3-4',10),('items=0-1',10),('bytes=0-',0)]:
            with self.assertRaises(ValueError):byte_range(header,size)

    def test_only_ui_assets_and_mounted_media_are_served(self):
        with TemporaryDirectory() as tmp:
            video=Path(tmp)/'test.MP4';video.write_bytes(b'0123456789')
            poster=Path(tmp)/'test.png';poster.write_bytes(b'PNG')
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,video=video,poster=poster))
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                def request(path,method='GET',headers=None):
                    conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request(method,path,headers=headers or {});response=conn.getresponse()
                    result=response.status,dict(response.getheaders()),response.read();conn.close();return result
                status,headers,body=request('/')
                self.assertEqual(status,200);self.assertIn(b'Content Machine',body)
                self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
                for asset in ('/studio.css','/studio.mjs','/state.mjs','/preview.png'):
                    self.assertEqual(request(asset)[0],200)
                self.assertEqual(request('/preview.mp4')[2],b'0123456789')
                status,headers,body=request('/preview.mp4',headers={'Range':'bytes=2-5'})
                self.assertEqual((status,body),(206,b'2345'));self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
                self.assertEqual(request('/preview.mp4','HEAD')[2],b'')
                status,headers,body=request('/preview.mp4',headers={'Range':'bytes=90-'})
                self.assertEqual(status,416);self.assertEqual(headers['Content-Range'],'bytes */10')
                for route in ('/.env','/../pyproject.toml','/war_research/providers.py','/%2e%2e/.env','/unknown'):
                    self.assertEqual(request(route)[0],404)
                video.unlink();self.assertEqual(request('/preview.mp4')[0],404)
            finally:server.shutdown();server.server_close();thread.join()

    def test_cli_rejects_bad_options_and_closes_server(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):main(['--port','-1'])
            with TemporaryDirectory() as tmp:
                wrong=Path(tmp)/'wrong.txt';wrong.write_text('not video')
                with self.assertRaises(SystemExit):main(['--demo','--video',str(wrong)])
        with patch('war_studio.__main__.ThreadingHTTPServer') as factory,contextlib.redirect_stdout(io.StringIO()):
            factory.return_value.serve_forever.side_effect=KeyboardInterrupt
            main(['--demo','--port','0']);factory.return_value.server_close.assert_called_once()
