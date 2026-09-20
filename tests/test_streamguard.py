from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from jevops.adapters import JevAdapter, LlmAdapter, RulesAdapter
from jevops.adapters.fixtures import TimeoutFixtureAdapter, UnsafeReplayFixtureAdapter
from jevops.benchmark.runner import (
    BENCHMARK_CASES,
    BENCHMARK_SEEDS,
    run_benchmark,
    run_episode_with_adapters,
    run_smoke_suite,
    summarize_results,
)
from jevops.contracts import Action, DecisionResult, IncidentClass, ProviderStatus
from jevops.streamguard.actions import validate_action
from jevops.streamguard.simulation import LocalSink, Scenario, run_episode
from jevops.streaming.processor import decide_and_audit, evidence_from_payload
from jevops.streaming.scenarios import generate_events
from jevops.payrecon.actions import validate_action as validate_payrecon_action
from jevops.payrecon.simulation import PayReconScenario, run_episode as run_payrecon_episode


class StreamGuardSimulationTests(unittest.TestCase):
    def test_seed_reproduces_the_same_evidence(self) -> None:
        first = run_episode(Scenario.SINK_SLOWDOWN_RECOVERABLE, 201)
        second = run_episode(Scenario.SINK_SLOWDOWN_RECOVERABLE, 201)
        self.assertEqual(first.evidence.input_hash, second.evidence.input_hash)
        self.assertEqual(first.evidence.model_state(), second.evidence.model_state())

    def test_model_evidence_has_no_scenario_or_truth_fields(self) -> None:
        episode = run_episode(Scenario.SINK_FAILURE_PERSISTENT, 301)
        payload = json.dumps(episode.evidence.model_state()).lower()
        for forbidden in ("scenario", "acceptable_actions", "unsafe_actions", "persistent"):
            self.assertNotIn(forbidden, payload)

    def test_recoverable_and_persistent_paths_have_different_outcomes(self) -> None:
        recoverable = run_episode(Scenario.SINK_SLOWDOWN_RECOVERABLE, 201)
        persistent = run_episode(Scenario.SINK_FAILURE_PERSISTENT, 301)
        self.assertIsNotNone(recoverable.detector_opened_at)
        self.assertIsNotNone(persistent.detector_opened_at)
        self.assertTrue(recoverable.recovered_by_end)
        self.assertFalse(persistent.recovered_by_end)

    def test_healthy_sink_drains_a_short_traffic_spike(self) -> None:
        spike = run_episode(Scenario.TRAFFIC_SPIKE, 401)
        self.assertTrue(spike.recovered_by_end)

    def test_sink_is_idempotent_on_duplicate_event_ids(self) -> None:
        from collections import deque

        sink = LocalSink()
        records = deque(["same-event", "same-event"])
        processed, errors, _ = sink.write(records, 2, fail_writes=False, latency_ms=12)
        self.assertEqual((processed, errors, len(records)), (2, 0, 0))
        self.assertEqual(sink.committed_count, 1)


class StreamGuardDecisionTests(unittest.TestCase):
    def test_rules_classify_clear_sink_and_load_cases(self) -> None:
        rules = RulesAdapter()
        sink = rules.decide(run_episode(Scenario.SINK_FAILURE_PERSISTENT, 301).evidence)
        spike = rules.decide(run_episode(Scenario.TRAFFIC_SPIKE, 401).evidence)
        self.assertEqual(sink.incident_class, IncidentClass.SINK_DEGRADED)
        self.assertEqual(sink.recommended_action, Action.RETRY)
        self.assertEqual(spike.incident_class, IncidentClass.LOAD_SURGE)
        self.assertEqual(spike.recommended_action, Action.WAIT)

    def test_unsafe_replay_is_blocked_by_observable_preconditions(self) -> None:
        episode = run_episode(Scenario.SINK_FAILURE_PERSISTENT, 301)
        unsafe = UnsafeReplayFixtureAdapter().decide(episode.evidence)
        gate = validate_action(episode.evidence, unsafe)
        self.assertEqual(gate.raw_action, Action.REPLAY)
        self.assertEqual(gate.effective_action, Action.ESCALATE)
        self.assertIn("healthy sink", gate.override_reason or "")

    def test_timeout_is_a_distinct_non_decision(self) -> None:
        evidence = run_episode(Scenario.TRAFFIC_SPIKE, 401).evidence
        result = TimeoutFixtureAdapter().decide(evidence)
        gate = validate_action(evidence, result)
        self.assertEqual(result.status, ProviderStatus.TIMEOUT)
        self.assertIsNone(gate.effective_action)

    def test_all_engines_audit_the_identical_input_hash(self) -> None:
        episode = run_episode(Scenario.SINK_SLOWDOWN_RECOVERABLE, 201)
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            rows = run_episode_with_adapters(episode, [RulesAdapter(), JevAdapter(), LlmAdapter()])
        self.assertEqual({row["evidence_hash"] for row in rows}, {episode.evidence.input_hash})
        statuses = {row["audit"]["decision"]["engine"]: row["audit"]["decision"]["status"] for row in rows}
        self.assertEqual(statuses, {"rules": "OK", "jev": "UNAVAILABLE", "llm": "UNAVAILABLE"})

    def test_smoke_suite_preserves_every_scheduled_provider_attempt(self) -> None:
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            rows = run_smoke_suite([RulesAdapter(), JevAdapter(), LlmAdapter()])
        self.assertEqual(len(rows), 36)
        self.assertEqual(sum(row["audit"]["decision"]["status"] == "UNAVAILABLE" for row in rows), 24)

    def test_benchmark_covers_every_scenario_with_multiple_seeds(self) -> None:
        self.assertEqual({scenario for scenario, _ in BENCHMARK_CASES}, set(Scenario))
        for scenario in Scenario:
            self.assertEqual(
                {seed for scheduled, seed in BENCHMARK_CASES if scheduled is scenario},
                set(BENCHMARK_SEEDS),
            )
        self.assertGreater(len(BENCHMARK_SEEDS), 1)

    def test_benchmark_repeats_calls_and_shares_each_evidence_snapshot(self) -> None:
        first = RulesAdapter()
        second = RulesAdapter()
        cases = (
            (Scenario.NORMAL, 101),
            (Scenario.FALSE_RECOVERY, 202),
        )
        with (
            patch.object(first, "decide", wraps=first.decide) as first_decide,
            patch.object(second, "decide", wraps=second.decide) as second_decide,
        ):
            rows = run_benchmark([first, second], runs=2, cases=cases)
        self.assertEqual(first_decide.call_count, 4)
        self.assertEqual(second_decide.call_count, 4)
        grouped_hashes: dict[tuple[int, int], set[object]] = {}
        for row in rows:
            key = (row["benchmark"]["run"], row["benchmark"]["seed"])
            grouped_hashes.setdefault(key, set()).add(row["evidence_hash"])
        self.assertTrue(all(len(hashes) == 1 for hashes in grouped_hashes.values()))

    def test_benchmark_summary_reports_quality_latency_and_failures(self) -> None:
        def row(
            status: str,
            latency: float,
            *,
            action: bool | None,
            incident: bool | None,
            unsafe: bool | None,
            unnecessary: bool | None,
        ) -> dict[str, object]:
            return {
                "audit": {
                    "decision": {
                        "engine": "jev",
                        "status": status,
                        "elapsed_ms": latency,
                    }
                },
                "evaluation": {
                    "action_acceptable": action,
                    "class_acceptable": incident,
                    "unsafe_recommendation": unsafe,
                    "unnecessary_escalation": unnecessary,
                },
            }

        summary = summarize_results(
            [
                row("OK", 10, action=True, incident=True, unsafe=False, unnecessary=False),
                row("OK", 20, action=False, incident=True, unsafe=True, unnecessary=True),
                row("TIMEOUT", 30, action=None, incident=None, unsafe=None, unnecessary=None),
                row("UNAVAILABLE", 0, action=None, incident=None, unsafe=None, unnecessary=None),
                row("SERVICE_ERROR", 40, action=None, incident=None, unsafe=None, unnecessary=None),
            ]
        )[0]
        self.assertEqual(summary["total_attempts"], 5)
        self.assertEqual(summary["total_evaluated_decisions"], 2)
        self.assertEqual(summary["action_accuracy"], 0.5)
        self.assertEqual(summary["incident_class_accuracy"], 1.0)
        self.assertEqual(summary["unsafe_recommendation_count"], 1)
        self.assertEqual(summary["unnecessary_escalation_count"], 1)
        self.assertEqual(summary["median_latency_ms"], 25.0)
        self.assertEqual(summary["p95_latency_ms"], 38.5)
        self.assertEqual(summary["provider_failure_count"], 1)
        self.assertEqual(summary["provider_timeout_count"], 1)
        self.assertEqual(summary["provider_unavailable_count"], 1)

    def test_benchmark_preserves_jev_confidence_metadata(self) -> None:
        jev = JevAdapter()
        result = DecisionResult(
            engine="jev",
            engine_version="test",
            status=ProviderStatus.OK,
            incident_class=IncidentClass.HEALTHY_OR_RECOVERING,
            recommended_action=Action.WAIT,
            elapsed_ms=12,
            metadata={"incident_confidence": 0.8, "action_confidence": 0.9},
        )
        with patch.object(jev, "decide", return_value=result):
            row = run_benchmark(
                [jev], runs=1, cases=((Scenario.NORMAL, 101),)
            )[0]
        self.assertEqual(row["audit"]["decision"]["metadata"]["action_confidence"], 0.9)


class StreamGuardLiveTests(unittest.TestCase):
    def test_live_scenarios_are_seeded_and_do_not_leak_scenario_identity(self) -> None:
        first = list(generate_events(Scenario.INTERMITTENT_FAILURE, 701, 30, "test-run"))
        second = list(generate_events(Scenario.INTERMITTENT_FAILURE, 701, 30, "test-run"))
        normalized_first = [event.as_dict() | {"timestamp": "ignored"} for event in first]
        normalized_second = [event.as_dict() | {"timestamp": "ignored"} for event in second]
        self.assertEqual(normalized_first, normalized_second)
        self.assertNotIn("scenario", json.dumps(normalized_first).lower())
        self.assertTrue(any(event.sink_errors > 0 for event in first))
        self.assertTrue(any(event.sink_errors == 0 for event in first[15:]))

    def test_live_processor_preserves_hash_and_safety_gate(self) -> None:
        evidence = run_episode(Scenario.SINK_FAILURE_PERSISTENT, 301).evidence
        reconstructed = evidence_from_payload(evidence.model_state())
        rows = decide_and_audit(
            reconstructed, [RulesAdapter(), UnsafeReplayFixtureAdapter()]
        )
        self.assertEqual({row["evidence_hash"] for row in rows}, {evidence.input_hash})
        self.assertEqual(
            rows[1]["audit"]["gate"]["effective_action"], Action.ESCALATE
        )


class PayReconTests(unittest.TestCase):
    def test_rules_keep_reconciliation_deterministic(self) -> None:
        rules = RulesAdapter()
        missing = rules.decide(run_payrecon_episode(PayReconScenario.MISSING_RETAINED, 601).evidence)
        mismatch = rules.decide(run_payrecon_episode(PayReconScenario.PROJECTION_MISMATCH, 602).evidence)
        conflict = rules.decide(run_payrecon_episode(PayReconScenario.INTEGRITY_CONFLICT, 603).evidence)
        self.assertEqual((missing.incident_class, missing.recommended_action), (IncidentClass.DELIVERY_GAP, Action.REPLAY))
        self.assertEqual((mismatch.incident_class, mismatch.recommended_action), (IncidentClass.PROJECTION_MISMATCH, Action.RECONCILE))
        self.assertEqual((conflict.incident_class, conflict.recommended_action), (IncidentClass.INTEGRITY_CONFLICT, Action.ESCALATE))

    def test_payrecon_blocks_replay_without_a_known_gap(self) -> None:
        episode = run_payrecon_episode(PayReconScenario.INTEGRITY_CONFLICT, 603)
        unsafe = UnsafeReplayFixtureAdapter().decide(episode.evidence)
        gate = validate_payrecon_action(episode.evidence, unsafe)
        self.assertEqual(gate.effective_action, Action.ESCALATE)
        self.assertIn("non-conflicting", gate.override_reason or "")

    def test_payrecon_engines_share_an_identical_evidence_snapshot(self) -> None:
        episode = run_payrecon_episode(PayReconScenario.OUT_OF_ORDER, 604)
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            rows = run_episode_with_adapters(episode, [RulesAdapter(), JevAdapter(), LlmAdapter()])
        self.assertEqual({row["evidence_hash"] for row in rows}, {episode.evidence.input_hash})
