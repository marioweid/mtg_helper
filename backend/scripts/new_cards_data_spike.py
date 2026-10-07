"""Read-only Scryfall feasibility probe; never connects to an application database.

Run from backend/: uv run python -m scripts.new_cards_data_spike --download
Artifacts are cached under .cache/new-cards-spike; downloads are explicit and bounded.
"""

import argparse
import gzip
import hashlib
import json
import time
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

Card = dict[str, Any]
CACHE = Path(".cache/new-cards-spike")
_HEADERS = {"User-Agent": "MTGHelper-Feasibility/1.0", "Accept": "application/json"}
_EXCLUDED_LAYOUTS = {"token", "double_faced_token", "art_series", "emblem", "planar", "scheme"}


def paper_design(card: Card) -> bool:
    """Identify plausible paper gameplay objects, not certify future legality."""
    return bool(
        "paper" in card.get("games", [])
        and card.get("oracle_id")
        and card.get("layout") not in _EXCLUDED_LAYOUTS
        and card.get("border_color") not in {"silver", "gold"}
        and card.get("security_stamp") != "acorn"
        and card.get("set_type") not in {"memorabilia", "token", "vanguard"}
    )


def rules_text(card: Card) -> str:
    """Preserve each face's rules and identity without implying simultaneous access."""
    faces = card.get("card_faces") or []
    if faces:
        return "\n".join(
            f"{face['name']} [{face.get('type_line', '')}]: {face.get('oracle_text', '')}"
            for face in faces
        )
    return card.get("oracle_text") or ""


def window_state(first_release: str | None, today: date) -> str:
    """Classify release age; unknown dates do not become new by observation."""
    if first_release is None:
        return "unknown"
    released = date.fromisoformat(first_release)
    if released > today:
        return "upcoming"
    return "recent" if today < released + timedelta(days=60) else "expired"


def iter_cards(path: Path) -> Iterator[Card]:
    """Stream and validate a gzip JSONL archive without loading the full export."""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            card = json.loads(line)
            if not isinstance(card, dict) or card.get("object") != "card":
                raise ValueError(f"Invalid card object in {path.name}, line {number}")
            yield card


def download_export(client: httpx.Client, entry: Card, directory: Path) -> Card:
    """Download one official archive with size bound and atomic local publication."""
    uri = entry["jsonl_download_uri"]
    host = urlparse(uri).hostname or ""
    if urlparse(uri).scheme != "https" or not host.endswith(".scryfall.io"):
        raise ValueError("Bulk manifest returned a non-Scryfall download URL")
    path = directory / f"{entry['type']}.jsonl.gz"
    partial = path.with_suffix(".partial")
    started = time.perf_counter()
    size = 0
    digest = hashlib.sha256()
    with client.stream("GET", uri) as response, partial.open("wb") as target:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > 130 * 1024 * 1024:
                raise ValueError("Bulk archive exceeded the probe's 130 MiB limit")
            digest.update(chunk)
            target.write(chunk)
    partial.replace(path)
    return {
        "type": entry["type"],
        "updated_at": entry["updated_at"],
        "bytes": size,
        "sha256": digest.hexdigest(),
        "download_seconds": round(time.perf_counter() - started, 3),
    }


def download(directory: Path) -> None:
    """Fetch two bulk exports once; fail visibly on HTTP/network errors without retrying."""
    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=_HEADERS, timeout=180, follow_redirects=True) as client:
        response = client.get("https://api.scryfall.com/bulk-data")
        response.raise_for_status()
        entries = {entry["type"]: entry for entry in response.json()["data"]}
        sources = [
            download_export(client, entries[kind], directory)
            for kind in ("default_cards", "oracle_cards")
        ]
    write_json(directory / "sources.json", sources)


def first_paper_dates(cards: Iterator[Card]) -> tuple[dict[str, str], Counter[str]]:
    """Reduce all printing dates by Oracle ID, independently of the reprint flag."""
    dates: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for card in cards:
        counts["all_printings"] += 1
        if not paper_design(card):
            continue
        counts["paper_printings"] += 1
        released = card.get("released_at")
        if not released:
            counts["paper_missing_release"] += 1
            continue
        date.fromisoformat(released)
        oracle = card["oracle_id"]
        dates[oracle] = min(dates.get(oracle, released), released)
    return dates, counts


def compact(card: Card, first: str | None) -> Card:
    """Retain public card facts necessary for a reproducible recommendation probe."""
    fields = (
        "id",
        "oracle_id",
        "name",
        "mana_cost",
        "cmc",
        "type_line",
        "color_identity",
        "keywords",
        "layout",
        "released_at",
        "reprint",
        "set",
        "set_type",
        "games",
        "legalities",
        "preview",
        "edhrec_rank",
        "prices",
        "game_changer",
        "card_faces",
        "oracle_text",
        "scryfall_uri",
    )
    result = {field: card.get(field) for field in fields}
    result.update(first_paper_release=first, full_rules=rules_text(card))
    return result


def analyze(directory: Path, today: date) -> Card:
    """Measure canonical date errors and current-importer coverage using actual code."""
    from mtg_helper.services.scryfall import (
        _is_commander_playable,
        _is_commander_relevant,
        _map_card,
    )

    started = time.perf_counter()
    dates, counts = first_paper_dates(iter_cards(directory / "default_cards.jsonl.gz"))
    catalog: list[Card] = []
    samples: dict[str, list[str]] = {}
    sets: Counter[str] = Counter()
    legality: Counter[str] = Counter()
    for card in iter_cards(directory / "oracle_cards.jsonl.gz"):
        counts["oracle_records"] += 1
        first = dates.get(card.get("oracle_id", ""))
        catalog.append(compact(card, first))
        if first is None:
            continue
        state = window_state(first, today)
        counts[f"paper_{state}"] += 1
        mapped = _map_card(card)
        loses_text = bool(rules_text(card)) and not mapped["oracle_text"]
        counts["paper_face_text_lost"] += int(loses_text)
        rep_recent = window_state(card.get("released_at"), today) in {"upcoming", "recent"}
        if rep_recent and state == "expired":
            counts["false_new_from_representative_date"] += 1
            add_sample(samples, "false_new_from_representative_date", card["name"])
        if state not in {"upcoming", "recent"}:
            continue
        sets[card["set"]] += 1
        legality[card["legalities"].get("commander", "unknown")] += 1
        retained = _is_commander_relevant(card) and _is_commander_playable(card)
        counts[f"{state}_retained_by_current_importer"] += int(retained)
        counts[f"{state}_missing_preview_metadata"] += int(not card.get("preview"))
        counts[f"{state}_missing_edhrec_rank"] += int(card.get("edhrec_rank") is None)
        counts[f"{state}_face_text_lost"] += int(loses_text)
        if not retained:
            add_sample(samples, f"{state}_dropped", card["name"])
        if loses_text:
            add_sample(samples, f"{state}_face_text_lost", card["name"])
    write_json(directory / "catalog.json", catalog)
    report = {
        "observed_at": datetime.now(UTC).isoformat(),
        "as_of": today.isoformat(),
        "scope": "full default-printing export + oracle representatives; no database writes",
        "caveat": "paper shape is not positive proof of upcoming Commander eligibility",
        "sources": json.loads((directory / "sources.json").read_text()),
        "counts": dict(counts),
        "active_sets": dict(sets),
        "active_legalities": dict(legality),
        "samples": samples,
        "analysis_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(directory / "data-report.json", report)
    return report


def add_sample(samples: dict[str, list[str]], key: str, name: str) -> None:
    """Keep bounded diagnostic examples without flooding the report."""
    values = samples.setdefault(key, [])
    if len(values) < 12:
        values.append(name)


def write_json(path: Path, value: object) -> None:
    """Write a local UTF-8 artifact; callers only provide public/synthetic data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    """Run the explicit download or reuse existing artifacts, then print aggregate findings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(UTC).date())
    args = parser.parse_args()
    if args.download:
        download(CACHE)
    report = analyze(CACHE, args.as_of)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
