# JevOps — two experiments in real-time exception triage

**Status: local StreamGuard and PayRecon slices implemented; no provider benchmark results yet.**

Monitoring can identify a backlog without explaining its cause. Payment reconciliation can identify a mismatch without knowing whether it needs immediate intervention. JevOps will compare **Rules, Jev, and one general-purpose LLM** on those bounded decisions using the same evidence.

| Experiment | Deterministic responsibility | Decision-layer responsibility |
| --- | --- | --- |
| **StreamGuard** | Produce/consume events, measure symptoms, detect an operational anomaly | Classify the incident and recommend WAIT, RETRY, PAUSE, REPLAY, or ESCALATE |
| **PayRecon** | Deduplicate events, validate lifecycle transitions, reconcile synthetic records | Classify an exception and recommend WAIT, REPLAY, RECONCILE, or ESCALATE |

The hypothesis is that Jev can offer a useful quality/latency/cost tradeoff for ambiguous triage. It is a hypothesis, not a promised result. Strong rules may win, especially on numeric evidence. A negative result is publishable and useful.

## Scope

One Python application with two domain modules and a shared evaluation harness. Start locally without a broker; add a single Redpanda broker and Grafana/Prometheus for the live demo. Use SQLite for transactional local state and JSONL for reproducible evidence/results. No training pipeline, agent runtime, Kubernetes, Spark, Airflow, external database server, or custom frontend.

All data is synthetic. All remediation is shadow-mode or acts only on an isolated simulator. No payment execution, real ledger correction, or infrastructure control is exposed to a model.

## Review the plan

1. [Phased roadmap and first vertical slice](ROADMAP.md)
2. [Architecture, stack decisions, and proposed repository structure](docs/architecture.md)
3. [Scenario generation, lifecycle rules, and ground truth](docs/scenarios.md)
4. [Evidence, decision interfaces, and action safety](docs/decision-contract.md)
5. [Fair benchmark methodology and limitations](docs/benchmark-methodology.md)
6. [Jev research, SDK integration, and source register](docs/jev-integration.md)
7. [Grafana dashboards and short demo](docs/demo.md)

[AGENTS.md](AGENTS.md) preserves engineering constraints for future coding sessions. It is developer guidance, not part of the application.

## Smallest useful implementation

Build a seeded StreamGuard queue simulation with normal traffic, a recoverable sink slowdown, a persistent sink failure, and a traffic spike. Measure actual queue behavior; detect lag; freeze the evidence; run the three adapters; print recommendations and save the trace. Include a timeout case and a deliberately unsafe recommendation to exercise the guardrail. Add Grafana only after this path works.

The local slices are contract and integration checks, not benchmark conclusions. The next milestone adds the live broker and Grafana, then the richer held-out evaluation.

## Environment discovered

The workspace was empty and was not a Git repository. macOS arm64 has Python 3.9.6, Git, and Docker Compose 2.40.3. Docker's daemon was unavailable; `uv` was not on PATH. Plan for Python 3.12, because the inspected TypeSafe SDK requires Python >=3.10. No credentials were read, packages installed, API decisions purchased, or containers started during planning.

## Run the local StreamGuard slice

Use Python 3.12 in an isolated environment. The app runs offline when API keys are absent; it records Jev and LLM as `UNAVAILABLE` rather than creating mock results.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m jevops simulate --scenario sink_slowdown_recoverable --seed 201 --show-truth
.venv/bin/python -m jevops payrecon --scenario projection_mismatch --seed 602 --show-truth
.venv/bin/python -m jevops smoke-suite
.venv/bin/python -m unittest discover -s tests -v
```

`smoke-suite` writes ignored synthetic audit records to `artifacts/streamguard-smoke.jsonl`. It contains 12 seeded episodes and three real adapters per episode. Configure `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY` only when you intentionally want live provider calls; no key is required for simulation and test work.

For safety-path checks, add `--exercise-fixtures` to `simulate`. This adds clearly labeled test-only timeout and unsafe-replay adapters; their results are not provider benchmark data.

PayRecon currently models the deterministic lifecycle/projection boundary locally. Its `REPLAY` action only redelivers a known retained event to the local projection; `RECONCILE` only rebuilds that disposable projection from verified synthetic source events. Neither action can call a processor or alter money movement.
