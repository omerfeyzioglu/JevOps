"""Publish seeded StreamGuard operational events to Kafka."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Sequence
from uuid import uuid4

from jevops.streamguard.simulation import Scenario
from jevops.streaming.scenarios import generate_events


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a seeded StreamGuard scenario.")
    parser.add_argument("--scenario", choices=[item.value for item in Scenario], required=True)
    parser.add_argument("--seed", type=int, default=401)
    parser.add_argument("--duration", type=int, default=70)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--run-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.duration < 1 or args.interval < 0:
        raise SystemExit("duration must be positive and interval must be non-negative")

    from confluent_kafka import Producer

    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = os.environ.get("STREAMGUARD_EVENTS_TOPIC", "streamguard.events")
    run_id = args.run_id or f"run-{args.seed}-{uuid4().hex[:8]}"
    producer = Producer({"bootstrap.servers": bootstrap, "client.id": "streamguard-generator"})

    print(f"publishing {args.scenario} as {run_id} to {topic}", flush=True)
    for event in generate_events(Scenario(args.scenario), args.seed, args.duration, run_id):
        producer.produce(
            topic,
            key=run_id.encode(),
            value=json.dumps(event.as_dict(), separators=(",", ":")).encode(),
        )
        producer.poll(0)
        print(
            json.dumps(
                {
                    "sequence": event.sequence,
                    "received": event.records_received,
                    "processed": event.records_processed,
                    "queue_depth": event.queue_depth,
                    "sink_errors": event.sink_errors,
                    "sink_latency_ms": event.sink_latency_ms,
                }
            ),
            flush=True,
        )
        if args.interval:
            time.sleep(args.interval)
    producer.flush(10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

