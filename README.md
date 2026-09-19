# JevOps

JevOps compares bounded triage decisions in two synthetic real-time data workflows.

- **StreamGuard** detects queue anomalies and recommends `WAIT`, `RETRY`, `PAUSE`, `REPLAY`, or `ESCALATE`.
- **PayRecon** detects payment-lifecycle reconciliation exceptions and recommends `WAIT`, `REPLAY`, `RECONCILE`, or `ESCALATE`.

Rules, Jev, and an LLM receive the same immutable evidence snapshot. Deterministic code owns anomaly detection, lifecycle validation, arithmetic, idempotency, and action preconditions. Models only recommend a bounded next action.

This repository is a local, synthetic experiment. It does not connect to payment processors, execute payments, manipulate infrastructure, or claim production performance.

## Included

- Seeded StreamGuard queue simulation: normal traffic, recoverable sink slowdown, persistent sink failure, load surge, and ambiguous early evidence.
- Seeded PayRecon lifecycle simulation: duplicates, delays, out-of-order delivery, retained-event gaps, projection mismatches, and integrity conflicts.
- Rules, Jev, and Anthropic structured-output adapters behind one contract.
- Auditable evidence hashes and raw-versus-gated action records.
- Safety gates that prevent unsafe simulated replay or reconciliation.
- Offline test coverage for reproducibility, idempotency, evidence isolation, timeout handling, and action gating.

Redpanda, Prometheus, Grafana, and live API evaluation are not part of the current implementation.

## Run locally

Requires Python 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
```

Run a StreamGuard scenario:

```bash
.venv/bin/python -m jevops simulate \
  --scenario traffic_spike \
  --seed 401 \
  --show-truth
```

Run a PayRecon scenario:

```bash
.venv/bin/python -m jevops payrecon \
  --scenario projection_mismatch \
  --seed 602 \
  --show-truth
```

Run the local StreamGuard suite and tests:

```bash
.venv/bin/python -m jevops smoke-suite
.venv/bin/python -m unittest discover -s tests -v
```

`--show-truth` prints the evaluator’s synthetic truth for demonstration. Decision adapters never receive it.

Use `--exercise-fixtures` with `simulate` to show timeout accounting and an unsafe replay being rejected by the safety gate. These are explicit test fixtures, not model results.

## Provider configuration

The project works without credentials. When keys are absent, Jev and LLM results are recorded as `UNAVAILABLE`; no mock decisions are generated.

To enable live provider calls, set the variables from `.env.example` in your shell. Do not commit `.env` files or any credentials.

```bash
export TYPESAFE_API_KEY="..."
export ANTHROPIC_API_KEY="..."
```

See [architecture.md](docs/architecture.md) for the decision boundary and repository structure.
