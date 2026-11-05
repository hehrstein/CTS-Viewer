"""Tests for the runtime translations shipped with the integration."""

from __future__ import annotations

import json
from pathlib import Path


def test_english_translation_matches_the_default_strings() -> None:
    """Home Assistant can use English as the runtime fallback language."""
    integration_path = Path(__file__).parents[1] / "custom_components" / "cts_strasbourg"

    strings = json.loads((integration_path / "strings.json").read_text("utf-8"))
    english = json.loads(
        (integration_path / "translations" / "en.json").read_text("utf-8")
    )

    assert english == strings
