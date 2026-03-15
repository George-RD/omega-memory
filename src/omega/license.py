"""OMEGA License Management — Pro activation and validation.

License state is cached in ~/.omega/license.json with a 7-day validity window.
The omega activate CLI command calls omegamemory.com/api/activate to validate.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("omega.license")

OMEGA_DIR = Path.home() / ".omega"
LICENSE_FILE = OMEGA_DIR / "license.json"

ACTIVATE_URL = "https://omegamax.co/api/activate"
CACHE_DAYS = 7
GRACE_DAYS = 3  # Extra grace on network failure
_LICENSE_TIMEOUT = int(__import__("os").environ.get("OMEGA_LICENSE_TIMEOUT", "30"))


def _call_activate_api(key: str) -> dict[str, Any]:
    """Call the activation API. Returns parsed JSON response."""
    import urllib.request
    import urllib.error

    data = json.dumps({"key": key}).encode()
    req = urllib.request.Request(
        ACTIVATE_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_LICENSE_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _read_license() -> dict[str, Any] | None:
    """Read and parse the license file. Returns None if missing or corrupt."""
    try:
        if not LICENSE_FILE.exists():
            return None
        data = json.loads(LICENSE_FILE.read_text())
        if "key" not in data or "valid_until" not in data:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _write_license(key: str, valid_until: float, activated_at: float | None = None) -> None:
    """Write license cache to disk with restricted permissions (0o600)."""
    OMEGA_DIR.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(json.dumps({
        "key": key,
        "valid_until": valid_until,
        "activated_at": activated_at or time.time(),
    }))
    LICENSE_FILE.chmod(0o600)


def activate(key: str) -> bool:
    """Activate a license key by validating with the API.

    Returns True if activation succeeded, False otherwise.
    """
    try:
        result = _call_activate_api(key)
    except Exception as e:
        logger.warning("Activation failed: %s", e)
        return False

    if not result.get("valid"):
        reason = result.get("reason", "Unknown error")
        logger.info("License invalid: %s", reason)
        return False

    # Parse expires_at ISO string to epoch
    expires_at = result.get("expires_at", "")
    try:
        dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        valid_until = dt.timestamp()
    except (ValueError, AttributeError):
        # Fallback: 7 days from now
        valid_until = time.time() + (CACHE_DAYS * 86400)

    _write_license(key, valid_until)
    return True


def is_pro() -> bool:
    """Check if a valid Pro license exists.

    Reads cached license. If valid_until > now, returns True.
    If within 24h of expiry, triggers silent re-validation.
    If expired, attempts re-validation; on network failure, grants 3-day grace.
    """
    import os
    if os.environ.get("OMEGA_DEV_PRO") == "1":
        return True

    data = _read_license()
    if data is None:
        return False

    now = time.time()
    valid_until = data["valid_until"]

    if valid_until > now:
        # Still valid — check if nearing expiry for proactive re-validation
        if valid_until - now < 86400:  # Within 24 hours
            _try_revalidate(data["key"], data)
        return True

    # Expired — try to re-validate
    return _try_revalidate(data["key"], data)


def _try_revalidate(key: str, current_data: dict) -> bool:
    """Attempt to re-validate a license key silently.

    On success, updates the cache. On network failure, extends grace period.
    On confirmed cancellation, returns False.
    """
    try:
        result = _call_activate_api(key)
    except Exception:
        # Network failure — grant grace period if not already well past expiry
        now = time.time()
        grace_until = current_data["valid_until"] + (GRACE_DAYS * 86400)
        if now < grace_until:
            logger.debug("Network failure, grace period active until %s",
                        datetime.fromtimestamp(grace_until, tz=timezone.utc).isoformat())
            return True
        return False

    if result.get("valid"):
        expires_at = result.get("expires_at", "")
        try:
            dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            valid_until = dt.timestamp()
        except (ValueError, AttributeError):
            valid_until = time.time() + (CACHE_DAYS * 86400)
        _write_license(key, valid_until, current_data.get("activated_at"))
        return True

    return False


def deactivate() -> None:
    """Remove the local license file."""
    try:
        LICENSE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def license_status() -> dict[str, Any]:
    """Return current license status for display."""
    data = _read_license()
    if data is None:
        return {"active": False, "key": None, "valid_until": None}

    now = time.time()
    key = data["key"]
    # Mask the key for display: show first 14 + last 4 chars
    if len(key) > 20:
        masked = key[:14] + "..." + key[-4:]
    else:
        masked = key

    return {
        "active": data["valid_until"] > now,
        "key": masked,
        "valid_until": datetime.fromtimestamp(data["valid_until"], tz=timezone.utc).isoformat(),
    }
