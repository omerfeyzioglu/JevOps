# Corrected benchmark — 2 October 2026

## What was corrected

The previous Laya integration used the SDK's default 512-token context and 192-token question head. Rebuilding the exact requests shows truncation in **69 of 90 question inputs**. This includes evidence/policy text and option descriptions. [Input audit](../results/2026-10-02-corrected/input-audit.json) preserves the original and corrected lengths for every fixture. Earlier Laya scores describe that truncated integration and are superseded for full-evidence comparisons.

The corrected adapter preserves every evidence field and the complete shared rubric using lossless compact JSON, a 1,024-token context, and a 384-token question head. A preflight check rejects any request that would truncate instructions, options, or evidence. All 90 final inputs fit; the largest uses 613 tokens. These context settings differ from the checkpoint's training/default settings and can affect behavior; they were chosen to retain the full request, without selecting them for the highest test score.

The common PayRecon action definitions now explicitly include the safety gate's prerequisites: a verified mismatch, complete source, no pending prerequisite, and no integrity conflict before reconciliation; a known retained missing event without conflict before replay. All learned engines receive the same revised definitions. The deterministic Rules adapter also handles a complete, matching healthy projection instead of falling through to escalation. The synthetic truth and gate policies were not changed.

CPU is a valid deployment target. The earlier CPU measurements were not invalid solely because they used CPU. This run uses native Apple MPS for the primary comparison and a matched native CPU control to measure hardware separately. Docker installs the locked SDK/runtime dependencies instead of resolving a newer Laya release on each build.

## Final experiment

- 15 scenarios, three seeds, and **three repeated calls per fixture**
- 540 primary decisions: 288 StreamGuard and 252 PayRecon
- 135 additional Laya CPU control decisions on the same fixtures and repeats
- All 675 final calls returned `OK`; zero missing cases or truncated inputs
- Two Laya warmup calls per device, excluded from the tables
- Sequential provider calls, with deterministic rotation of provider order
- Apple M4, macOS arm64, Python 3.12.13, PyTorch 2.14.0, Laya 0.3.4, four CPU threads
- Root English checkpoint revision `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851`; OpenAI disabled

[Runtime metadata and source hashes](../results/2026-10-02-corrected/run-metadata.json), [warmup records](../results/2026-10-02-corrected/warmup-records.json), and [raw data](../results/2026-10-02-corrected/) are committed. Accuracy scores raw recommendations against private synthetic truth; gate outcomes remain separate. Remote latency includes SDK client construction and the API round trip. Laya latency includes serialization, token validation, and model inference, excluding model loading.

## StreamGuard — 24 fixtures × 3 repeats

| Engine | Raw action accuracy | Class accuracy | Unsafe raw | Unnecessary escalation | Median | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rules | 72/72 (100.0%) | 72/72 (100.0%) | 0/72 | 0/72 | 0.006 ms | 0.010 ms |
| Jev | 55/72 (76.4%) | 63/72 (87.5%) | 0/72 | 11/72 | 486 ms | 780 ms |
| Gemini 3.5 Flash-Lite | 49/72 (68.1%) | 52/72 (72.2%) | 0/72 | 20/72 | 950 ms | 1,118 ms |
| Laya (MPS) | 45/72 (62.5%) | 18/72 (25.0%) | 0/72 | 0/72 | 519 ms | 571 ms |

No StreamGuard recommendation was overridden or oracle-labeled unsafe. Laya selected `RETRY` in 66 of 72 calls and `WAIT` in six; its class distribution was mostly `MIXED`. Higher action accuracy does not imply reliable classification.

## PayRecon — 21 fixture identifiers × 3 repeats

| Engine | Raw action accuracy | Class accuracy | Unsafe raw | Unnecessary escalation | Median | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rules | 63/63 (100.0%) | 63/63 (100.0%) | 0/63 | 0/63 | 0.005 ms | 0.008 ms |
| Gemini 3.5 Flash-Lite | 63/63 (100.0%) | 63/63 (100.0%) | 0/63 | 0/63 | 946 ms | 1,143 ms |
| Jev | 54/63 (85.7%) | 63/63 (100.0%) | 0/63 | 0/63 | 478 ms | 640 ms |
| Laya (MPS) | 18/63 (28.6%) | 27/63 (42.9%) | 12/63 | 0/63 | 461 ms | 512 ms |

The gate changed 45 Laya and nine Jev recommendations. All 12 oracle-labeled unsafe raw recommendations came from Laya and were blocked. No effective action in this matrix was oracle-labeled unsafe. Zero oracle-labeled unsafe Jev recommendations does not mean zero policy violations: nine recommendations still failed gate prerequisites.

## Laya device control

| Domain | MPS median / p95 | CPU median / p95 | Matching class and action |
| --- | ---: | ---: | ---: |
| StreamGuard | 519 ms / 571 ms | 861 ms / 946 ms | 72/72 |
| PayRecon | 461 ms / 512 ms | 759 ms / 958 ms | 63/63 |

These are two-question calls with substantial operational evidence and a ModernBERT-large based model. Local execution removes network latency but still requires neural computation. The author's [model card](https://huggingface.co/convaiinnovations/laya#benchmarks) measures its roughly 33–40 ms single-question figures on a Tesla T4, which differs from this Apple M4 workload and device. CPU and MPS use float32 in the pinned SDK. This run establishes measured speed on the available hardware; it does not reproduce the author's GPU benchmark.

## Diagnostic progression

The [full-input run with original action definitions](../results/2026-10-02-corrected/diagnostics/input-only-original-policy/) was preserved before applying the shared policy clarification. It used the same three repeats and MPS/CPU controls. In that stage Laya scored 62.5% StreamGuard and 14.3% PayRecon action accuracy; Jev scored 42.9% and Gemini 77.8% on PayRecon. The final revised PayRecon definitions changed those measured results to 28.6%, 85.7%, and 100%, respectively. This is a development diagnostic on the same fixtures, not an independent held-out validation.

## Reproduce and verify

```bash
make setup
set -a && source .env && set +a
make benchmark BENCHMARK_ARGS="--runs 3 --laya-device mps --cpu-comparison"
make test
make verify-results
```

Use `--laya-device cpu` on a CPU host, or `cuda` on a compatible GPU. Outputs go to `artifacts/verified-benchmarks/`. Runtime device, package versions, checkpoint revision, and source hashes are generated automatically. Exact reproduction of the checkpoint requires loading the recorded Hugging Face revision from a local snapshot; model repositories and remote services can change.

The verifier replays seeded simulation and independently recomputes evidence hashes, oracle scores, gate results, complete scenario/seed/run/engine coverage, and summaries. It verifies the diagnostic subdirectory as well. Unit tests include rejection of oversized Laya requests and detection of tampered scores and duplicate records.

All 36 unit tests passed both natively and in the built Linux Docker image. A separate real-model [container smoke check](../results/2026-10-02-corrected/container-validation/runtime.json) covered all 15 scenarios with seed 101: 15 `OK` decisions, CPU execution, and no truncated inputs. Its [raw records](../results/2026-10-02-corrected/container-validation/decisions.jsonl) validate deployment compatibility; their latency is not part of the native device comparison above.

## Live-path scope

The committed [September live run](../results/2026-09-22/live/) remains transport evidence for Kafka, Flink, the worker, Prometheus, and Grafana. Its Laya decisions used the older integration. The corrected input checker was separately applied to all 480 archived live evidence records in [live-input-audit.json](../results/2026-10-02-corrected/live-input-audit.json); that is input-fit validation, not a new live accuracy benchmark.

## Limits

- StreamGuard has 24 distinct operational fixture states. PayRecon has **seven**: its three seeds change identifiers, not operational facts. Neither three seeds nor three repeats turn those into independent payment examples.
- Fixtures and policy definitions are developed in this repository. These results are regression/development benchmarks, not blind evaluation on unseen production data.
- Rules are a synthetic-contract control. Their 100% score is not evidence of general production performance.
- Laya still has weak incident classification and weak PayRecon action accuracy; fixing integration does not establish autonomous-use readiness.
- Safety is tested against finite oracle labels and observable prerequisites. Zero unsafe effective actions here is not a general safety proof.
- API outputs and latency can vary with service releases and load. No CUDA or Tesla T4 hardware was tested.
- The project records recommendations and gate outcomes; it has no action executor.
