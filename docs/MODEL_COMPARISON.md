# Writer model comparison — October 30, 2026

> Updated configuration: research/writing now use Gemini 3.8 Flash with Gemini 3.5 Flash-Lite fallback. Qwen 3.8 27B through Groq is selected for visuals. See [the visual benchmark](VISUAL_MODEL_BENCHMARK.md) for the completed later comparison; earlier notes below remain historical.

**Current decision:** use Gemini's free API for the writer and postpone other model
comparisons, following the user's final direction. The notes below record exploratory
checks from this build; they do not establish a writing-quality winner. Gemini TTS is a
separate audio choice. The exploratory OpenRouter jobs have ended or been stopped.

## Current candidates

| Model | Access and pricing | Structured output | Practical implication |
|---|---|---|---|
| NVIDIA Nemotron 3 Ultra free | $0 input/output; rate-limited free route | Its current free endpoint does not enforce `response_format` | Initial free candidate; prompt for JSON, validate locally, and repair once |
| MiniMax M2.7 direct | Live API catalog: $0.30 input / $1.20 output per million tokens; web page also showed discounts | JSON mode; not schema enforcement | Paid direct alternative; not established as the best narrator |
| MiniMax M3 direct | Live API catalog: $0.30 / $1.20 per million; web page also showed discounts | JSON-schema structured outputs | Paid direct candidate with output-format controls and multimodal input |
| MiniMax M3 free variant | A zero-price :free page exists and M3 appears in the Free Models Router's usage chart | Current callable availability needs checking | The direct :free call returned 404 with our key; the live catalog omitted this variant |
| MiniMax M3.1 Flash | Free launch ended October 22; normal listed rates $0.15 / $0.60 per million, with discounted provider routes displayed from $0.06 / $0.24 | JSON-schema structured outputs | A relevant newer MiniMax candidate if a small paid budget becomes acceptable |

Prices depend on provider, discounts, and routing. These are the pages checked for
this report, not a contractual price or a guarantee of continuing availability:

- [Nemotron 3 Ultra free](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free)
- [MiniMax M2.7](https://openrouter.ai/minimax/minimax-m2.7)
- [MiniMax M3](https://openrouter.ai/minimax/minimax-m3)
- [MiniMax M3 free variant](https://openrouter.ai/minimax/minimax-m3:free)
- [Free Models Router](https://openrouter.ai/openrouter/free)
- [Live API catalog](https://openrouter.ai/api/v1/models)
- [MiniMax M3.1 Flash](https://openrouter.ai/minimax/minimax-m3.1-flash)

M3.1 Flash's page shows a provider discount that differs from its normal-price banner;
verify the selected provider before budgeting. Reasoning tokens, reviews, retries, and
OpenRouter fees may affect total paid use. No paid MiniMax inference was performed.

## What “better” means for this project

General reasoning, coding, and agent benchmarks cannot establish which model produces
the best 105-second historical explanation. OpenRouter also explicitly describes its
free-model popularity ranking as usage, not a quality benchmark.

The useful comparison is the same ready dossier, duration target, writing prompt and
checks, scored on:

1. **Factual support:** no invented ratios, motives, troop movements, or precise figures.
2. **Story:** an accurate hook and understandable cause -> action -> consequence.
3. **Spoken delivery:** natural phrasing, purposeful pauses, restrained emphasis, useful
   pronunciation guidance, and variation without theatrical shouting.
4. **Format adherence:** valid structured scenes, claim references, and a usable TTS plan.
5. **Efficiency:** end-to-end latency, repair attempts, quota availability, and final cost.

Narration quality also needs listening tests with the same TTS voice. A text-only review
cannot show that one model's directions sound more human when synthesized.

## Decision for this build

Gemini is the writer default, using `gemini-3.5-flash-lite`. OpenRouter and Groq remain
optional adapters for later tests. Explicit OpenRouter use can choose a pinned model
with `--model` or `OPENROUTER_MODEL`. The dynamic `openrouter/free` route is also supported,
and the adapter records the actual model returned; it does not guarantee a MiniMax choice.
The OpenRouter adapter sends a zero-price provider cap, so a paid model ID will not
silently incur a bill. Paid MiniMax testing would require deliberately changing that
configuration in a later task. No API keys are included in source code or reports.

The user's screenshot correctly showed MiniMax M3 in free-router usage. Our initial
statement that MiniMax could only be paid was too broad: paid direct routes, free
variants, and router usage history must be distinguished. The public :free page and
live API disagreed about callable availability during this check. That is a result for
this endpoint/account at this time, not proof MiniMax never has free access.

Free does not mean unlimited. OpenRouter's free catalog currently describes 20 requests
per minute and 50 per day without the qualifying credit purchase, with a larger daily
allowance after purchasing credits. Account-specific limits and upstream availability
still apply. See [free model access](https://openrouter.ai/collections/free-models/) and
[limits](https://openrouter.ai/docs/api_reference/limits).

Cerebras was also checked: its current documentation describes a $5, 30-day trial after
adding a payment method, and explicitly says it has no permanently renewing free tier.
It is therefore not an ongoing free replacement for this project. See
[Cerebras rate limits and trial terms](https://inference-docs.cerebras.ai/support/rate-limits).
