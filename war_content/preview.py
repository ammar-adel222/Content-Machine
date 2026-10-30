"""Render original vector designs through the same PixiJS interpreter as playback."""
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from .agent import ContentError

RENDERER = Path(__file__).resolve().parents[1]/"renderer/asset.mjs"


def render_preview(design):
    with TemporaryDirectory(prefix="content-visual-") as tmp:
        folder=Path(tmp);source=folder/"design.json";target=folder/"preview.png"
        source.write_text(design.model_dump_json(),encoding="utf-8")
        try:
            result=subprocess.run(["node",str(RENDERER),str(source),str(target)],
                cwd=RENDERER.parent.parent,capture_output=True,timeout=45)
            if result.returncode or not target.is_file():
                raise ContentError("Visual preview renderer failed; check renderer dependencies/browser installation.")
            return target.read_bytes()
        except (OSError,subprocess.TimeoutExpired):
            raise ContentError("Visual preview renderer unavailable or timed out.") from None
