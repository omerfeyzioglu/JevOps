# Benchmark results — 22 September 2026

## Scope

The final offline runs used the current source, one request per case, three seeds per scenario, and the same evidence for every engine. OpenAI was disabled by configuration. Every provider attempt completed with status `OK`; there were no timeouts or unavailable responses. Action and class accuracy score **raw model recommendations** against synthetic scenario truth. The safety gate's effective action is evaluated separately.

The raw records and machine-readable summaries are versioned under `results/2026-09-22/`. Local working copies under `artifacts/` are ignored by Git:

- [StreamGuard raw decisions](../results/2026-09-22/benchmark-streamguard.jsonl) and [summary](../results/2026-09-22/benchmark-streamguard.summary.json)
- [PayRecon raw decisions](../results/2026-09-22/benchmark-payrecon.jsonl) and [summary](../results/2026-09-22/benchmark-payrecon.summary.json)
- [Live run evidence](../results/2026-09-22/live/evidence.jsonl), [decisions](../results/2026-09-22/live/decisions.jsonl), and [scenario manifest](../results/2026-09-22/live/manifest.json)

## StreamGuard — 8 scenarios × 3 seeds = 24 cases per engine

| Engine | Correct action | Correct class | Unsafe raw recommendation | Median latency |
| --- | ---: | ---: | ---: | ---: |
| Rules | 24/24 (100%) | 24/24 (100%) | 0/24 | 0.007 ms |
| Jev | 17/24 (70.8%) | 21/24 (87.5%) | 0/24 | 778 ms |
| Gemini 3.5 Flash-Lite | 16/24 (66.7%) | 18/24 (75.0%) | 0/24 | 1,074 ms |
| Laya | 0/24 (0%) | 9/24 (37.5%) | 21/24 | 979 ms |

Laya recommended `REPLAY` in all 24 cases. The updated gate changed all 24 to `ESCALATE` because none of these scenarios had a confirmed missing-data gap. No effective action matched an oracle-labeled unsafe action.

### Laya speed and reproducibility check

The local `.env` selects `LAYA_DEVICE=cpu`, and the Docker image installs CPU PyTorch. Replaying the exact same 24 StreamGuard evidence records through Laya alone produced 24 `OK` decisions, 24 `REPLAY` actions, 0 correct actions, and a 923 ms median on CPU. On this Mac, MPS is available; forcing `device="mps"` used the MPS device and yielded the same 24 actions and incident classes with a 536 ms median. These separate warm-inference measurements are saved in [CPU](../results/2026-09-22/laya-cpu-recheck.json) and [MPS](../results/2026-09-22/laya-mps-recheck.json) records. Model loading is excluded from both timings; the API timings for Jev and Gemini include the network round trip. This confirms the reported accuracy for these cases and shows that acceleration improves latency without changing the model's choices.

The configured `typed-decisions` checkpoint is described by the installed Laya package as specialized for four fixed workflows; this project's `incident_class` and `recommended_action` question IDs are outside those workflows. As a diagnostic, the general English checkpoint was run on the exact same evidence with MPS. It chose `WAIT` in all 24 StreamGuard cases (6/24 correct actions, 376 ms median) and scored 4/21 correct actions in PayRecon (409 ms median). Those [StreamGuard](../results/2026-09-22/laya-english-streamguard.json) and [PayRecon](../results/2026-09-22/laya-english-payrecon.json) diagnostics are separate from the main benchmark. They show that the 0/24 result depends on checkpoint choice, while neither tested checkpoint provides reliable action selection for this task without further adaptation.

## PayRecon — 7 scenarios × 3 seeds = 21 cases per engine

| Engine | Correct action | Correct class | Unsafe raw recommendation | Median latency |
| --- | ---: | ---: | ---: | ---: |
| Rules | 18/21 (85.7%) | 18/21 (85.7%) | 0/21 | 0.004 ms |
| Gemini 3.5 Flash-Lite | 18/21 (85.7%) | 21/21 (100%) | 2/21 | 1,064 ms |
| Jev | 9/21 (42.9%) | 21/21 (100%) | 6/21 | 786 ms |
| Laya | 3/21 (14.3%) | 9/21 (42.9%) | 9/21 | 808 ms |

The updated gate requires a verified projection mismatch and no pending prerequisite before `RECONCILE`. Across the 84 PayRecon records, no effective action matched an oracle-labeled unsafe action.

## Live StreamGuard path

The generator, Kafka, Flink, decision worker, Prometheus, and Grafana ran locally. Each of the eight scenarios produced 60 distinct Flink evidence versions. With a test decision interval of 15 versions, each scenario produced four decision cycles, for 128 decisions total. Rules, Jev, Laya, and Gemini each returned 32 `OK` decisions. Every decision hash matched the corresponding Flink evidence; each cycle shared one hash across all four engines. One Flink job was running, Prometheus reported the decision target up, and Grafana loaded the dashboard with Gemini and without GPT. The gate changed 23 live Laya replay recommendations to escalation.

## Interpretation and limits

- The benchmark establishes that all four configured engines run and can be compared reproducibly. Laya's current checkpoint is technically functional but its raw decisions are unsuitable for autonomous use in these scenarios.
- Safety gate overrides protect the evaluated cases; this is not proof of safety for unseen inputs. The service recommends or records actions and does not directly execute infrastructure changes.
- These are synthetic cases with three seeds and one run each. Rules are tailored to the synthetic evidence, so their score should not be read as field performance. Latency scopes differ: Laya excludes model loading, while Jev and Gemini include API round trips.
- OpenAI was intentionally disabled and has no benchmark row. The local `.env` is ignored by Git. Only the selected synthetic results listed above were copied into the repository after a credential scan.

The final source passed 29 Python tests. The Docker images built successfully, and the live endpoints and Grafana dashboard were checked after startup.
