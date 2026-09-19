# Scenarios, fault model, and ground truth

## Generator design

Generate event trajectories, not labeled metric rows. A seed controls baseline rates, durations, service-time noise, delivery jitter, fault onset, and telemetry gaps. Fix scenario distributions and oracle definitions before evaluating providers. No LLM generates scenarios or judges answers in the primary benchmark.

Each episode has warmup, fault onset, detection, observation cutoff, and a follow-up horizon. Vary severity, duration, baseline capacity, and observation completeness independently where physically plausible. A shared latent dependency can correlate failures; do not add unrelated random noise and call it realistic.

Initial ranges are **synthetic design assumptions**: 20–100 events/second, 1.5–3x baseline spare processing capacity, 10–40 seconds of fault duration, 1–5x offered-load changes, and 0–20% missing observation samples. Tune only to obtain interpretable resource use and a balanced range of difficulties, before seeing model results. Retain runs where the detector misses a fault.

## StreamGuard scenario catalog

Each row is a family with easy, boundary, and noisy/overlap variants. Actions below are examples under stated conditions, not a family-name lookup table.

| Family | Injection and observable evidence | Contrasts and acceptable handling |
| --- | --- | --- |
| S1 Sink slowdown/failure | Increase sink service time or return transient/permanent write errors; measured write latency rises and processing falls | Recovery trend inside budget → WAIT; idempotent transient failure → RETRY; repeated harmful attempts → PAUSE or ESCALATE according to policy |
| S2 Consumer crash | Stop the simulated consumer worker, leave producer running; stale heartbeat, increasing lag, no writes | Confirmed crashed worker with restart budget → RETRY; repeated restart failure → ESCALATE; stale heartbeat alone may be UNKNOWN |
| S3 Traffic spike | Increase offered load; sink remains healthy initially | Short spike with drain capacity → WAIT; persistent overload beyond deadline → ESCALATE; overlap with sink throttling → MIXED |
| S4 Network delay | Delay or time out sink/processor calls at the application boundary | Transient transport failure → bounded RETRY/WAIT; simultaneous stale telemetry can require UNKNOWN/ESCALATE; not a real network outage test |
| S5 Schema failure | Inject incompatible payload versions and validation failures | Deterministic reject/quarantine first; PAUSE affected partition if repeated, ESCALATE schema repair; REPLAY only after compatibility is restored |
| S6 Hot partition/skew | Route disproportionate keys to one partition with fixed per-partition capacity | Total rate can look normal; compare per-partition lag. Short skew → WAIT; persistent skew needs ESCALATE, not imaginary autoscaling |
| S7 Duplicate burst | Redeliver existing IDs and increase dedupe work | Dedupe prevents extra writes; WAIT if draining, ESCALATE if resource/deadline budget is exhausted; conflicting payload IDs are integrity exceptions |
| S8 Recovery/checkpoint gap | Interrupt after a sink commit but before offset commit, or leave a bounded unprocessed range after restart | Dedupe handles redelivery; REPLAY only for a known recoverable gap and a healthy sink. Slow catch-up can resemble a new failure |

Add clean controls: no anomaly and a short benign deviation. Deliberately construct matched snapshots with similar aggregate lag but different sink errors, heartbeat freshness, partition imbalance, and recent trends. Some early snapshots must be observationally indistinguishable; correct handling is uncertainty, not guessing a hidden cause.

## PayRecon lifecycle assumptions

One currency per payment, integer minor units, one full capture and settlement, and optionally one full refund after settlement. The intended successful sequence is AUTHORIZED → CAPTURED → SETTLED → REFUNDED. A terminal SETTLED payment need not refund. Do not include partial operations, fees, FX, chargebacks, or void/expiry workflows in v1.

Event identity is `(processor, event_id)`; operation identity includes payment ID, event type, and processor operation ID. Store a payload hash. Exact duplicates are no-ops; reuse of an identity with different content is an integrity conflict. Lifecycle facts are retained even when a prerequisite is absent; never advance the verified projection merely because a later event arrived.

Use event time to describe the lifecycle and arrival time to model delivery. After the missing prerequisite arrives, re-evaluate buffered facts deterministically. Replaying all events must reach the same projection as a clean ordered delivery. Apply dedupe and projection changes in one SQLite transaction. The processor snapshot and local ledger projection are separate observations; missing/stale snapshots are UNKNOWN evidence, not authoritative absence.

Synthetic timing policy starts with a 30-second delivery grace period, a 60-second settlement expectation after capture, and a 90-second hard exception deadline. Record when each timer starts. These accelerated demo windows are not payment-network commitments. Deadline flags are computed in code and visible to all engines.

| Family | Injection and observed mismatch | Contrasts and acceptable handling |
| --- | --- | --- |
| P1 Duplicate delivery | Repeat the same processor event and payload | Dedupe normally resolves it without triage; burst detector/other mismatch may justify WAIT. Conflicting duplicate payload → INTEGRITY_CONFLICT/ESCALATE |
| P2 Late event | Hold a capture/settlement notification but keep available snapshot evidence consistent | Within grace and progressing → EXPECTED_DELAY/WAIT; retained missing notification after grace → DELIVERY_GAP/REPLAY if source health allows |
| P3 Out of order | Deliver settlement before capture or refund before settlement | Buffer, do not skip prerequisites; within grace → OUT_OF_ORDER/WAIT; retained missing prerequisite → REPLAY; unavailable prerequisite beyond deadline → ESCALATE |
| P4 Missing delivery | Drop a notification from transport while retaining it in the source log | Known event and healthy delivery path → DELIVERY_GAP/REPLAY; absent source proof or expired retention → ESCALATE |
| P5 Processor delay | Delay the actual lifecycle transition, not just notification | Fresh pending processor state → EXPECTED_DELAY/WAIT within budget; REPLAY cannot invent settlement; hard deadline → ESCALATE |
| P6 Projection mismatch | Drop a local projection update while event receipt is recorded | Complete verified source → PROJECTION_MISMATCH/RECONCILE; conflicting evidence prevents rebuild and requires ESCALATE |
| P7 Infrastructure interruption | Stop event consumption or make processor-status observations unavailable | Drain/replay once healthy; stale source plus pending settlement → UNKNOWN or MIXED; do not infer financial failure from infrastructure symptoms |
| P8 Integrity mismatch | Change amount/currency or produce contradictory source facts | Deterministic mismatch detection; INTEGRITY_CONFLICT/ESCALATE. A simultaneous processor delay must not justify WAIT or fabricated correction |

Clean controls include ordinary complete lifecycles and isolated exact duplicates. No model calls are necessary for those in the operational path; benchmark controls still assess whether engines over-escalate when given the same snapshot.

## Difficulty and overlap

Easy cases have clear evidence and comfortable timing margins. Boundary cases sit just before/at/after grace and hard deadlines, with explicit inclusive comparisons (`elapsed >= deadline` is exceeded). Hard cases combine faults, hide samples, or provide contradictory observations. Initial overlaps: spike + sink slowdown; crash + stale heartbeat; duplicates + skew; late settlement + consumer interruption; out-of-order capture + processor delay; integrity conflict + otherwise reassuring delay evidence.

Hold out overlap combinations and noise ranges for a separate stress set; do not simply reshuffle adjacent windows from the same run. Include evidence-preserving changes of irrelevant IDs and message wording as robustness checks. Text must describe observed symptoms without embedding the scenario label or desired action. The primary corpus uses structured evidence; optional log-text ablations must be labeled separately.

## Truth has three distinct layers

1. **Hidden causal truth:** injected faults, authoritative synthetic lifecycle, and future schedule. Used for simulator verification and outcome analysis only.
2. **Evidence-justified truth at time t:** acceptable incident labels and actions based solely on the available prefix and published policy. This is the primary triage target. UNKNOWN can be correct even when the simulator knows the fault.
3. **Observed outcome:** actual effects of an applied action over the fixed follow-up horizon. Used only in separate recovery experiments, not to relabel a sensible earlier decision using hindsight.

Per evaluated snapshot, the private manifest stores `acceptable_classes`, `acceptable_actions`, `unsafe_actions`, `escalation_required`, `identifiable`, rationale, and policy version. Acceptable actions and unsafe actions are disjoint; a safe but wasteful action may belong to neither. An unnecessary ESCALATE is scored as over-escalation, not automatically unsafe.

Example: a source notification is provably retained, the consumer is healthy, grace has elapsed, and no conflict exists. REPLAY is appropriate. Before grace, with credible arrival progress, WAIT may also be appropriate. If source availability is unknown and a hard deadline has elapsed, ESCALATE is appropriate. These distinctions must be encoded before engine outputs are seen.

Implement the oracle from scenario manifests and reviewed policy tables independently of the rule adapter. Human-review at least two contrasting examples per family and all ambiguous label sets; verify safety/disjointness invariants and metamorphic properties. If reviewers cannot justify a unique action from available evidence, use a set of acceptable actions or mark the case unscorable for action accuracy and report that count. Never quietly discard hard cases.
