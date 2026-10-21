"""Acceptance seams for globally shared Commander-Konstellation assessments."""

import json
from uuid import uuid4

import pytest

from mtg_helper.services.new_cards.evaluator import EvidenceRequest


@pytest.mark.no_db
def test_ac01_evaluator_payload_has_only_commander_and_candidate_facts() -> None:
    """The provider seam never receives private deck or account data."""
    commander = {"oracle_id": str(uuid4()), "name": "Commander", "oracle_text": "Draw."}
    candidate = {"oracle_id": str(uuid4()), "name": "Candidate", "oracle_text": "Fly."}
    request = EvidenceRequest({"commanders": [commander]}, [candidate])

    payload = json.loads(request.payload())

    assert payload == {
        "commanders": [{"key": "D00", "name": "Commander", "oracle_text": "Draw."}],
        "candidates": [{"key": "C01", "name": "Candidate", "oracle_text": "Fly."}],
    }
