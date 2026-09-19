# Grafana and demo strategy

## What the viewer should understand

“We detected a symptom deterministically. Three decision engines saw the same evidence. Here is what each recommended, what the safety policy allowed, and what happened in the simulator.” The short demo demonstrates this boundary; it does not substitute for held-out evaluation.

Use two provisioned Grafana dashboards with the same layout. No custom web UI. Prometheus scrapes app metrics every second for a live walkthrough; show actual measured behavior. Exported benchmark artifacts remain the source of truth for exact percentiles and cost accounting.

| Row | StreamGuard | PayRecon |
| --- | --- | --- |
| System condition | Arrival/processing rate, lag, oldest-record age | Events received/applied, unresolved exceptions, oldest exception age |
| Fault evidence | Sink latency/errors, heartbeat age, lag by partition | Duplicate/conflict counts, missing prerequisites, source freshness, delivery delay |
| Decisions | Rules/Jev/LLM class and action state timelines | Same, with reconciliation action vocabulary |
| Safety and execution | Raw versus effective action, override/timeout counts | Same, with amount/conflict guards visible |
| Outcome | Lag drains, errors fall, incident clears | Event projection becomes consistent, exception clears or escalates |

Prometheus labels are bounded: domain, engine, status, class, action, partition. No payment IDs, request IDs, error prose, seeds, or input hashes in labels. Keep those in JSONL and local audit records. Low-volume decision counters and histograms summarize behavior; one-hot last-decision gauges support state timelines, reset on each run with observation timestamps so stale values are apparent.

Use Grafana's [built-in annotations](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/annotate-visualizations/) and [annotation API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/annotations/) for fault start/end, detector firing, evidence version, selected engine, action block/application, and operator repair. Annotation failure must not block the experiment. Render enum descriptions and audit facts; do not manufacture natural-language model explanations.

## First recorded walkthrough: 60–90 seconds

1. **0–15 seconds:** steady StreamGuard traffic, flat lag, healthy sink. Show “synthetic workload / simulated actions.”
2. **15–30 seconds:** inject sink slowdown using a preselected seed. Sink latency rises and processing falls; backlog becomes visible. Annotate the injection separately from detection.
3. **30–45 seconds:** anomaly opens. Freeze a snapshot. Display all three recommendations and measured response times; allow disagreement. Distinguish waiting for a response from model WAIT.
4. **45–65 seconds:** the preselected controller recommends an action; display the safety gate and application. If the right response is PAUSE, show backlog persisting until a clearly labeled fault-clear/operator step. Do not fake immediate recovery.
5. **65–90 seconds:** resume/drain, close after clean windows. End with one concrete observation and a link to the benchmark report, including a failure or disagreement when available.

PayRecon companion walkthrough: normal authorization/capture → delay settlement notification while the processor reports settlement → deterministic mismatch opens → compare WAIT/REPLAY/RECONCILE/ESCALATE → safe event replay restores the local projection. A second short integrity-conflict example demonstrates why escalation is necessary. Show both cases; do not imply all missing settlements are harmless delays.

## Demo safeguards and acceptance

Select the controller before each run. Never apply three competing recommendations to shared mutable state. Show simulated time acceleration if enabled, and use wall-clock time for provider latency. Fault expiry, operator repair, and automatic action are separate annotation types.

If an API is unavailable, show UNAVAILABLE. A saved recording may be replayed with “recorded API decisions” clearly visible; cached responses cannot be presented as live latency measurements. Do not use fixture responses in a public performance claim.

Acceptance: a new user can start the stack from documented commands, inject a named fault, observe detection and three decision statuses, distinguish raw/effective/applied actions, and see recovery or an honest unresolved escalation. Restart/reset returns to a known baseline. The dashboards contain no secrets or synthetic payment-level identifiers as metric labels.
