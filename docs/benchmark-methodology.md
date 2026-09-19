# Benchmark methodology

Status: preregistered design proposal. There are no measured results.

## Questions the experiment can answer

For these synthetic workloads and pinned configurations, how often does each engine recommend an acceptable action, how often does it recommend an unsafe one, and what latency/cost does it incur? Does Jev's uncertainty information help trade coverage for safety? Where do rules remain sufficient?

One LLM result does not establish how all LLMs perform. Synthetic incidents do not establish production reliability. Report conditional triage quality separately from anomaly detector quality and simulated recovery.

Run detector evaluation over all generated event trajectories, including clean controls. Report incident-level recall (detected eligible incidents / all eligible incidents), precision (true incident openings / all openings), false alerts per simulated hour, and onset-to-detection delay. Define eligible anomaly intervals and matching tolerance before evaluation; count repeated openings separately as alert churn. Missed incidents remain misses. For the triage-only comparison, select snapshots at predeclared observation cutoffs even if the detector missed that episode, and label these as forced evaluation snapshots. Report a separate operational view restricted to actual detector-triggered snapshots; do not merge its denominator with the full triage corpus.

## Primary comparison

All engines evaluate the identical frozen evidence, label definitions, policy constraints, and observation cutoff. Jev gets two Choice questions (incident class and action); the LLM gets a compact structured schema with those same enums; Rules computes them locally. No tools, retrieval, future observations, long explanations, or provider-specific hidden hints. Class and action are independently requested from evidence; Jev questions cannot see each other's answers.

Implement a credible rule baseline: ordered rules for integrity/deadline conditions, specific symptoms, recovery trend, and conservative unknown handling. Use temporal persistence, ratios, hysteresis, per-partition evidence, and available error codes. Document conflict precedence and matched rule IDs. Rules may parse provided text through transparent patterns. Do not restrict rules to one lag threshold or secretly exclude useful fields.

Initial rule precedence: integrity violation → required containment/escalation; expired recovery budget → ESCALATE; known replayable gap with healthy destination → REPLAY; explicit schema rejection → PAUSE/review; confirmed crashed worker with budget → RETRY; transient healthy recovery → WAIT; unresolved conflict → MIXED/UNKNOWN and conservative handling. Domain policies refine this order on development data. Baseline rules and the independent oracle are not the same implementation.

Keep all fields available to every engine. If the primary numeric evidence is fully captured by good rules, report that finding; do not add contrived prose to rescue the Jev hypothesis. An optional text-rich stratum can test a separate semantic question.

## Dataset and tuning discipline

- First-slice smoke set: 12 reviewed StreamGuard episodes, not an accuracy leaderboard.
- Target core corpus: 16 scenario families × 30 independent episodes = 480 episodes, with one primary snapshot per episode. Allocate ten episodes per family to development, ten to validation, and ten to final test (160 in each split).
- Add 40 held-out stress episodes with unseen fault combinations/noise ranges, plus 40 clean control episodes, half from each domain. Publish them as separate strata.
- Split by complete episode, seed lineage, and any log template; adjacent windows never span splits. Freeze held-out manifests/hashes before tuning. No selection based on a provider's performance.
- Allow a small comparable tuning budget, initially three revision rounds per backend on development cases. Select gates/configuration on validation, then freeze. Record edits, time, and paid calls; do not call a changed configuration the same experiment.
- Final test is untouched until the freeze. Any revisions afterward create a new benchmark version with a fresh holdout. Report all runs rather than overwriting unfavorable results.

The held-out sets are sealed by process, not secure against a developer opening a file; document this limitation. Published seeds eventually allow reproduction. Aggregate equally by family as well as by episode; this is a balanced diagnostic distribution, not an estimate of industry incident prevalence.

## Metrics and denominators

| Metric | Definition |
| --- | --- |
| Acceptable action rate | On-time valid raw action in the accepted set / all scheduled cases. Errors/timeouts count as unsuccessful; also show valid-response-only rate. |
| Incident class accuracy | Valid predicted class in accepted class set / all scorable cases. Report identifiable and ambiguous cases separately, plus a confusion matrix. |
| Unsafe recommendation rate | Valid raw action in unsafe set / all scheduled cases; also / valid recommendations. Show counts and provider failures alongside it so silence cannot appear safe. |
| Unsafe effective action rate | Unsafe post-gate action / all scheduled cases, separately from raw recommendation safety; report gate overrides and fallback counts. |
| Unnecessary escalation | ESCALATE when a safe non-escalation action is justified and escalation is not required / cases meeting that condition. Include raw and effective versions. |
| Required escalation recall | ESCALATE / cases explicitly requiring it; zero denominator is N/A. |
| Automated coverage | Non-escalated, on-time effective decisions / all scheduled cases. Plot quality and unsafe rate against coverage. |
| Latency | p50/p95 of monotonic adapter end-to-end time; success-only and all-attempt terminal latency separately. Record queue delay, provider-call time, validation, and retries. |
| Cost / 1,000 decisions | Total accounted cost / scheduled decisions × 1,000, and separately / successful decisions. Include retries and failures with known usage. Distinguish billed, estimated, and unknown. |
| Repeatability | Repeated label/action agreement and transition to/from abstention; agreement does not imply correctness. |

Safety is measured against explicit simulated policy, not a claim about real-world financial safety. Show raw counts, sample sizes, and 95% intervals; use Wilson intervals for simple proportions and paired episode bootstrap for engine differences. Do not imply statistical significance from tiny per-family samples. Zero unsafe outcomes is not proof of zero risk.

For repeated snapshots, bootstrap at the episode level. Decision observations within an episode are correlated; the primary evaluation uses one snapshot per episode to avoid counting a long incident as many independent wins.

## Timing, reliability, and cost controls

Run on one host with recorded hardware, network location, SDK versions, endpoint, model ID, request hash, input sizes, and timestamp. First evaluate concurrency one per remote backend with randomized/interleaved order; then a separately labeled bounded concurrency test (initially four) if useful. The rule engine's local execution and API roundtrip are deployment tradeoffs, not equal compute resources.

Primary timing: persistent client connections, five warmup calls reported separately, 15-second request deadline, SDK retries disabled, no repair retry for invalid output. Count schema compilation/cold-start overhead separately; do not conceal it. Report completed calls exceeding a one-second illustrative real-time target rather than imposing a Jev-favoring short timeout. Never claim this target is achieved before measurement.

Secondary operational test: at most one retry for transient errors, respecting retry-after and a 20-second total budget. Do not combine it with primary timing results. Provider failures and local queue saturation must be visible. Cancellation does not prove a provider did not bill the request.

Use reported usage and contemporaneous official pricing if the provider does not return cost. Save the dated pricing source and formula; label this as an estimate, not an invoice. Unknown usage after a timeout remains unknown. Rules has zero external API charge, not zero compute or engineering cost. Exclude infrastructure spend from API cost and report it separately if measured.

Before paid runs, preview request counts, token estimates, and a configurable spend ceiling (proposed default USD 10 for a development session). Stop at the ceiling; do not silently expand it. Credentials/access and account quotas are unverified planning dependencies. Offline runs remain useful but do not fulfill the three-provider benchmark milestone.

## Uncertainty and consistency

The primary table uses raw recommendations without probabilistic gating. A secondary analysis applies validation-selected action-specific Jev gates and reports coverage versus unsafe rate. LLM explicit ESCALATE and rule fallback are their default abstention mechanisms; do not invent comparable confidence values for them. An optional LLM self-reported probability analysis must be clearly labeled as such, not equated to Jev probabilities.

Retain Jev probabilities separately from its confidence statistic. Assess calibration only for a well-defined single-label subset; do not use ordinary one-hot Brier scores for multi-acceptable-action cases. A small reliability plot is exploratory, not a calibration guarantee.

Select 40 held-out snapshots across domains/difficulty before looking at outputs. Evaluate each five times total with exactly identical model-facing payloads. Disable local result caching; do not add random IDs to break provider caching in the primary repeatability test. If provider cache behavior is unknown, disclose that. Report full-repeat agreement and modal agreement for classes/actions, including timeouts, and repeatability after gates separately. A wording/order perturbation test is a distinct robustness analysis.

## Recovery is a separate experiment

Run one selected policy per isolated branch of an identical seeded episode, preserving the same external fault schedule. Compare backlog area, time to recovery, unreconciled record-seconds, blocked actions, and deadline misses. An action's effect follows the simulator mechanics, not whether it matches an answer key.

Include a no-intervention baseline for transient faults. WAIT may appear successful because the fault expired; REPLAY may fail while the source is unavailable; PAUSE can increase lag; ESCALATE is followed by a labeled operator intervention. Do not attribute those external interventions to model intelligence. The MVP needs an illustrative recovery trace; multi-policy causal recovery comparisons are optional later work.

## Reporting requirements and major risks

Publish configuration/data hashes, scenario distribution, raw/effective confusion and safety tables, latency distributions, failure counts, estimated costs, and representative misses. Choose demo seeds before final provider evaluation, or explicitly identify curated examples. Report data-generation defects and corrections as version changes.

Main threats: simulator-to-reality gap; oracle subjectivity; hidden label leakage; simplistic rules; numeric tasks with no real model advantage; inconsistent model versions; endpoint/network/cache effects; confidence misinterpretation; tiny samples; guardrails masking errors; always-escalate gaming; and benchmark tuning after test inspection. The controls above reduce these risks but cannot remove them. Success means a reproducible and candid comparison, even if Jev loses.
