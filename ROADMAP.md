# Implementation roadmap

**Current milestone: local StreamGuard and PayRecon slices implemented; live broker/Grafana integration is next.**

Aim for 6–8 focused AI-assisted engineering days plus API-access/setup contingency. This is a rough effort budget, not a delivery promise. Prefer complete, demonstrable paths over broad scenario coverage. If time slips, reduce scenario variants and optional analysis before weakening correctness or benchmark controls.

## 0 — Review this plan

Delivered: scope and repository layout; causal/observable ground-truth separation; decision contracts; benchmark protocol; Jev research; demo strategy; AGENTS.md. Implementation is authorized; phase 1 is in progress.

Defaults proposed for review: Python 3.12, direct TypeSafe SDK, Claude Haiku 4.5 as the single LLM comparator, one Redpanda broker only after the local slice, SQLite/JSONL, simulated remediation, and no training pipeline. Access to both APIs, acceptable test spend, and Docker resources remain unverified. No private credentials are needed in chat.

Exit: complete the acceptance checks below before starting the broker/Grafana milestone.

## 1 — Smallest vertical slice: StreamGuard locally (1–1.5 days)

Implemented: Git repository, Python package, Python 3.12 declaration, resolved dependency lock, offline tests, seeded local queue/sink simulation, deterministic detector, public evidence contract, rules/Jev/LLM adapters, audit envelope, and shared action gate. Docker is not required yet. Dependency installation and SDK surface verification are complete; live provider validation remains pending credentials.

Build the following single path:

1. Seeded producer → bounded local queue → instrumented sink → measured lag/throughput/latency.
2. Normal traffic, recoverable sink slowdown, persistent sink failure, and healthy traffic spike. Include a boundary case where early evidence does not distinguish causes.
3. Deterministic anomaly detection and one frozen common evidence snapshot per incident.
4. Rules, Jev, and LLM adapters returning class/action; unavailable credentials produce an explicit status. Two Jev Choices and the equivalent LLM structured result only.
5. Shadow audit, shared action validator, and one isolated simulated recovery path.
6. Console comparison and JSONL evidence/results for 12 reviewed episodes. No Grafana, Kafka, extensive report generator, or custom UI yet.

Acceptance: same seed reproduces local evidence/truth; all adapters receive the same evidence hash; no ground-truth field leaks; obvious cases have reviewed expected handling; an unsafe replay is blocked; an API timeout is counted and does not stop event processing. Obtain one genuine response from each API when access is available. Offline completion without credentials is explicitly partial integration, not the finished three-way slice.

**Why first:** this tests whether the context is useful and whether Jev fits the actual decision, before paying the infrastructure cost. It also reveals if good rules already solve the meaningful cases.

## 2 — StreamGuard live MVP (1 day)

Add one Redpanda broker with three partitions, replace local transport behind the same domain path, and retain the offline generator for evaluation. Add persisted sink dedupe/offset handling and fault injection for consumer crash and schema rejection. Provision Prometheus and one Grafana dashboard.

Acceptance: four live fault families (sink, traffic, crash, schema) visibly degrade metrics; detector fires; all engines are shadow-compared; one preselected policy acts only on the simulator. Replay after a crash cannot duplicate sink writes. Cold start/reset and broker health failures are understandable. No production Kafka throughput claims.

Minimum StreamGuard is complete here once the three providers are live; richer scenarios belong to phase 4.

## 3 — PayRecon MVP (1–1.5 days)

Local implementation started alongside the shared contract work: the synthetic lifecycle scenarios, deterministic Rules decisions, common Jev/LLM adapter path, and reconciliation action gate are present and covered by offline tests. SQLite persistence, live transport reuse, and Grafana display remain part of the live-integration milestone.

Reuse the harness, transport, storage, and instrumentation. Build the synthetic lifecycle, separate processor observations, idempotent event projection, deterministic reconciliation, and action preconditions. Initial families: duplicate delivery, delayed/out-of-order delivery, missing retained event, and amount/projection mismatch. Use integer money and accelerated documented deadlines.

Acceptance: ordered and reordered complete streams converge; duplicates cannot double-count; missing prerequisites do not advance state; mismatches open deterministically; safe replay closes a delivery gap; deterministic rebuild closes a projection defect; conflicting amounts require escalation; repeated WAIT eventually reaches the hard deadline. Show the same three adapters and a second Grafana dashboard.

Minimum PayRecon is complete here. It is explicitly a simulated lifecycle/projection experiment, not a general financial ledger.

## 4 — Honest evaluation (1.5–2 days)

Expand to the eight families per domain in docs/scenarios.md. Review oracle labels, add overlaps/noise/unknowns, and freeze episode-level data splits. Finish the strong rules baseline and at most three tuning rounds per engine. Verify that no backend receives special evidence.

Run the frozen paired test plus controls/stress cases under a previewed spend cap. Produce action/class quality, raw/effective safety, escalation, API failure, p50/p95 latency, cost, and repeatability reports. Include confidence-versus-coverage only as a secondary analysis. Preserve the manifests, input/output hashes, provider IDs, and selected failure traces.

Acceptance: every scheduled case is accounted for, unavailable/timeouts cannot disappear, no benchmark table uses mocks, and results reproduce from saved outputs without API calls. A fair negative result satisfies this phase. Threshold or prompt changes after test inspection require a new experiment version.

## 5 — Portfolio packaging (0.5–1 day)

Verify fresh-start instructions and reset behavior. Record the two short walkthroughs, with selected controller and simulator boundaries visible. Add a concise findings report discussing where rules suffice, what Jev changes, and the tested LLM's tradeoffs. Include setup costs and limitations rather than a universal winner headline.

Acceptance: README links to runnable commands, dashboards/demo, architecture, and measured report; a reader can explain the business problem and decision boundary without reading implementation code. Both experiments work from the same repository and Compose stack. No credentials, generated bulk artifacts, or unsupported production claims are committed.

## Optional only after completion

Noul/Score diagnostic ablations; text-rich evidence robustness; a broader LLM comparison; matched multi-policy recovery branches; or a hybrid rules→Jev policy. Keep hybrid results separate from the primary Rules/Jev/LLM table. Do not add these if the core demos or report remain unfinished.

## Risks and decision gates

| Risk | Response |
| --- | --- |
| Jev adds no value over rules | Preserve the finding. Analyze rules' coverage and maintenance surface; do not change the simulator to force an advantage. |
| API unavailable, rate-limited, or incompatible | Keep offline deterministic work moving; mark integration blocked/partial and retain the original benchmark requirement. Verify SDK/model contract before scaling runs. |
| Docker/runtime setup consumes time | Finish local slice first, then resolve daemon/runtime; measure laptop resource use before widening load. |
| Simulator or label quality is weak | Spend time on causal mechanics and reviewed observable evidence, reduce scenario count if needed. Avoid hiding unidentifiable cases. |
| Broad action taxonomy creates ambiguity | Keep accepted-action sets and preconditions explicit. Simplify labels before freeze rather than retrofit them to model answers. |
| Safety gate makes every backend look safe | Publish raw unsafe proposals, overrides, and effective outcomes side by side. |
| Too much infrastructure or polish | Keep four Compose services and two dashboards. Cut optional analytics, UI, and extra providers first. |

The next authorized engineering step after review is phase 1, not building the entire stack at once.
