"""Run the full comparison and a paired Laya CPU control with runtime metadata."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
from zoneinfo import ZoneInfo

from jevops.adapters.gemini import GeminiAdapter
from jevops.adapters.jev import JevAdapter
from jevops.adapters.laya import LayaAdapter, _check_token_budget
from jevops.adapters.rules import RulesAdapter
from jevops.adapters.rubric import rubric_for
from jevops.benchmark.runner import (
    BENCHMARK_CASES, BENCHMARK_SEEDS, BENCHMARK_SNAPSHOT_SECONDS,
    run_episode_with_adapters, summarize_results, write_json, write_jsonl,
)
from jevops.payrecon.simulation import PayReconScenario, run_episode as payrecon_episode
from jevops.streamguard.simulation import Scenario, run_episode


def episodes():
    return {
        "streamguard": [run_episode(s, seed, snapshot_second=BENCHMARK_SNAPSHOT_SECONDS.get(s))
                        for s, seed in BENCHMARK_CASES],
        "payrecon": [payrecon_episode(s, seed) for s in PayReconScenario for seed in BENCHMARK_SEEDS],
    }


def warmup(adapter, evidence):
    records = []
    for _ in range(2):
        result = adapter.decide(evidence)
        if result.status.value != "OK":
            raise RuntimeError(f"Laya warmup failed: {result.status.value}: {result.error}")
        records.append(asdict(result))
    return records


def input_audit(adapter, matrix):
    from laya.common import build_sequence
    agent = adapter._get_model()
    records = []
    for domain, cases in matrix.items():
        for index, episode in enumerate(cases):
            state = episode.evidence.model_state()
            ci, ca, qi, qa = rubric_for(domain)
            questions = {
                "incident_class": {"type": "choice", "instructions": qi, "criteria": ci},
                "recommended_action": {"type": "choice", "instructions": qa, "criteria": ca},
            }
            compact = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
            checked = _check_token_budget(agent, compact, questions)
            for name, q in questions.items():
                internal = {"t": "choice", "ins": q["instructions"], "crit": q["criteria"]}
                original, _ = build_sequence(agent.tok, state, internal, 512, 192)
                full, _ = build_sequence(agent.tok, state, internal, 8192, 1024)
                corrected, _ = build_sequence(agent.tok, compact, internal, 1024, 384)
                if len(corrected) != checked["request_tokens_by_question"][name]:
                    raise RuntimeError("Laya sequence layout differs from token-budget validation")
                records.append({
                    "domain": domain, "scenario": episode.truth.scenario.value,
                    "seed": BENCHMARK_SEEDS[index % len(BENCHMARK_SEEDS)],
                    "question": name, "evidence_hash": episode.evidence.input_hash,
                    "original_sequence_tokens": len(original),
                    "original_full_tokens": len(full),
                    "original_input_truncated": original != full,
                    "corrected_sequence_tokens": len(corrected),
                    "corrected_input_truncated": False,
                })
    return records


def run_matrix(matrix, adapters, runs, output_dir, suffix=""):
    for domain, cases in matrix.items():
        rows = []
        output = output_dir / f"benchmark-{domain}{suffix}.jsonl"
        for repeat in range(1, runs + 1):
            for index, episode in enumerate(cases):
                # Rotate provider order deterministically to reduce order bias.
                offset = (index + repeat - 1) % len(adapters)
                ordered = adapters[offset:] + adapters[:offset]
                batch = run_episode_with_adapters(episode, ordered)
                for row in batch:
                    row["benchmark"] = {"run": repeat, "seed": BENCHMARK_SEEDS[index % len(BENCHMARK_SEEDS)]}
                rows.extend(batch)
            write_jsonl(rows, output)
            print(f"{domain}{suffix}: run {repeat}/{runs}, {len(rows)} records", flush=True)
        write_json(summarize_results(rows), output.with_suffix(".summary.json"))
        for item in summarize_results(rows):
            print(json.dumps(item), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/verified-benchmarks"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--laya-device", choices=("cpu", "mps", "cuda"))
    parser.add_argument("--cpu-comparison", action="store_true")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("runs must be at least one")
    os.environ["OPENAI_ENABLED"] = "false"
    os.environ["LAYA_ENABLED"] = "true"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    matrix = episodes()
    laya = LayaAdapter(model="convaiinnovations/laya", subfolder="", device=args.laya_device)
    warmups = {"laya": warmup(laya, matrix["streamguard"][0].evidence)}
    write_json(input_audit(laya, matrix), args.output_dir / "input-audit.json")
    adapters = [RulesAdapter(), JevAdapter(), laya, GeminiAdapter()]
    run_matrix(matrix, adapters, args.runs, args.output_dir)
    if args.cpu_comparison:
        cpu = LayaAdapter(model="convaiinnovations/laya", subfolder="", device="cpu")
        cpu.name = "laya-cpu"
        warmups["laya-cpu"] = warmup(cpu, matrix["streamguard"][0].evidence)
        run_matrix(matrix, [cpu], args.runs, args.output_dir, "-laya-cpu")
    agent = laya._get_model()
    from huggingface_hub import snapshot_download
    import torch
    checkpoint_path = Path(snapshot_download(laya.model, local_files_only=True))
    write_json(warmups, args.output_dir / "warmup-records.json")
    write_json({
        "date": datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat(),
        "runs_per_case": args.runs, "seeds": list(BENCHMARK_SEEDS),
        "engines": [a.name for a in adapters], "openai_enabled": False,
        "laya": {"model": laya.model, "revision": checkpoint_path.name,
                 "subfolder": laya.subfolder, "requested_device": args.laya_device,
                 "device": str(agent.device), "encoder": agent.cfg["encoder"],
                 "max_len": agent.cfg["max_len"], "head_max_len": agent.cfg["head_max_len"],
                 "latency_scope": "warm adapter call including serialization and input validation, excluding model loading"},
        "cpu_comparison": args.cpu_comparison,
        "warmup_calls_per_device": 2, "provider_order": "deterministic cyclic rotation",
        "remote_latency_scope": "API end to end including SDK client construction",
        "python": platform.python_version(), "platform": f"{platform.system()} {platform.machine()}",
        "torch_threads": torch.get_num_threads(),
        "hardware": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
                    if platform.system() == "Darwin" else platform.processor(),
        "packages": {name: importlib.metadata.version(name) for name in
                     ("laya", "torch", "transformers", "typesafe-sdk", "google-genai")},
        "git_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_sha256": {str(p): sha256(p.read_bytes()).hexdigest() for p in
                          [Path("src/jevops/adapters/laya.py"), Path("src/jevops/benchmark/runner.py"),
                           Path("src/jevops/benchmark/oracle.py"), Path("src/jevops/adapters/rubric.py"),
                           Path("src/jevops/adapters/rules.py"), Path(__file__).relative_to(Path.cwd())]},
    }, args.output_dir / "run-metadata.json")


if __name__ == "__main__":
    main()
