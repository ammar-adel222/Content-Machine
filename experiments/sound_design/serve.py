"""Local-only listening gallery with WAV byte ranges for native audio controls."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re


class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.remaining=None
        target=Path(self.translate_path(self.path)).resolve()
        if not target.is_relative_to(Path(self.directory).resolve()):
            self.send_error(404);return None
        if target.suffix!='.wav' or not self.headers.get('Range'):
            return super().send_head()
        if not target.is_file():self.send_error(404);return None
        size=target.stat().st_size;match=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
        if match and any(match.groups()):
            first,last=match.groups();start=int(first) if first else max(0,size-int(last))
            end=min(size-1,int(last)) if first and last else size-1
        else:start,end=size,0
        if start>end or start>=size:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return None
        self.send_response(206);self.send_header('Content-Type','audio/wav');self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Content-Length',str(end-start+1));self.end_headers()
        source=target.open('rb');source.seek(start);self.remaining=end-start+1;return source

    def copyfile(self,source,output):
        if self.remaining is None:return super().copyfile(source,output)
        while self.remaining:
            block=source.read(min(self.remaining,65536))
            if not block:break
            output.write(block);self.remaining-=len(block)

    def log_message(self,*args):pass


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,default=64922)
    args=p.parse_args(argv)
    if not args.root.is_dir() or not 0<=args.port<=65535:p.error('Choose a gallery directory and valid port.')
    with ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(args.root.resolve()))) as server:
        print(f'Listening comparison: http://127.0.0.1:{server.server_port}/',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
    return 0


if __name__=='__main__':raise SystemExit(main())
