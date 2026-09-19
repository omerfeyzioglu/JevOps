# Evidence, decisions, and safe actions

## Shared input

Conceptual interface: `decide(evidence, rubric, request_options) -> decision_result`. All adapters use the same validated evidence and label/action rubric. Backend settings differ only where APIs require them.

| Evidence group | Contents |
| --- | --- |
| Identity and time | schema version, domain, opaque incident ID, evidence version, observation cutoff, window duration |
| Measured facts | current values, baseline values, slopes, counts, ages, units, missingness and freshness |
| Event observations | bounded recent errors/status messages, source and observation time; deterministic selection, no generated summary |
| Policy | SLA/deadline state already computed in code, retries spent, action preconditions, wait/replay budgets |
| History | prior observed effects and attempts from a fixed trace; no other backend's answers |

StreamGuard includes arrival/processing rates, lag by partition, sink latency and error counts, heartbeat age, checkpoint age, duplicate/schema-rejection counts, and capacity headroom. PayRecon includes received lifecycle facts, pending prerequisites, missing transition age, dedupe/conflict counts, amount/currency equality flags, snapshot age, processor status and delivery backlog. Counts, ratios, temporal comparisons, and descriptive buckets are computed once and supplied to **all** engines. A feature such as `deadline_exceeded` is valid; `correct_action` is not.

Exclude scenario ID/name, seed, injected fault type/duration, future recovery schedule, expected labels/actions, evaluator notes, and human-written explanations of the fault. Opaque IDs are generated independently of labels. Use a common stable truncation policy and a 6 KB initial evidence target; count truncations. Preserve the full available trace outside the model-facing snapshot for audit.

## Output and audit envelope

Required raw decision: `incident_class` and `recommended_action`, each an enum. Adapters do not return arbitrary commands or execution arguments. Jev probability distributions/confidence are optional provider metadata; Rules has rule IDs, not invented probabilities. LLM has no required numeric confidence or explanation. Do not request free-text reasoning merely to penalize its latency.

The harness adds engine/version, input hash, question/rule/config hashes, requested/returned model, status, attempt count, start/end monotonic timestamps, token usage, measured/estimated/unknown cost, and raw response location. Status distinguishes OK, timeout, rate limit, invalid output, refusal, service error, and unavailable. Missing keys produce UNAVAILABLE, not a fake model result.

Then record `raw_action`, `uncertainty_action`, `effective_action`, `override_reason`, and `applied_action`. A failed provider produces no raw recommendation; fallback is separately audited. Low-confidence routing is a secondary policy comparison, not silently included in raw model accuracy.

## StreamGuard classes

`HEALTHY_OR_RECOVERING`, `SINK_DEGRADED`, `CONSUMER_UNAVAILABLE`, `LOAD_SURGE`, `NETWORK_DEGRADED`, `SCHEMA_REJECT`, `PARTITION_SKEW`, `DUPLICATE_BURST`, `MIXED`, `UNKNOWN`.

Use MIXED only when evidence supports multiple active causes with no single adequate explanation. UNKNOWN covers missing evidence or an unrepresented cause. Faults can coexist; this label describes the actionable interpretation rather than pretending every incident has exactly one latent cause.

| Action | Meaning and deterministic prerequisites |
| --- | --- |
| WAIT | Continue observing for one bounded interval, initially ten logical seconds; no forced recovery. Only within the wait budget, without integrity risk or missed hard deadline. |
| RETRY | One controlled sink-write retry or one consumer-worker restart, with the target derived in code from available capabilities. Requires idempotency and remaining budget. No blind retry of schema/integrity errors. |
| PAUSE | Temporarily pause the affected consumer/partition to prevent repeated bad writes or retry pressure. Preserve backlog; require storage headroom and a resume/review deadline. Does not itself fix a sink. |
| REPLAY | Reprocess a bounded known offset range after the cause is removed. Requires retained source, a known checkpoint, healthy destination, and dedupe. |
| ESCALATE | Record a local review ticket with evidence; perform no inferred repair. |

## PayRecon classes

`BENIGN_DUPLICATE`, `EXPECTED_DELAY`, `OUT_OF_ORDER`, `DELIVERY_GAP`, `PROJECTION_MISMATCH`, `INTEGRITY_CONFLICT`, `MIXED`, `UNKNOWN`.

| Action | Meaning and deterministic prerequisites |
| --- | --- |
| WAIT | Recheck after a bounded interval while inside the processor grace period. Never extend the hard exception deadline through repeated waits. |
| REPLAY | Redeliver known retained lifecycle events into the local projection. Never reissue a payment/capture/refund request. Require healthy consumer, retained source, and idempotent apply. |
| RECONCILE | Run a deterministic comparison/rebuild of the disposable local projection from verified complete source evidence. No invented lifecycle event or financial adjustment. Conflicting or stale source evidence blocks rebuild. |
| ESCALATE | Record a local review ticket; freeze automated repair when integrity is uncertain or source evidence conflicts. |

Exact duplicates normally disappear in deterministic processing. Duplicate-burst exceptions arise only when a volume detector opens one or duplicates coexist with a separate mismatch; the model is not asked to deduplicate every event.

## Common gate and failure behavior

Validate schema, permitted action, evidence freshness, target state/version, deadlines, source availability, idempotency, and attempt budgets immediately before applying any simulated action. Identical gates apply to every engine. A gate cannot infer the hidden fault or improve a model's classification.

Reject unsafe/inapplicable actions and fall back to ESCALATE; a provider failure may use one bounded WAIT only if observable policy explicitly permits it. Repeated WAIT, PAUSE, and RETRY all have expiry/budget rules. Resuming a paused stream requires an explicit healthy observation and successful validation probe; deadline expiry escalates.

Track each simulated action with an idempotency key `(incident, evidence_version, action)`. In a shadow comparison, all engines are advisory. In a recovery demonstration, select exactly one engine before the run; other engines remain shadow-only. Fixed safety containment may act regardless of model response and must be labeled as such.

The demo must show that PAUSE can stop damage without reducing lag, WAIT can recover because a fault ends naturally, and ESCALATE requires a scripted operator repair. Do not equate every recommendation with successful recovery.
