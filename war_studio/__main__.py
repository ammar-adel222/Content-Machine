"""Serve the API-independent studio UI and an optional, explicitly mounted video."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit
import webbrowser

WEB=Path(__file__).parent/'web'
ASSETS={'/':'index.html','/index.html':'index.html','/studio.css':'studio.css',
        '/studio.mjs':'studio.mjs','/state.mjs':'state.mjs','/backend.mjs':'backend.mjs'}


def byte_range(header,size):
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
    if not match or not any(match.groups()) or size<=0:raise ValueError('Invalid byte range.')
    left,right=match.groups()
    if not left:
        count=int(right)
        if count<=0:raise ValueError('Invalid suffix range.')
        return max(0,size-count),size-1
    start=int(left);end=min(int(right),size-1) if right else size-1
    if start>=size or start>end:raise ValueError('Range outside file.')
    return start,end


class Handler(BaseHTTPRequestHandler):
    def __init__(self,*args,video=None,poster=None,**kwargs):
        self.video=video;self.poster=poster
        super().__init__(*args,**kwargs)

    def do_HEAD(self):self.serve(head=True)
    def do_GET(self):self.serve()
    def log_message(self,*args):pass

    def serve(self,head=False):
        route=urlsplit(self.path).path
        target=WEB/ASSETS[route] if route in ASSETS else self.video if route=='/preview.mp4' else self.poster if route=='/preview.png' else None
        if target is None or not Path(target).is_file():self.send_error(404);return
        target=Path(target);size=target.stat().st_size;start,end=0,size-1;partial=False
        if self.headers.get('Range'):
            try:start,end=byte_range(self.headers['Range'],size);partial=True
            except ValueError:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type',{'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.mp4':'video/mp4','.png':'image/png'}[target.suffix.lower()])
        self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if head:return
        try:
            with target.open('rb') as source:
                source.seek(start);remaining=end-start+1
                while remaining>0:
                    chunk=source.read(min(65536,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--video',type=Path,default=Path('output/austerlitz-presentation/final.mp4'))
    parser.add_argument('--poster',type=Path,default=Path('output/austerlitz-presentation/final-50.png'))
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--demo',action='store_true',help='Use the isolated UI demonstration instead of the live project backend.')
    parser.add_argument('--projects',type=Path,default=Path('output/projects'))
    parser.add_argument('--data',type=Path,default=Path('output/studio'))
    parser.add_argument('--env-file',type=Path,default=Path('.env'))
    args=parser.parse_args(argv)
    if not 0<=args.port<=65535:parser.error('Port must be between 0 and 65535.')
    if not args.demo:
        from .api import create_app
        import uvicorn
        if args.open:webbrowser.open(f'http://127.0.0.1:{args.port}')
        uvicorn.run(create_app(args.projects,args.data,args.env_file),host='127.0.0.1',port=args.port,log_level='warning')
        return
    for name in ('video','poster'):
        value=getattr(args,name)
        if value.exists() and (not value.is_file() or value.suffix.lower()!={ 'video':'.mp4','poster':'.png'}[name]):parser.error(f'{name} must be an MP4 video or PNG poster file respectively.')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,video=args.video,poster=args.poster))
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'Content Machine UI demo: {url}',flush=True)
    if args.open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
