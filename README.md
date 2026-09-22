# JevOps

[Latest local benchmark results](docs/benchmark-results-2026-09-22.md)

JevOps compares bounded operational decisions from deterministic Rules, Jev, local Laya, GPT-5.6 Luna, and Gemini 3.5 Flash-Lite. All five engines receive the same immutable evidence; deterministic code owns aggregation, lifecycle checks, and safety prerequisites. The models recommend actions but never execute infrastructure changes.

StreamGuard is the live demo. A seeded generator publishes operational events to Kafka, Flink turns a rolling window into `EvidenceSnapshot` records, and a Python worker runs the existing adapters and authoritative safety gate. Prometheus and Grafana show the incident and decision behavior. The existing offline StreamGuard benchmark and PayRecon simulation remain available.

```text
scenario generator → Kafka → Flink → evidence topic → decision worker
                                                        ├─ Rules
                                                        ├─ Jev
                                                        ├─ Laya (local)
                                                        ├─ GPT-5.6 Luna
                                                        └─ Gemini 3.5 Flash-Lite
                                              → safety gate → Prometheus → Grafana
```

## Run the live demo

Docker with Compose is required.

```bash
docker compose up --build -d
docker compose run --rm scenario-generator \
  --scenario traffic_spike_sink_degradation --seed 401
```

Open the [StreamGuard Grafana dashboard](http://localhost:3000/d/streamguard-live/streamguard-live-demo) (anonymous viewer is enabled). Flink is at [localhost:8081](http://localhost:8081), Prometheus at [localhost:9090](http://localhost:9090), and raw application metrics at [localhost:8000/metrics](http://localhost:8000/metrics).

Available live scenarios are `normal`, `traffic_spike`, `sink_slowdown_recoverable`, `sink_failure_persistent`, `ambiguous_early`, `intermittent_failure`, `false_recovery`, and `traffic_spike_sink_degradation`. Add `--duration 90` or `--interval 0.25` to change the run length or playback speed.

Laya runs locally and downloads its configured checkpoint on first use; it requires no API key. The default is `convaiinnovations/laya` with the `typed-decisions` checkpoint. Set `LAYA_MODEL`, `LAYA_SUBFOLDER`, and optionally `LAYA_DEVICE` (`cpu`, `mps`, or `cuda`) in your local `.env` to change it. `LAYA_ENABLED=false` explicitly disables local inference. Laya's reported `elapsed_ms` is local inference time after model loading; Jev, GPT, and Gemini report API end-to-end latency. Without credentials, those three remote providers are recorded as `UNAVAILABLE`; no fake decisions are substituted. To enable them, copy `.env.example` to `.env`, add `TYPESAFE_API_KEY`, `OPENAI_API_KEY`, and/or `GEMINI_API_KEY`, and restart `decision-service`. Set `OPENAI_ENABLED=false` to omit GPT from live decisions and benchmark rows without removing its adapter. Gemini defaults to `gemini-3.5-flash-lite`; set `GEMINI_MODEL` to select another model available to your API key. `DECISION_EVERY_N_SNAPSHOTS` controls provider call frequency.

Stop the stack with `docker compose down`. Add `-v` only when you also want to remove persisted local Kafka data and the Docker Laya model cache. The decision-service image uses CPU PyTorch, and the first Docker run downloads the Laya checkpoint into a persistent volume.

## Offline benchmark and tests

Requires Python 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m jevops smoke-suite
set -a && source .env && set +a
.venv/bin/python -m jevops benchmark --runs 1 --output artifacts/benchmark.jsonl
.venv/bin/python -m jevops payrecon-benchmark --runs 1 --output artifacts/payrecon-benchmark.jsonl
.venv/bin/python -m unittest discover -s tests -v
```

Set `TYPESAFE_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` to compare Rules, Jev, local Laya, GPT-5.6 Luna, and Gemini 3.5 Flash-Lite in the live demo, StreamGuard commands, and PayRecon. The benchmark commands run every scenario in their domain with three seeds, give every engine the same evidence, write raw JSONL, print one summary row per engine, and save the same summary beside the raw file as a `.summary.json` file. `--runs N` repeats every provider request without application-level caching. The smaller `smoke-suite` remains available for quick contract checks.

Benchmark accuracy and unsafe recommendation rates score the providers' raw recommendations. Each raw record also contains the safety gate's effective action. StreamGuard replay requires a confirmed missing-data gap as well as a retained source, known checkpoint, and healthy sink. The current scenarios contain no confirmed replay gap, so the gate escalates replay requests. PayRecon reconciliation requires a verified projection mismatch with no pending prerequisite or integrity conflict.

Run one original scenario with `jevops simulate --scenario traffic_spike --seed 401`, or PayRecon with `jevops payrecon --scenario projection_mismatch --seed 602`. See [docs/architecture.md](docs/architecture.md) for the decision boundary.
