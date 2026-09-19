# Jev research and proposed integration

Reviewed 2026-09-20. Findings below come from TypeSafe's official documentation and repositories. Community search results were useful discovery leads but are not treated as authoritative API documentation. No authenticated request or latency/cost benchmark was run.

## Verified integration surface

The [HTTP reference](https://docs.typesafe.ai/api) documents `POST https://api.typesafe.ai/v1/systemone` with bearer authentication and `model`, `state`, and `questions`. State can be structured JSON. Question IDs associate responses with callers; they do not supply meaning to the model. Put the full question in instructions and option criteria. Answers and usage are returned in a structured response.

Use the [official Python SDK](https://docs.typesafe.ai/sdk/python), package `typesafe-sdk`, import `typesafe_sdk`, and `AsyncTypeSafeClient`. The [inspected v0.7.0 release](https://github.com/typesafe-ai/typesafe-sdk-python/releases/tag/v0.7.0) changed serialization to Pydantic; its [package metadata](https://github.com/typesafe-ai/typesafe-sdk-python/blob/v0.7.0/pyproject.toml) requires Python >=3.10. Plan to pin 0.7.0 initially after a Python 3.12 compatibility smoke test. Do not copy a third-party SDK wrapper.

The [model page](https://docs.typesafe.ai/models) currently lists `jev-1.13.0`, with aliases including `jev-latest`. Pin the versioned ID and record the response's model field. It lists input-token billing at USD 0.042 per million and free output tokens, but access, prices, and quotas must be rechecked before running. Usage tokens are not a guaranteed dollar-cost field. Do not import a gateway model ID into a direct TypeSafe request without verification.

The [SDK retry reference](https://docs.typesafe.ai/sdk/python/api/retries) documents default retries and configurable `RetryPolicy`. Explicitly disable retries for primary timing and verify the installed SDK accepts the configuration. Exercise timeout, 429, overloaded, invalid-response, and connection-error handling through offline fixtures before paid calls. Log attempts and elapsed wall time; do not mistake SDK retry time for inference time.

## Use the right primitive

| Primitive | Meaning | Project use |
| --- | --- | --- |
| [Choice](https://docs.typesafe.ai/primitives/choice) | One option, distribution over options, and a separate confidence statistic | Primary: one incident-class Choice plus one action Choice over the common evidence |
| [Noul](https://docs.typesafe.ai/primitives/noul) | Probability that a defined yes/no proposition holds; no separate confidence | Optional diagnostic: “Do the supplied dependency observations support a transient failure?” Not a permissions gate |
| [Score](https://docs.typesafe.ai/primitives/score) | Expected position on ordered rubric levels, from 0 to number-of-levels minus one | Deferred: qualitative operational impact such as contained/degraded/blocked; never money, exact delay, or arbitrary action ordering |

Do not add questions solely to showcase every primitive. WAIT/REPLAY/RECONCILE/ESCALATE are categorical choices, not points on a severity scale. Code computes amount equality, elapsed time, counts, deadlines, and safe replay eligibility.

Both MVP Choices share one request. They are independent and cannot consume each other's predictions. Ask the action question directly from evidence and supplied policy, not “given your classification.” Inconsistent class/action pairs are recorded; the safety gate validates the action's actual preconditions.

A future Noul/Score diagnostic must have an independently defined use and receive its own ablation. Extra questions change token cost and may change measured latency. They are excluded from the minimal comparison until justified.

## Request design sketch — not executable integration code

| Field | Planned content |
| --- | --- |
| `model` | `jev-1.13.0` after access verification |
| `state` | Exact common evidence snapshot from the context builder |
| `questions.incident_class.type` | `choice` |
| `questions.incident_class.instructions` | Identify the best-supported incident interpretation from currently available evidence; select MIXED for supported overlap or UNKNOWN when insufficient |
| `questions.incident_class.criteria` | Descriptions of every domain class in the shared rubric |
| `questions.action.type` | `choice` |
| `questions.action.instructions` | Choose the next bounded triage action using current evidence and supplied policy; select ESCALATE when no justified automated option remains |
| `questions.action.criteria` | Action meanings, exclusions, and safety prerequisites from decision-contract.md |

Keep initial criteria as plain text descriptions, which the HTTP reference documents directly. The broader primitive guidance also describes richer structured criteria; verify SDK serialization before adopting them. Do not invent temperature, streaming, max-output-token, or prose-explanation fields for Jev.

## Known limitations relevant to these projects

TypeSafe's [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) warn about precise arithmetic, time comparisons, indirection, distracting state, literal interpretation, and inconsistent related judgments. Therefore preprocess measured facts, keep state bounded, include unknown outcomes, and enforce action invariants in ordinary code. Typed answers do not establish correctness or safety.

The [confidence guide](https://docs.typesafe.ai/confidence) describes confidence as a summary of distribution shape. It is not necessarily the chosen option's probability or a calibrated likelihood that our workflow is safe. Any threshold is selected on validation data and reported with its coverage. Noul 0.5 means uncertainty about a proposition, not medium severity.

## Official examples inspected

- [Choice guidance and triage example](https://docs.typesafe.ai/primitives/choice): shows routing with several independent judgments and code-owned branching. We adopt the bounded routing pattern, not its sample thresholds.
- [Smart-home demo](https://docs.typesafe.ai/demos/smart-home): shows shared-state question fan-out. The page says full source will be released; this review inspected the explanation, not an unverified runnable repository. Our MVP needs two questions, not a large speculative tree.
- [Choice self-consistency cookbook](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook): demonstrates repeated evaluations and uncertainty/coverage tradeoffs. Its results belong to its own task and cannot be used as JevOps evidence. Our primary repeats keep payloads identical rather than adding a random field.
- [Building guide](https://docs.typesafe.ai/concepts/how-to-build-with-system-one) and [state guide](https://docs.typesafe.ai/concepts/state): support small judgments over named evidence with arithmetic and execution retained in code.

The documentation includes downstream model-training examples. They solve a different problem and do not justify training here.

## Official agent guidance

The [official agent-skill page](https://docs.typesafe.ai/agent-skill) points to [typesafe-ai/skills](https://github.com/typesafe-ai/skills/tree/main/skills/typesafe-ai). Its SKILL.md was read during planning; the directory listing contained SKILL.md and an MIT LICENSE. The inspected SKILL.md Git blob was `0109513f9656917dc93cbc5ecddfca465a53ce66`; the directory may change.

Decision: use its guidance, link it here and from AGENTS.md, and avoid copying or automatically installing a second instruction bundle. The useful persistent project-specific rules are in AGENTS.md and this note. This keeps API guidance tied to current official docs and avoids vendored instructions going stale. A dedicated project skill would duplicate these files today. If later installed at the user's request, use the official complete directory with its license and record the pinned revision.

The separately discovered `dbreunig/building-with-jev-skill` is not the official source identified by TypeSafe's installation page; it is not required or installed.

## General-purpose LLM comparator

Proposed default: Anthropic direct API, `claude-haiku-4-5-20251001`, a small general-purpose model rather than a deliberately expensive reasoning configuration. The current [model catalog](https://platform.claude.com/docs/en/models/overview) lists this model ID, and the [structured-output docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) list Haiku 4.5 support. Verify account access and pin the SDK when implementing.

Use one Messages request with `output_config.format` JSON schema for the two required enum fields. Disable extended thinking, use temperature zero where supported, and a small sufficient output budget, initially 256 tokens. Treat refusal/truncation as failures, not fabricated decisions. Keep the same evidence, label rubrics, and no-shot setup as Jev; any few-shot experiment supplies equivalent examples to both. No explanation generation or tools in the primary benchmark.

This choice tests one practical LLM configuration, not the strongest possible LLM. If credentials favor another provider, choose it before evaluation and document the change. Do not silently swap models during a run.

## Implementation-time verification checklist

Confirm runtime compatibility, installed SDK signatures, pinned model availability, request serialization, answer validation, usage fields, retry controls, and error mapping. Save a small redacted live response once execution is authorized. Recheck the [TypeSafe documentation index](https://docs.typesafe.ai/llms.txt), model pricing, and provider quotas before paid benchmarks. These remaining checks do not block planning, but they block claims that an integration has been validated.
