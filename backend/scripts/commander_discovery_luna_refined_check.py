"""Fresh six-call Luna experiment: $0.25 cap, 300s timeout, no retries or ledger resume."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from openai import OpenAI

from mtg_helper.services.recommendations import refinement as refined
from scripts import commander_discovery_check as base
from scripts import commander_discovery_luna_pipeline as pipeline
from scripts.deck_recovery_check import freeze
from scripts.new_cards_data_spike import Card, write_json


class Experiment:
    """Own the fresh single-use receipt and all dependencies for this fixed three-stage run."""

    def __init__(self, workspace: pipeline.Workspace, path: Path, client: OpenAI) -> None:
        self.workspace = workspace
        self.path = path
        self.client = client
        self.report: Card = {
            "started_at": datetime.now(UTC).isoformat(),
            "runs": [],
            "reserved_usd": pipeline.reservation(),
            "budget_usd": pipeline.BUDGET_USD,
        }

    def run(self) -> Card:
        """Checkpoint each request before sending; retain failures and stop on unknown billing."""
        if self.client.max_retries != 0:
            raise ValueError("Fresh Luna experiment requires SDK max_retries=0")
        pipeline.reservation()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(self.report, indent=2) + "\n")
        for index, (phase, case_id) in enumerate(pipeline.CALLS):
            try:
                payload, provenance = self.workspace.payload(phase, case_id, self.report)
                stage = pipeline.stage(phase, payload)
                if not self._within_bounds(index, stage, payload):
                    break
                freeze(
                    self.path.parent / "requests" / f"{phase}-{case_id}.json",
                    {
                        "phase": phase,
                        "case_id": case_id,
                        "instructions": stage.prompt,
                        "schema": stage.schema.model_json_schema(),
                        "payload": payload,
                    },
                )
                freeze(self.path.parent / "observations" / f"{phase}-{case_id}.json", provenance)
            except ValueError as exc:
                self.report["stopped"] = f"{phase}/{case_id}: input/prerequisite failure: {exc}"
                break
            self._attempt(phase, case_id, payload, stage)
            if self.report.get("stopped"):
                break
        write_json(self.path, self.report)
        return self.report

    def _within_bounds(self, index: int, stage: base.Stage, payload: Card) -> bool:
        if base.request_bytes(stage, payload) > stage.byte_limit:
            self.report["stopped"] = "Input byte bound exceeded; no truncation or request"
        remaining = sum(
            base.estimated_cost(pipeline.MODEL, *pipeline.BOUNDS[phase])
            for phase, _ in pipeline.CALLS[index:]
        )
        spent = sum(run.get("estimated_cost_usd", 0) for run in self.report["runs"])
        if spent + remaining > pipeline.BUDGET_USD:
            self.report["stopped"] = "Remaining reservation exceeds authorized $0.25 ceiling"
        return not self.report.get("stopped")

    def _attempt(self, phase: str, case_id: str, payload: Card, stage: base.Stage) -> None:
        attempt = {
            "phase": phase,
            "case_id": case_id,
            "model": pipeline.MODEL,
            "state": "attempted",
            "input_sha256": hashlib.sha256(
                json.dumps(payload, ensure_ascii=False).encode()
            ).hexdigest(),
            "input_byte_bound": stage.byte_limit,
            "max_output_tokens": stage.output_limit,
        }
        self.report["runs"].append(attempt)
        write_json(self.path, self.report)
        attempt.update(base.call_once(self.client, phase, pipeline.MODEL, payload, stage=stage))
        attempt["state"] = "returned"
        self._price(attempt, stage)
        if not self.report.get("stopped"):
            self._validate(attempt, payload, stage)
        write_json(self.path, self.report)
        print(phase, case_id, attempt.get("status", attempt.get("error")), flush=True)

    def _price(self, attempt: Card, stage: base.Stage) -> None:
        usage = attempt.get("usage")
        if (
            not isinstance(usage, dict)
            or attempt.get("response_model") != pipeline.MODEL
            or attempt.get("service_tier") != "default"
        ):
            self.report["stopped"] = (
                "Unknown usage, model or service-tier pricing; no further requests"
            )
            return
        counts = [usage.get("input_tokens"), usage.get("output_tokens")]
        if any(type(n) is not int or n < 0 for n in counts):
            self.report["stopped"] = "Invalid usage; no further requests"
            return
        attempt["estimated_cost_usd"] = base.estimated_cost(pipeline.MODEL, *counts)
        if counts[0] > stage.byte_limit or counts[1] > stage.output_limit:
            self.report["stopped"] = (
                "Reported usage exceeds reserved call bound; no further requests"
            )

    def _validate(self, attempt: Card, payload: Card, stage: base.Stage) -> None:
        if attempt.get("status") != "completed":
            self.report["stopped"] = "Incomplete response; retain output and stop without retry"
            return
        try:
            raw = json.loads(attempt["output"], object_pairs_hook=refined.unique_object)
            stage.schema.model_validate(raw)
        except ValueError as exc:
            attempt["quality_error"] = str(exc)
            self.report["stopped"] = "Invalid structured output; no repair, substitution or retry"


def summarize(report: Card, destination: Path) -> Card:
    """Replay saved output and quotation coverage; this does not measure semantic accuracy."""
    rows = []
    for run in report["runs"]:
        row = {
            key: run.get(key)
            for key in (
                "phase",
                "case_id",
                "model",
                "status",
                "seconds",
                "estimated_cost_usd",
                "usage",
            )
        }
        if run.get("status") == "completed":
            request = json.loads(
                (destination / "requests" / f"{run['phase']}-{run['case_id']}.json").read_text(
                    encoding="utf-8"
                )
            )
            try:
                if run["phase"] == "review":
                    row.update(refined.parse_review(run["output"], request["payload"]))
                else:
                    raw = json.loads(run["output"], object_pairs_hook=refined.unique_object)
                    row["plan"] = refined.RefinementPlan.model_validate(raw).model_dump()
            except ValueError:
                row["error"] = "invalid_structured_output"
        else:
            row["error"] = run.get("error", "incomplete")
        rows.append(row)
    unpriced = sum("estimated_cost_usd" not in run for run in report["runs"])
    known = sum(run.get("estimated_cost_usd", 0) for run in report["runs"])
    return {
        "attempts": len(rows),
        "authorized_maximum": 6,
        "budget_usd": pipeline.BUDGET_USD,
        "estimated_cost_usd": None if unpriced else known,
        "known_estimated_cost_usd": known,
        "unpriced_attempts": unpriced,
        "stopped": report.get("stopped"),
        "runs": rows,
        "scope": "known regressions; quotation coverage is not semantic accuracy",
    }


def main() -> None:
    """Prepare offline, execute once when explicitly authorized, or summarize saved evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    workspace = pipeline.prepare()
    print("Reserved upper estimated spend:", pipeline.reservation())
    path = pipeline.DESTINATION / "results.json"
    if args.live:
        from mtg_helper.config import settings

        with OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            max_retries=0,
            timeout=pipeline.TIMEOUT_SECONDS,
        ) as client:
            report = Experiment(workspace, path, client).run()
    elif args.summarize:
        report = json.loads(path.read_text(encoding="utf-8"))
    else:
        print("Fresh inputs prepared offline; no paid calls made.")
        return
    result = summarize(report, pipeline.DESTINATION)
    write_json(pipeline.DESTINATION / "summary.json", result)
    print("Attempts:", result["attempts"], "estimated spend:", result["estimated_cost_usd"])


if __name__ == "__main__":
    main()
