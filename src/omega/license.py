"""OMEGA License — Community Edition.

The community edition is free and open-source. Pro features
(coordination, entity engine, cloud sync, oracle) are available
at https://omegamax.co.
"""

from __future__ import annotations

from typing import Any


def is_pro() -> bool:
    """Check if Pro features are available. Always False in community edition."""
    return False


def activate(key: str) -> bool:
    """Activate a Pro license key.

    In the community edition, this is a no-op.
    Visit https://omegamax.co for Pro activation.
    """
    print("Pro activation is available at https://omegamax.co")
    return False


def deactivate() -> None:
    """Remove the local license. No-op in community edition."""
    pass


def license_status() -> dict[str, Any]:
    """Return current license status."""
    return {"plan": "community", "pro": False, "active": False}
