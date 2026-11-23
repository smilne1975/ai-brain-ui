"""Standalone product capabilities and temporary legacy compatibility."""

import os


def legacy_cad_enabled() -> bool:
    # Opt in at process startup; the standalone product never auto-detects this switch.
    return os.environ.get("BRAIN_LEGACY_CAD", "").strip() == "1"


def cad_matches_scan(brain: dict, private_token: str | None) -> bool:
    # Old caches without the flag predate the split, so they cannot be reused.
    return brain.get("legacy_cad") is (legacy_cad_enabled() and private_token is None)
