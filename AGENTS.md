# JevOps engineering guidance

## Purpose and current phase

This file keeps future AI-assisted changes consistent with the experiment. Read README.md and ROADMAP.md, then the relevant docs before changes. The current deliverable is planning only. Wait for the user's implementation instruction before writing application code. Once implementation is requested, progress through the accepted roadmap without repeatedly asking for routine choices.

## Boundaries

- Keep one Python package, two domain modules, and one shared benchmark harness. Do not add training, new infrastructure, or a model cascade without a demonstrated need and a documented scope change.
- Deterministic code owns arithmetic, time comparisons, deduplication, lifecycle validation, reconciliation, and action preconditions. Models only recommend triage decisions.
- Model output must never invoke shell commands, initiate payments/refunds, or modify real systems. Apply simulated actions through a small allowlist with fresh-state checks.
- Ground-truth manifests, fault schedules, future observations, and scenario names must not reach decision adapters. Preserve the exact common evidence and its hash.
- Keep raw recommendations, uncertainty handling, safety overrides, and final applied actions separate. Do not report post-guardrail safety as model safety.
- Do not weaken rules, favor one provider's inputs, cherry-pick seeds, fabricate results, or change labels after seeing held-out outputs. Publish failures and unavailable providers explicitly.
- Store credentials only in runtime environment variables; never in committed fixtures, traces, screenshots, or docs.

## Integration and checks

Read docs/jev-integration.md and recheck official API/SDK docs before implementation or upgrades. The [official TypeSafe skill](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md) is useful design guidance; live docs remain the API source of truth. No skill installer or agent framework is required.

Keep question wording, label definitions, and thresholds centrally versioned. Pin model IDs and dependencies; record requested and returned model versions. Do not assume Jev has temperature, free-text explanations, or Noul confidence.

Use meaningful tests for event-time behavior, idempotency, missing evidence, safety gates, label leakage, and result accounting. Live API tests are separate from offline tests. Never label mock provider outputs as measured results. Update roadmap status and relevant decisions when a milestone changes.
