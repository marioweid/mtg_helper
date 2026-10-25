"""Safety checks for the narrow local New Cards copy command."""

import pytest

from scripts.copy_new_cards_local import validate_target

pytestmark = pytest.mark.no_db


def test_rejects_equivalent_or_remote_copy_targets() -> None:
    source = "postgresql://user:secret@localhost:5432/source"
    with pytest.raises(ValueError, match="must not identify"):
        validate_target(source, "postgresql://other:secret@127.0.0.1:5432/source")
    with pytest.raises(ValueError, match="loopback"):
        validate_target(source, "postgresql://user:secret@example.test:5432/local_copy")


def test_accepts_a_different_loopback_database() -> None:
    validate_target(
        "postgresql://user:secret@localhost:5432/source",
        "postgresql://user:secret@localhost:5432/local_copy",
    )
