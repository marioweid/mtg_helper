"""Shared, exact Deck Tutor acceptance-list data for deterministic adapters."""

import re
from dataclasses import dataclass
from pathlib import Path

_PARENT_SPEC = Path(__file__).parents[2] / ".agent/specs/deck-tutor/spec.md"
_CARD_LINE = re.compile(r"^(?P<quantity>\d+) (?P<name>.+?)(?: \*CMDR\*)?$")


@dataclass(frozen=True)
class TutorFixture:
    """One supplied Lerndeck with its required Tutor-Modus and command zone."""

    name: str
    mode: str
    commanders: tuple[str, ...]
    mainboard: tuple[tuple[int, str], ...]


def acceptance_fixtures() -> tuple[TutorFixture, TutorFixture]:
    """Parse the approved complete lists without substituting stock-card facts."""
    text = _PARENT_SPEC.read_text(encoding="utf-8")
    return (
        _fixture(text, "Yuna", "Yuna:", "commander", ("Yuna, Grand Summoner",)),
        _fixture(
            text,
            "Blue Farm",
            "Blue Farm:",
            "cedh",
            ("Kraum, Ludevic's Opus", "Tymna the Weaver"),
        ),
    )


def _fixture(
    text: str, name: str, heading: str, mode: str, commanders: tuple[str, ...]
) -> TutorFixture:
    """Extract one fenced list and exclude the supplied non-current sideboard."""
    section = text.split(heading, maxsplit=1)[1].split("```", maxsplit=2)[1]
    entries = []
    for line in section.splitlines():
        if line == "SIDEBOARD:":
            break
        match = _CARD_LINE.match(line)
        if match and match["name"] not in commanders:
            entries.append((int(match["quantity"]), match["name"]))
    return TutorFixture(name=name, mode=mode, commanders=commanders, mainboard=tuple(entries))
