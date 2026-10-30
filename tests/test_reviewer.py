import unittest
from war_reviewer.agent import ReviewerAgent
from war_reviewer.models import Findings, Issue, Scores
from war_writer.agent import fingerprint
from .writer_helpers import draft


class ReviewModel:
    def __init__(self):
        self.used = []
        self.result = Findings(scores=Scores(accuracy=4, clarity=4, visual_logic=4, voice=4, readability=4), issues=[])

    def generate(self, prompt, schema, consume):
        consume()
        self.used.append("fake:reviewer")
        return self.result.model_copy(deep=True)


class ReviewerTests(unittest.TestCase):
    def test_pass_low_score_and_blockers(self):
        artifact, model = draft(), ReviewModel()
        reviewer = ReviewerAgent(model)
        review = reviewer.review(artifact, {}, lambda: None)
        self.assertEqual(review.status, "pass")
        self.assertEqual(review.artifact_sha256, fingerprint(artifact))
        self.assertEqual(review.models_used, ["fake:reviewer"])
        model.result.scores.accuracy = 2
        self.assertEqual(reviewer.review(artifact, {}, lambda: None).status, "revise")
        model.result.scores.accuracy = 4
        model.result.issues = [Issue(severity="blocking", message="An unsupported maneuver is depicted.")]
        self.assertEqual(reviewer.review(artifact, {}, lambda: None).status, "revise")

    def test_local_issues_cannot_be_overridden(self):
        review = ReviewerAgent(ReviewModel()).review(draft(), {}, lambda: None, ["Known invalid route"])
        self.assertEqual(review.status, "revise")
        self.assertEqual(review.local_issues, ["Known invalid route"])

    def test_advisory_does_not_block_and_consumes_budget(self):
        model, calls = ReviewModel(), []
        model.result.issues = [Issue(severity="advisory", message="Consider a calmer opening delivery.")]
        review = ReviewerAgent(model).review(draft(), {}, lambda: calls.append(1))
        self.assertEqual(review.status, "pass")
        self.assertEqual(calls, [1])
