# Benchmark results — 2 October 2026

## Executive summary

The final repository configuration was evaluated across 15 synthetic scenarios and three seeds per scenario. Rules, Jev, local Laya, and Gemini received the same immutable evidence in every case. OpenAI was disabled. All 180 provider attempts completed with status `OK`.

Rules led action accuracy in both domains: 100% on StreamGuard and 85.7% on PayRecon. Gemini followed at 62.5% and 81.0%, respectively. Jev classified every PayRecon case correctly but selected an acceptable action in 42.9% of cases. Laya's general English checkpoint improved StreamGuard action accuracy from the earlier typed-checkpoint result of 0% to 29.2%, but remained weak on both domains.

The safety gate changed 34 PayRecon recommendations. No effective action in the published matrix matched an oracle-labeled unsafe action.

## Reproducibility contract

| Setting | Value |
| --- | --- |
| Date | 2 October 2026 |
| Runs per case | 1 |
| Seeds | 101, 202, 303 |
| Engines | Rules, Jev, Laya, Gemini 3.5 Flash-Lite |
| OpenAI | Disabled |
| Laya checkpoint | `convaiinnovations/laya`, repository root |
| Laya device | CPU |
| Laya latency scope | Warm local inference; model loading excluded |
| Remote latency scope | API end to end |
| Python | 3.13.13 |
| Host | macOS arm64 |

The exact configuration is recorded in [run-metadata.json](../results/2026-10-02/run-metadata.json). Raw records and generated summaries are committed beside it:

- [StreamGuard raw JSONL](../results/2026-10-02/benchmark-streamguard.jsonl) and [summary](../results/2026-10-02/benchmark-streamguard.summary.json)
- [PayRecon raw JSONL](../results/2026-10-02/benchmark-payrecon.jsonl) and [summary](../results/2026-10-02/benchmark-payrecon.summary.json)

Run `make verify-results` to recompute both summaries and verify that all engines shared one evidence hash per case.

## Method

1. Deterministic simulation creates observable facts and private synthetic truth.
2. Each engine receives the same `EvidenceSnapshot`; scenario identity and expected answers are excluded.
3. The raw incident class and action are scored against the private truth.
4. The deterministic safety gate checks observable prerequisites and records an effective action.
5. Latency is recorded only for successful decisions.

`action_accuracy` and `unsafe_recommendation_rate` describe raw provider output. Gate overrides do not improve raw accuracy. Effective-action safety is reported separately.

## StreamGuard

Eight scenarios × three seeds produced 24 cases and 96 decisions.

| Engine | Action accuracy | Class accuracy | Unsafe raw | Unnecessary escalation | Median | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rules | 24/24 (100%) | 24/24 (100%) | 0/24 | 0/24 | 0.008 ms | 0.011 ms |
| Jev | 18/24 (75.0%) | 21/24 (87.5%) | 0/24 | 4/24 | 490 ms | 812 ms |
| Gemini 3.5 Flash-Lite | 15/24 (62.5%) | 18/24 (75.0%) | 0/24 | 7/24 | 979 ms | 1,186 ms |
| Laya | 7/24 (29.2%) | 15/24 (62.5%) | 0/24 | 0/24 | 693 ms | 815 ms |

Laya selected `WAIT` in 23 cases and `RETRY` in one. The general checkpoint is a better fit for arbitrary choice questions than the previously configured `typed-decisions` checkpoint, but its action accuracy is still too low for autonomous use.

No StreamGuard recommendation required a gate override in this run, and no effective action was oracle-labeled unsafe.

## PayRecon

Seven scenarios × three seeds produced 21 cases and 84 decisions.

| Engine | Action accuracy | Class accuracy | Unsafe raw | Unnecessary escalation | Median | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rules | 18/21 (85.7%) | 18/21 (85.7%) | 0/21 | 3/21 | 0.004 ms | 0.006 ms |
| Gemini 3.5 Flash-Lite | 17/21 (81.0%) | 20/21 (95.2%) | 3/21 | 0/21 | 971 ms | 1,191 ms |
| Jev | 9/21 (42.9%) | 21/21 (100%) | 6/21 | 0/21 | 495 ms | 581 ms |
| Laya | 3/21 (14.3%) | 5/21 (23.8%) | 9/21 | 0/21 | 700 ms | 729 ms |

The gate overrode 4 Gemini, 12 Jev, and 18 Laya recommendations. It requires a known retained gap before replay and a verified projection mismatch with no pending prerequisite before reconciliation. No effective PayRecon action was oracle-labeled unsafe.

## Live system evidence

The latest committed live system run remains under [`results/2026-09-22/live/`](../results/2026-09-22/live/). It verified the full generator, Kafka, Flink, decision worker, Prometheus, and Grafana path across all eight StreamGuard scenarios:

- 480 distinct Flink evidence records
- 128 provider decisions
- 32 `OK` decisions from each of Rules, Jev, Laya, and Gemini
- matching evidence hashes for every decision cycle
- one running Flink job and one healthy Prometheus target

That live run used the earlier Laya `typed-decisions` checkpoint. The 2 October offline benchmark supersedes it for model-quality comparisons; the live records remain evidence of the end-to-end data path.

## Interpretation

- **Rules establish the deterministic ceiling for this synthetic contract.** Their scores are expected to be strong because the rules use the same engineered facts that define the scenarios.
- **Jev is strongest on StreamGuard among the learned engines.** Its PayRecon classification is perfect in this matrix, but its action policy over-selects reconciliation and relies on the gate.
- **Gemini is strongest on PayRecon among learned engines.** It still produces unsafe raw recommendations in three cases, all blocked by the gate.
- **Laya is operationally functional but task-weak.** Local execution and lower median latency do not compensate for low action accuracy.
- **The gate is a control, not a model-quality fix.** Raw and effective actions stay separate in every audit record.

## Limits

- Results cover synthetic data, three seeds, and a single request per case.
- Provider behavior and latency can change with model releases, service load, network conditions, and SDK versions.
- Latency scopes differ between local Laya inference and remote API calls.
- The evaluator's truth is reviewed synthetic truth, not production incident labels.
- Zero unsafe effective actions in this finite matrix is not a general safety proof.
- The project does not execute actions; it records bounded recommendations and gate outcomes.
