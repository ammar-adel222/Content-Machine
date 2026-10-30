import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pydantic import ValidationError

from war_director.agent import (DirectorAgent, DirectionError, blocked, check_plan, cue_time,
    fit_camera, inside, intersection, on_segment, phrase_times, position_at, retime)
from war_director.models import AudioTiming, DirectionRequest, Plan, Point
from war_director.storage import markdown, save
from war_research.providers import ProviderError
from war_reviewer.models import Issue
from war_writer.agent import fingerprint
from .director_helpers import DirectorModel, blueprint, inputs, quality


class GeometryTests(unittest.TestCase):
    def test_point_boundaries_and_nan(self):
        for value in (-.1, 1.1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Point(x=value,y=.5)
        with self.assertRaises(ValidationError):
            DirectionRequest(scene_id="s1")

    def test_polygon_and_intersections(self):
        terrain = blueprint().terrain[0]
        self.assertTrue(inside(Point(x=.5,y=.5),terrain.points))
        self.assertTrue(inside(Point(x=.45,y=.5),terrain.points))
        self.assertFalse(inside(Point(x=.2,y=.2),terrain.points))
        self.assertTrue(on_segment(Point(x=.5,y=.5),Point(x=0,y=0),Point(x=1,y=1)))
        self.assertIsNotNone(intersection(Point(x=0,y=0),Point(x=1,y=1),Point(x=0,y=1),Point(x=1,y=0)))
        self.assertIsNone(intersection(Point(x=0,y=0),Point(x=.2,y=0),Point(x=.5,y=1),Point(x=1,y=1)))
        self.assertIsNotNone(intersection(Point(x=0,y=0),Point(x=1,y=0),Point(x=.5,y=0),Point(x=.8,y=0)))

    def test_barrier_crossing_and_supported_gate(self):
        terrain = blueprint().terrain[0]
        a,b = Point(x=.3,y=.5),Point(x=.7,y=.5)
        self.assertTrue(blocked(a,b,terrain))
        terrain.crossings = [Point(x=.5,y=.5)]
        self.assertFalse(blocked(a,b,terrain))


class PlanCheckTests(unittest.TestCase):
    def setUp(self):
        self.dossier,self.script = inputs()
        self.b = blueprint()

    def issues(self):
        return check_plan(self.b,self.dossier,self.script)[0]

    def test_valid_and_timing(self):
        issues,timeline = check_plan(self.b,self.dossier,self.script)
        self.assertEqual(issues,[])
        self.assertEqual(len([row for row in timeline if row["kind"] != "introduce"]),4)
        self.assertEqual(timeline[0]["start_sec"],0)
        self.assertGreater(timeline[-1]["end_sec"],90)

    def test_measured_timing_and_wrong_inputs(self):
        clock = phrase_times(self.script)
        durations = {key: 22.0 for key in clock}
        audio = AudioTiming(script_sha256=fingerprint(self.script),durations=durations)
        self.assertEqual(phrase_times(self.script,audio)["s1.p1"],(0,22.25))
        audio.script_sha256 = "wrong"
        with self.assertRaises(DirectionError):
            phrase_times(self.script,audio)
        audio.script_sha256 = fingerprint(self.script)
        audio.durations.pop("s1.p1")
        with self.assertRaises(DirectionError):
            phrase_times(self.script,audio)
        with self.assertRaises(ValidationError):
            AudioTiming(script_sha256="x",durations={"s1.p1":-1})

    def test_wrong_scene_order_and_scale(self):
        self.b.scenes.reverse()
        self.b.scale = "campaign"
        self.assertTrue(any("scenes" in i for i in self.issues()))
        self.assertTrue(any("scale" in i for i in self.issues()))

    def test_duplicate_ids_and_claims(self):
        self.b.forces[1].id = "west"
        self.b.terrain.append(self.b.terrain[0].model_copy())
        self.b.terrain[0].claim_ids = ["bad"]
        self.b.scenes[1].actions[0].id = "a1"
        self.b.scenes[0].actions[0].claim_ids = ["bad"]
        issues = self.issues()
        self.assertTrue(any("Duplicate force" in i for i in issues))
        self.assertTrue(any("Duplicate terrain" in i for i in issues))
        self.assertTrue(any("Duplicate action" in i for i in issues))
        self.assertTrue(any("unknown research" in i for i in issues))

    def test_invalid_polygon_barrier_and_crossings(self):
        self.b.terrain[0].points = [Point(x=.3,y=.3),Point(x=.5,y=.5)]
        self.assertTrue(any("three points" in i for i in self.issues()))
        self.b.terrain[0].shape = "polyline"
        self.assertTrue(any("blocked terrain" in i for i in self.issues()))
        self.b.terrain[0].passability = "open"
        self.assertTrue(any("explicit barriers" in i for i in self.issues()))
        self.b.terrain[0].crossings = [Point(x=.5,y=.5)]
        self.b.terrain[0].claim_ids = ["C1"]
        self.assertTrue(any("crossings require" in i for i in self.issues()))

    def test_self_intersecting_polygon(self):
        self.b.terrain[0].points = [Point(x=.1,y=.1),Point(x=.8,y=.8),Point(x=.8,y=.1),Point(x=.1,y=.8)]
        self.assertTrue(any("intersect itself" in i for i in self.issues()))

    def test_camera_and_subgroups(self):
        self.b.scenes[0].focus.x = .1
        self.b.forces[0].subgroups = 1
        self.assertTrue(any("camera" in i for i in self.issues()))
        self.assertTrue(any("subgroups" in i for i in self.issues()))
        self.assertEqual(fit_camera(self.b.scenes[0]).focus.x,.5)

    def test_start_position_in_water(self):
        self.b.forces[0].position = Point(x=.5,y=.5)
        self.assertTrue(any("starting position" in i for i in self.issues()))
        self.b.forces[0].kind = "air"
        self.assertFalse(any("starting position" in i for i in self.issues()))
        self.b.forces[0].kind = "fleet"
        self.assertFalse(any("starting position" in i for i in self.issues()))
        self.b.terrain[0].kind = "plain"
        self.assertTrue(any("starting position" in i for i in self.issues()))

    def test_unknown_force_and_wrong_phrase(self):
        a = self.b.scenes[0].actions[0]
        a.unit_id = "ghost"
        self.assertTrue(any("unknown force" in i for i in self.issues()))
        a.unit_id = "west"
        a.end.phrase_id = "s2.p1"
        self.assertTrue(any("anchors" in i for i in self.issues()))
        a.end.phrase_id = "s1.p999"
        self.assertTrue(any("anchors" in i for i in self.issues()))

    def test_duration_and_engagement_targets(self):
        a = self.b.scenes[0].actions[0]
        a.end.fraction = 0
        self.assertTrue(any("positive duration" in i for i in self.issues()))
        a.kind = "engage"
        self.assertTrue(any("opposing target" in i for i in self.issues()))
        a.target_id = "west"
        self.assertTrue(any("opposing target" in i for i in self.issues()))
        a.target_id = "east"
        self.assertTrue(any("live positions" in i for i in self.issues()))

    def test_teleport_route_and_blocked_movement(self):
        a = self.b.scenes[0].actions[0]
        a.kind = "move"
        self.assertTrue(any("continuous route" in i for i in self.issues()))
        a.route = [Point(x=.3,y=.5),Point(x=.7,y=.5)]
        self.assertTrue(any("teleports" in i for i in self.issues()))
        self.assertTrue(any("crosses incompatible" in i for i in self.issues()))

    def test_nonmovement_cannot_relocate(self):
        self.b.scenes[0].actions[0].route = [Point(x=.2,y=.2),Point(x=.3,y=.2)]
        self.assertTrue(any("non-movement" in i for i in self.issues()))

    def test_persistent_routes_and_concurrent_forces(self):
        a = self.b.scenes[0].actions[0]
        a.kind,a.route = "move",[Point(x=.2,y=.2),Point(x=.3,y=.2)]
        other = a.model_copy(deep=True)
        other.id,other.unit_id,other.route = "other","east",[Point(x=.7,y=.7),Point(x=.8,y=.7)]
        self.b.scenes[0].actions.append(other)
        b = self.b.scenes[1].actions[0]
        b.kind,b.route = "move",[Point(x=.3,y=.2),Point(x=.4,y=.2)]
        self.assertEqual(self.issues(),[])
        b.route[0] = Point(x=.2,y=.2)
        self.assertTrue(any("teleports" in i for i in self.issues()))

    def test_overlapping_same_force_orders_and_fade(self):
        a = self.b.scenes[0].actions[0]
        a.kind,a.route = "move",[Point(x=.2,y=.2),Point(x=.3,y=.2)]
        other = a.model_copy(deep=True)
        other.id,other.route[0] = "other",Point(x=.3,y=.2)
        self.b.scenes[0].actions.append(other)
        self.assertTrue(any("overlapping movement" in i for i in self.issues()))
        a.kind,a.route = "fade",[]
        self.assertTrue(any("silently reappear" in i for i in self.issues()))

    def test_interpolated_live_position_and_contact(self):
        a = self.b.scenes[0].actions[0]
        a.kind,a.route = "move",[Point(x=.2,y=.2),Point(x=.4,y=.2),Point(x=.6,y=.2)]
        p = position_at(self.b.forces[0],5,[(0,10,a)])
        self.assertAlmostEqual(p.x,.4)
        self.assertEqual(position_at(self.b.forces[0],11,[(0,10,a)]),a.route[-1])

    def test_faded_target_and_bad_measured_duration(self):
        self.b.scenes[0].actions[0].kind = "fade"
        target = self.b.scenes[1].actions[0]
        target.unit_id,target.target_id,target.kind = "east","west","engage"
        self.assertTrue(any("target force has already faded" in i for i in self.issues()))
        audio = AudioTiming(script_sha256=fingerprint(self.script),durations={k:2 for k in phrase_times(self.script)})
        self.assertTrue(any("60–150" in i for i in check_plan(self.b,self.dossier,self.script,audio)[0]))

    def test_optional_gaps_do_not_block_overview(self):
        self.b.gaps = ["Exact clock times are unknown."]
        self.assertEqual(self.issues(),[])

    def test_narrated_terrain_must_be_visually_represented(self):
        self.dossier.findings.claims[5].statement += " The ground was rocky."
        self.script.draft.scenes[0].phrases[0].text += " The ground was rocky."
        self.assertTrue(any("rocky_ground" in i for i in self.issues()))

    def test_force_introduction_and_unsupported_withdrawal(self):
        self.b.forces[0].introduced_at.phrase_id = "s3.p1"
        self.assertTrue(any("not been introduced" in i for i in self.issues()))
        self.b.forces[0].introduced_at.phrase_id = "unknown"
        self.assertTrue(any("introduction references" in i for i in self.issues()))
        a = self.b.scenes[0].actions[0]
        a.kind,a.route = "withdraw",[Point(x=.2,y=.2),Point(x=.3,y=.2)]
        self.assertTrue(any("surrender alone" in i for i in self.issues()))
        a.kind,a.claim_ids = "move",["C1"]
        self.assertTrue(any("cited movement event" in i for i in self.issues()))

    def test_campaign_mode_and_gap(self):
        self.dossier.selected.scope = self.script.scope = "war"
        self.b.scale = "campaign"
        self.assertTrue(any("campaign formation" in i for i in self.issues()))
        for scene in self.b.scenes:
            scene.actions[0].formation = "campaign"
        self.b.gaps = ["Missing essential route evidence."]
        self.b.blocking_gaps = self.b.gaps.copy()
        self.assertEqual(self.issues(),self.b.blocking_gaps)


class DirectorAgentTests(unittest.TestCase):
    def setUp(self):
        self.dossier,self.script = inputs()
        self.model = DirectorModel()
        self.agent = DirectorAgent(self.model)

    def test_generate_and_review(self):
        p = self.agent.direct(self.dossier,self.script)
        self.assertEqual(p.status,"ready")
        self.assertEqual(p.model_calls,2)
        self.assertEqual(p.review.status,"pass")
        self.assertEqual(p.timing_basis,"estimated")

    def test_incomplete_stale_or_invalid_input_rejected(self):
        for mutate in (lambda d,s:setattr(s,"status","needs_revision"),
                       lambda d,s:setattr(s,"dossier_sha256","wrong"),
                       lambda d,s:s.draft.scenes[0].claim_ids.append("unknown")):
            d,s = inputs()
            mutate(d,s)
            with self.assertRaises(DirectionError):
                self.agent.direct(d,s)

    def test_repair_local_or_review_issue(self):
        bad = blueprint()
        bad.scenes[0].actions[0].unit_id = "unknown"
        self.model.replies = [bad,blueprint(),quality()]
        self.assertEqual(self.agent.direct(self.dossier,self.script).model_calls,3)
        review = quality()
        review.issues = [Issue(severity="blocking",message="The explanation needs clearer causal links.")]
        self.model.replies = [blueprint(),review,blueprint(),quality()]
        self.assertEqual(self.agent.direct(self.dossier,self.script).model_calls,4)

    def test_budget_one_never_skips_review(self):
        p = self.agent.direct(self.dossier,self.script,DirectionRequest(max_model_calls=1))
        self.assertEqual(p.status,"needs_revision")
        self.assertEqual(p.timeline,[])

    def test_initial_failure_and_repair_failure(self):
        self.model.replies = [ProviderError("unavailable")]
        with self.assertRaises(ProviderError):
            self.agent.direct(self.dossier,self.script)
        bad = blueprint()
        bad.gaps = ["Insufficient evidence."]
        bad.blocking_gaps = bad.gaps.copy()
        self.model.replies = [bad,ProviderError("unavailable")]
        self.assertEqual(self.agent.direct(self.dossier,self.script).status,"needs_revision")

    def test_targeted_edit_preserves_world_and_other_scenes(self):
        old = self.agent.direct(self.dossier,self.script)
        scene = old.blueprint.scenes[1].model_copy(deep=True)
        scene.focus_reason = "Focus on the narrated crossing with a clearer explanation."
        self.model.replies = [scene,quality()]
        new = self.agent.direct(self.dossier,self.script,DirectionRequest(scene_id="s2",notes="Clarify focus."),old)
        self.assertEqual(new.changed_scene_ids,["s2"])
        self.assertEqual(new.blueprint.terrain,old.blueprint.terrain)
        self.assertEqual(new.blueprint.forces,old.blueprint.forces)
        self.assertEqual(new.blueprint.scenes[0],old.blueprint.scenes[0])

    def test_wrong_scene_and_stale_previous(self):
        old = self.agent.direct(self.dossier,self.script)
        self.model.replies = [old.blueprint.scenes[0],old.blueprint.scenes[0]]
        p = self.agent.direct(self.dossier,self.script,DirectionRequest(scene_id="s2",notes="Edit."),old)
        self.assertEqual(p.status,"needs_revision")
        with self.assertRaises(DirectionError):
            self.agent.direct(self.dossier,self.script,DirectionRequest(scene_id="s999",notes="Edit."),old)
        old.script_sha256 = "wrong"
        with self.assertRaises(DirectionError):
            self.agent.direct(self.dossier,self.script,previous=old)

    def test_retime_without_model_calls(self):
        old = self.agent.direct(self.dossier,self.script)
        audio = AudioTiming(script_sha256=fingerprint(self.script), durations={k:24 for k in phrase_times(self.script)})
        new = retime(old,self.dossier,self.script,audio)
        self.assertEqual(new.status,"ready")
        self.assertEqual(new.timing_basis,"measured")
        self.assertEqual(new.model_calls,0)
        self.assertEqual(new.blueprint,old.blueprint)
        self.assertEqual(new.duration_seconds,97)
        old.review = None
        self.assertEqual(retime(old,self.dossier,self.script,audio).status,"needs_revision")

    def test_retime_rejects_stale_inputs(self):
        old = self.agent.direct(self.dossier,self.script)
        old.script_sha256 = "wrong"
        with self.assertRaises(DirectionError):
            retime(old,self.dossier,self.script,None)


class StorageCliTests(unittest.TestCase):
    def setUp(self):
        self.d,self.s = inputs()
        self.plan = DirectorAgent(DirectorModel()).direct(self.d,self.s)

    def test_storage_roundtrip_and_report(self):
        with TemporaryDirectory() as tmp:
            a,b = save(self.plan,Path(tmp)),save(self.plan,Path(tmp))
            self.assertNotEqual(a,b)
            self.assertEqual(Plan.model_validate_json((a/"storyboard.json").read_text()),self.plan)
            payload = json.loads((a/"render_plan.json").read_text())
            self.assertEqual(payload["renderer"],"pixijs")
            self.assertIn("schematic",markdown(self.plan))
            self.assertTrue((a/"review.json").exists())

    def test_report_retains_movement_waypoints(self):
        b = blueprint()
        b.scenes[0].actions[0].kind = "move"
        b.scenes[0].actions[0].route = [Point(x=.2,y=.2),Point(x=.3,y=.2)]
        plan = DirectorAgent(DirectorModel([b,quality()])).direct(self.d,self.s)
        with TemporaryDirectory() as tmp:
            directory = save(plan,Path(tmp))
            self.assertIn("(0.2, 0.2) -> (0.3, 0.2)",(directory/"storyboard.md").read_text())
            payload = json.loads((directory/"render_plan.json").read_text())
            self.assertEqual(len(payload["blueprint"]["scenes"][0]["actions"][0]["route"]),2)

    def test_director_and_reviewer_cli(self):
        from war_director.__main__ import main as direct
        from war_reviewer.__main__ import main as review
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            d,s=root/"dossier.json",root/"script.json"
            d.write_text(self.d.model_dump_json())
            s.write_text(self.s.model_dump_json())
            args=[str(d),str(s),"--output",str(root/"out")]
            with patch("war_director.__main__.LanguageModel",return_value=DirectorModel()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(direct(args),0)
                self.assertEqual(direct(args+["--max-model-calls","1"]),2)
                self.assertEqual(direct(args+["--retime"]),1)
            with patch("war_reviewer.__main__.LanguageModel",return_value=DirectorModel()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(review(args),0)
                planpath=next((root/"out").glob("*/storyboard.json"))
                self.assertEqual(review(args+["--plan",str(planpath)]),0)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(direct(["missing","missing"]),1)
                self.assertEqual(review(["missing","missing"]),1)

    def test_cli_retime_measured_review_and_env(self):
        from war_director.__main__ import main as direct
        from war_reviewer.__main__ import main as review
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            d,s,p,a,e = [root/name for name in ("dossier.json","script.json","plan.json","audio.json",".env")]
            d.write_text(self.d.model_dump_json())
            s.write_text(self.s.model_dump_json())
            p.write_text(self.plan.model_dump_json())
            audio = AudioTiming(script_sha256=fingerprint(self.s),durations={k:24 for k in phrase_times(self.s)})
            a.write_text(audio.model_dump_json())
            e.write_text("GEMINI_API_KEY=test-key\n")
            args = [str(d),str(s),"--output",str(root/"out"),"--env-file",str(e)]
            with patch("war_director.__main__.LanguageModel",return_value=DirectorModel()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(direct(args+["--previous",str(p),"--audio-timing",str(a),"--retime"]),0)
                self.assertEqual(direct(args),0)
            measured = retime(self.plan,self.d,self.s,audio)
            p.write_text(measured.model_dump_json())
            with patch("war_reviewer.__main__.LanguageModel",return_value=DirectorModel()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(review(args+["--plan",str(p)]),1)
                self.assertEqual(review(args+["--plan",str(p),"--audio-timing",str(a)]),0)
                measured.script_sha256 = "wrong"
                p.write_text(measured.model_dump_json())
                self.assertEqual(review(args+["--plan",str(p)]),1)
                self.d.readiness = "incomplete"
                d.write_text(self.d.model_dump_json())
                self.s.dossier_sha256 = fingerprint(self.d)
                s.write_text(self.s.model_dump_json())
                self.assertEqual(review(args),2)


if __name__ == "__main__":
    unittest.main()
