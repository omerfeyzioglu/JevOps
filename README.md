# JevOps

JevOps compares bounded operational decisions from deterministic Rules, Jev, and an LLM. All three engines receive the same immutable evidence; deterministic code owns aggregation, lifecycle checks, and safety prerequisites. The models recommend actions but never execute infrastructure changes.

StreamGuard is the live demo. A seeded generator publishes operational events to Kafka, Flink turns a rolling window into `EvidenceSnapshot` records, and a Python worker runs the existing adapters and authoritative safety gate. Prometheus and Grafana show the incident and decision behavior. The existing offline StreamGuard benchmark and PayRecon simulation remain available.

```text
scenario generator → Kafka → Flink → evidence topic → decision worker
                                                        ├─ Rules
                                                        ├─ Jev
                                                        └─ LLM
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

Without credentials, Jev and LLM are recorded as `UNAVAILABLE`; no fake decisions are substituted. To enable them, copy `.env.example` to `.env`, add `TYPESAFE_API_KEY` and/or `ANTHROPIC_API_KEY`, and restart `decision-service`. `DECISION_EVERY_N_SNAPSHOTS` controls provider call frequency.

Stop the stack with `docker compose down`. Add `-v` only when you also want to remove persisted local Kafka data.

## Offline benchmark and tests

Requires Python 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m jevops smoke-suite
.venv/bin/python -m jevops benchmark --runs 1 --output artifacts/benchmark.jsonl
.venv/bin/python -m unittest discover -s tests -v
```

The benchmark runs all StreamGuard scenarios with three seeds, gives Rules, Jev, and the LLM the same evidence, writes raw JSONL, prints one summary row per engine, and saves the same summary beside the raw file as `benchmark.summary.json`. `--runs N` repeats every provider request without caching. The smaller `smoke-suite` remains available for quick contract checks.

Run one original scenario with `jevops simulate --scenario traffic_spike --seed 401`, or PayRecon with `jevops payrecon --scenario projection_mismatch --seed 602`. See [docs/architecture.md](docs/architecture.md) for the decision boundary.
