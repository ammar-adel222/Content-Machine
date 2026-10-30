# Quality reviewer — foundation report

The independent `war_reviewer` package reviews a Pydantic artifact against supplied
research context through the shared language-model adapter. It adds no dependencies.

Call `ReviewerAgent(model).review(artifact, context, consume, local_issues=None)`.
The consume callback enforces the caller's model budget. `QualityReview` records the
artifact SHA-256, model identities, issues, five scores and pass/revise status.

Scores cover accuracy, clarity, visual logic, voice and phone readability. Any score
below four, blocking finding, or known local issue requires revision. Advisory findings
are retained without blocking. Code calculates status; the model cannot override it.

The package accepts injected services and performs no publishing or source changes.
Offline tests verify scores, blocking/advisory issues, local failures, fingerprints,
model identities and budget callbacks. Run `python -m unittest tests.test_reviewer -v`.

This reviews text and plans. It does not inspect rendered video/audio or independently
verify sources. The default model family matches generation. The following director
component adds the CLI, integration tests and bounded repair loops, and expands this report.
