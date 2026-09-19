from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from jevops.adapters import JevAdapter, LlmAdapter, RulesAdapter
from jevops.adapters.fixtures import TimeoutFixtureAdapter, UnsafeReplayFixtureAdapter
from jevops.benchmark.runner import run_episode_with_adapters, run_smoke_suite
from jevops.contracts import Action, IncidentClass, ProviderStatus
from jevops.streamguard.actions import validate_action
from jevops.streamguard.simulation import LocalSink, Scenario, run_episode
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
