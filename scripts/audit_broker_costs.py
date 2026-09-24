"""Account for completed broker requests whose responses missed a worker deadline."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from package_baseline_evidence import public_events, usage_missing_calls


def audit(campaign, broker):
    campaign, broker = Path(campaign), Path(broker)
    results = json.loads((campaign / "results.json").read_text())
    if not results["completed"]:
        raise ValueError("Finish the campaign before sealing its cost audit")
    cached_requests = {path.name.rsplit("-", 1)[0] for path in broker.glob("*-?.png")}
    completed_requests = {path.name.removesuffix(".response.json")
                          for path in broker.glob("*.response.json")}
    if cached_requests - completed_requests:
        raise ValueError("Broker has unfinished requests; wait for their cost evidence")
    worker_requests, episode_cases = Counter(), {}
    for path in campaign.glob("*/events.jsonl"):
        for line in path.read_text().splitlines():
            event = json.loads(line)
            if event["kind"] == "model_request":
                worker_requests[event["payload"]["observation_id"]] += 1
            elif event["kind"] == "observation":
                episode_cases[event["payload"]["episode_id"]] = path.parent.name
    accounted, rows = Counter(), []
    for path in sorted(broker.glob("*.response.json")):
        response = json.loads(path.read_text())
        events = [{"kind": kind, "payload": payload} for kind, payload in response["events"]]
        requests = [event for event in events if event["kind"] == "model_request"]
        if len(requests) != 1 or response["calls"] != 1:
            raise ValueError("Audit requires the one-request-per-nonce broker contract")
        observation = requests[0]["payload"]["observation_id"]
        if observation.split(":")[0] not in episode_cases:
            raise ValueError("Broker response belongs to a different campaign")
        included = accounted[observation] < worker_requests[observation]
        accounted[observation] += 1
        rows.append({
            "request_sha256": hashlib.sha256(response["nonce"].encode()).hexdigest(),
            "episode": episode_cases.get(observation.split(":")[0]),
            "observation_id": observation,
            "included_in_worker_trace": included,
            "api_attempts": response["calls"],
            "input_tokens": response["input_tokens"],
            "output_tokens": response["output_tokens"],
            "usage_missing_calls": usage_missing_calls(events),
            "late_response_events": public_events(events) if not included else [],
        })
    if any(accounted[key] < count for key, count in worker_requests.items()):
        raise ValueError("Broker evidence missing for an acknowledged worker request")
    worker_calls = sum(row["summary"]["api_calls"] for row in results["rows"])
    if worker_calls != sum(worker_requests.values()):
        raise ValueError("Worker summaries disagree with recorded requests")
    for field in ("input_tokens", "output_tokens"):
        if sum(row[field] for row in rows if row["included_in_worker_trace"]) != sum(
            row["summary"][field] for row in results["rows"]
        ):
            raise ValueError("Acknowledged broker usage differs from worker totals")
    late = [row for row in rows if not row["included_in_worker_trace"]]
    return {
        "campaign_results_sha256": hashlib.sha256((campaign / "results.json").read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256((campaign / "protocol.json").read_bytes()).hexdigest(),
        "worker_recorded_api_attempts": worker_calls,
        "broker_recorded_api_attempts": len(rows),
        "unacknowledged_api_attempts": len(late),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "usage_missing_calls": sum(row["usage_missing_calls"] for row in rows),
        "rows": rows,
        "note": "Broker totals include late responses once, never added twice to worker totals. "
        "Missing token usage is unknown. Worker deadline failures remain failures; this audit "
        "does not turn late decisions into robot actions or change any success result. "
        "Only recorded API attempts are attested; provider billing is not independently verified.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--broker", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    Path(args.out).write_text(json.dumps(audit(args.campaign, args.broker), indent=2) + "\n")
