# Visual model benchmark — October 30, 2026

The user selected **Qwen 3.8 27B through Groq** for visuals after this comparison. The
engine defaults were updated accordingly. Research/writing use the separately selected
Gemini 3.8 Flash → Gemini 3.5 Flash-Lite chain.

## Method

Ten model routes were attempted, including both Groq GPT-OSS sizes. MiniMax's discussed
free variant was checked against the current catalog and skipped because no callable
zero-price route was listed. No paid MiniMax inference was requested.

Each model received the same two briefs: a tank with tracks, hull, turret and right-facing
barrel; and a top-down repeatable cliff motif. One attempt per brief, no output repair or
model fallback. All successful designs were rendered by the same PixiJS primitive interpreter,
at inspection size and small map size. Schema validity measures renderability, not art quality.

Vision-capable models also received two real map screenshots without their scene JSON.
One contains overlapping labels and a tank in water with no bridge; the control has clear
labels, a bridge and tanks on land. Eight fixed observations were scored. This tests basic
spatial inspection and controls for false positives; it does not establish general visual
reasoning, animation understanding or historical correctness.

Text-only models were not sent images and receive no image score. Provider errors are
availability results, not evidence that a model cannot design. Same prompts do not imply
identical backend schema enforcement: Gemini and selected OpenRouter routes support native
schemas, while Groq uses JSON mode. This compares the actual adapters intended for this project.

## Results

| Model / provider | Renderable designs | Image observations | Notes |
|---|---:|---:|---|
| Qwen 3.8 27B / Groq | 2/2 | 8/8 | Most usable combined result in this trial |
| GPT-OSS 120B / Groq | 2/2 | Not supported | Useful design candidate; text-only |
| GPT-OSS 20B / Groq | 1/2 | Not supported | Tank request returned HTTP 400 |
| Gemini 3.5 Flash-Lite | 1/2 | 8/8 | Cliff failed geometry validation |
| Gemini 3.8 Flash | 0/2 | Request failed | Network/503 failures; quality not established |
| Dots3 Note Preview / OpenRouter | 1/2 | 8/8 | Cliff response truncated at output limit |
| Nemotron 3.5 Super VL / OpenRouter | 1/2 | 7/8 | Cliff failed geometry validation |
| Nemotron 3.5 Lightning / OpenRouter | 0/2 | Not supported | Truncated/invalid structured output |
| Nemotron 3 Ultra / OpenRouter | 0/2 | Not supported | Provider returned API 502 |
| Inkling Small / OpenRouter | 0/2 | Request failed | Route returned HTTP 403 |
| MiniMax M3 free / OpenRouter | Not attempted | Not attempted | Free variant absent from live zero-price catalog |

Manual gallery inspection also matters. Qwen's sample had the clearest match to the
right-facing tank and top-down cliff briefs. GPT-OSS 120B returned valid JSON for both,
but the tank's track arrangement and bridge-like cliff silhouette still needed visual
revision. Flash-Lite's tank geometry was valid but its orientation did not match the
brief well. These are observations about single examples, not universal model rankings.

This finding led to the engine's rendered-asset review step: valid JSON alone is
insufficient. The reviewer now sees the actual rendered symbol, including its small
map appearance, before the CLI accepts a new asset.

## Reproduce

```powershell
node renderer/probes.mjs
python -m war_content.benchmark --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
node renderer/gallery.mjs

# Keep completed results and only test additional/missing candidates.
python -m war_content.benchmark --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env' --resume
```

`--output` and `--probes` select separate runs/datasets. Resume verifies a fingerprint
of the design prompts, briefs and input PNGs. Each model is limited to two design calls
and, if applicable, one image call. HTTP transport retries may add physical requests.
Results record actual returned model IDs, latency, errors and drawings. A renderer
gallery is provided for human assessment rather than allowing a model to grade its own art.

Local outputs, ignored by Git:

- [Rendered gallery](../output/benchmarks/visual/gallery.png)
- [Raw results](../output/benchmarks/visual/results.json)
- [Detailed generated report](../output/benchmarks/visual/report.md)
- [Control screenshot](../output/benchmarks/probes/control.png)
- [Problem screenshot](../output/benchmarks/probes/problem.png)

## Access and limitations

The catalog was fetched immediately before the tests. OpenRouter requests carried a
zero-price provider cap. MiniMax's paid catalog entries were not used. The older usage
chart showing MiniMax does not establish that its free endpoint is callable now.
Groq and Gemini used their existing configured keys without billing changes.

Free quotas are part of suitability: Groq currently documents an 8K TPM free-plan
limit for Qwen/GPT-OSS, with account-specific limits taking precedence. A multi-asset
build may need token-reset waits or a later resumed run. Broader comparisons should
repeat multiple seeds/topics and include finished-video inspection; these results are
an initial project-specific smoke comparison.

Sources: [OpenRouter catalog](https://openrouter.ai/api/v1/models),
[free model access](https://openrouter.ai/collections/free-models),
[Groq vision support](https://console.groq.com/docs/vision),
[Groq limits](https://console.groq.com/docs/rate-limits),
[Gemini pricing and free tiers](https://ai.google.dev/gemini-api/docs/pricing).
