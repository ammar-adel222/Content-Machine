"""Open the latest ready map bundle with a local, bundle-only preview server."""
import argparse
import json
import re
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .geodata import Battlefield

WEB = Path(__file__).parent/"web"
RUNTIME = {"index.html", "boot.js", "player.mjs", "motion.mjs", "symbols.mjs", "labels.mjs", "geography.mjs", "playback.mjs", "battlefield.mjs", "video.mjs"}


def ready(directory):
    try:
        build=json.loads((directory/"content.json").read_text(encoding="utf-8"))
        scene=json.loads((directory/"scene.json").read_text(encoding="utf-8"))
        if scene.get('purpose')=='battlefield_terrain_study':
            Battlefield.model_validate(scene.get('battlefield'))
            return build.get('status')=='preview' and build.get('publishing_ready') is False and bool(scene.get('scenes')) and (directory/'pixi.min.js').is_file()
        return (build.get("status")=="ready" and scene.get("schema_version")=="1.0" and
                bool(scene.get("assets")) and bool(scene.get("scenes")) and
                (directory/"pixi.min.js").is_file())
    except (OSError,ValueError,AttributeError):
        return False


def select_bundle(root, bundle=None,mode=None):
    def matches(path):
        scene=json.loads((path/'scene.json').read_text(encoding='utf-8'))
        tactical=bool(scene.get('battlefield')) or scene.get('blueprint',{}).get('scale')=='tactical'
        return not mode or (mode=='battlefield')==tactical
    if bundle is not None:
        directory=Path(bundle).resolve()
        if not ready(directory) or not matches(directory):
            raise ValueError("That folder has no ready map. Choose a generated output/content build, not war_content/web.")
        return directory
    candidates=[path for path in Path(root).glob("*") if path.is_dir() and ready(path) and matches(path)]
    if not candidates:
        raise ValueError("No ready maps found. Generate a ready content build before opening the preview.")
    return max(candidates,key=lambda path:(path.stat().st_mtime_ns,path.name)).resolve()


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self,*args,bundle,**kwargs):
        self.bundle=bundle
        super().__init__(*args,directory=str(bundle),**kwargs)

    def send_head(self):
        name=urlsplit(self.path).path.lstrip("/") or "index.html"
        allowed=RUNTIME | {"scene.json", "pixi.min.js"}
        if name not in allowed and not re.fullmatch(r'relief-[a-z0-9_-]+\.png',name):
            self.send_error(404)
            return None
        target=(WEB/name if name in RUNTIME else self.bundle/name).resolve()
        parent=WEB.resolve() if name in RUNTIME else self.bundle.resolve()
        if not target.is_relative_to(parent) or not target.is_file():
            self.send_error(404)
            return None
        self.send_response(200)
        self.send_header("Content-Type", "image/png" if target.suffix==".png" else "text/javascript" if target.suffix in (".js",".mjs") else
                         "application/json" if target.suffix==".json" else "text/html; charset=utf-8")
        self.send_header("Content-Length",str(target.stat().st_size))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        return target.open("rb")

    def log_message(self,*args):
        pass


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle",nargs="?",type=Path)
    p.add_argument("--root",type=Path,default=Path("output/content"))
    p.add_argument("--port",type=int,default=0)
    p.add_argument("--no-browser",action="store_true")
    p.add_argument('--mode',choices=['campaign','battlefield'],help='Select the latest preview of this map type')
    args=p.parse_args(argv)
    try:
        if not 0<=args.port<=65535:
            raise ValueError("Port must be between 0 and 65535.")
        bundle=select_bundle(args.root,args.bundle,args.mode)
        with ThreadingHTTPServer(("127.0.0.1",args.port),partial(PreviewHandler,bundle=bundle)) as server:
            url=f"http://127.0.0.1:{server.server_port}/"
            print(f"Map preview: {url}\nBuild: {bundle}\nPress Ctrl+C to stop.",flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    except (ValueError,OSError) as error:
        print(f"Preview failed: {error}")
        return 1


if __name__=="__main__":
    raise SystemExit(main())
