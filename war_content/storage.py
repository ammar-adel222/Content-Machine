"""Save portable, local-only PixiJS playback bundles."""
import json
import shutil
from pathlib import Path
from uuid import uuid4
from war_director.agent import phrase_times
from war_writer.agent import fingerprint
from .agent import ContentError, asset_key

WEB = Path(__file__).parent/"web"


def save(build, plan, script, root, *, audio=None, pixi=None):
    if build.plan_sha256 != fingerprint(plan) or build.script_sha256 != fingerprint(script):
        raise ContentError("Content build input versions changed before saving.")
    if build.status == "ready" and (plan.timing_basis == "measured") != (audio is not None):
        raise ContentError("Save needs the same audio timing basis as the storyboard.")
    if build.status == "ready" and (not pixi or not Path(pixi).is_file()):
        raise ContentError("PixiJS runtime missing. Install renderer dependencies or supply --pixi FILE.")
    directory = Path(root)/uuid4().hex
    directory.mkdir(parents=True,exist_ok=False)
    (directory/"content.json").write_text(build.model_dump_json(indent=2),encoding="utf-8")
    lines = ["# Content engine build", "", f"Topic: {build.topic}", f"Status: **{build.status}**",
             f"Model attempts: {build.model_calls}", f"Reused designs: {len(build.reused)}", "", "## Visuals", ""]
    lines += [f"- {b.brief.category} `{b.object_id}`: **{b.brief.concept}** — {b.brief.description}" for b in build.manifest.bindings]
    lines += ["", "## Issues", ""]+[f"- {i}" for i in build.issues]
    lines += ["", "Schematic geography; symbols are illustrative, not verified equipment reconstructions.",
              "Asset reviews record whether they inspected vector data or real rendered images. Full video still needs review.",
              "Playback is silent until the separate audio-production stage is connected."]
    if build.status == "ready":
        bindings = {category:{b.object_id:asset_key(b.brief) for b in build.manifest.bindings if b.brief.category == category}
                    for category in ("unit","terrain")}
        if any(key not in build.assets for group in bindings.values() for key in group.values()):
            raise ContentError("Ready build contains unresolved visuals.")
        if any(not asset.review.passed or asset.design_sha256 != fingerprint(asset.design) for asset in build.assets.values()):
            raise ContentError("Asset changed after review or does not have a passing review.")
        clock = phrase_times(script,audio)
        scenes = [{**s.model_dump(),"start":clock[f"{s.scene_id}.p1"][0],
                   "end":max(end for phrase,(_,end) in clock.items() if phrase.startswith(s.scene_id+"."))}
                  for s in plan.blueprint.scenes]
        captions = [{"start":clock[f"{s.id}.p{i}"][0],"end":clock[f"{s.id}.p{i}"][1],"text":p.text}
                    for s in script.draft.scenes for i,p in enumerate(s.phrases,1)]
        payload = {"schema_version":"1.0","topic":build.topic,"duration":plan.duration_seconds,
                   "timing_basis":plan.timing_basis,"layout_note":plan.blueprint.layout_note,
                   "blueprint":plan.blueprint.model_dump(),"scenes":scenes,"captions":captions,
                   "timeline":plan.timeline,"bindings":bindings,
                   "assets":{k:v.design.model_dump() for k,v in build.assets.items()}}
        (directory/"scene.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        for name in ("index.html","player.mjs","motion.mjs","symbols.mjs","labels.mjs"):
            shutil.copyfile(WEB/name,directory/name)
        shutil.copyfile(pixi,directory/"pixi.min.js")
        lines += ["", "Serve this directory over HTTP and open index.html. Use the timeline slider to inspect any frame."]
    (directory/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return directory
