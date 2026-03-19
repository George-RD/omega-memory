"""Tests for omega.license — Pro license management."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from omega.license import (
    LICENSE_FILE,
    activate,
    is_pro,
    deactivate,
    license_status,
)


@pytest.fixture(autouse=True)
def clean_license(tmp_path, monkeypatch):
    """Use a temp license file for all tests."""
    test_license = tmp_path / "license.json"
    monkeypatch.setattr("omega.license.LICENSE_FILE", test_license)
    yield test_license


class TestIsPro:
    def test_no_license_file(self):
        assert is_pro() is False

    def test_valid_license(self, clean_license):
        future = time.time() + 86400  # 1 day from now
        clean_license.write_text(json.dumps({
            "key": "OMEGA-PRO-test",
            "valid_until": future,
            "activated_at": time.time(),
        }))
        assert is_pro() is True

    def test_expired_license(self, clean_license):
        past = time.time() - (4 * 86400)  # 4 days ago, beyond 3-day grace
        clean_license.write_text(json.dumps({
            "key": "OMEGA-PRO-test",
            "valid_until": past,
            "activated_at": time.time() - (5 * 86400),
        }))
        # Expired and re-validation will fail (no network in test)
        assert is_pro() is False

    def test_corrupt_license_file(self, clean_license):
        clean_license.write_text("not json")
        assert is_pro() is False


class TestActivate:
    @patch("omega.license._call_activate_api")
    def test_successful_activation(self, mock_api, clean_license):
        future_iso = "2099-01-01T00:00:00Z"
        mock_api.return_value = {"valid": True, "expires_at": future_iso}

        result = activate("OMEGA-PRO-test-key")
        assert result is True
        assert clean_license.exists()

        data = json.loads(clean_license.read_text())
        assert data["key"] == "OMEGA-PRO-test-key"
        assert "valid_until" in data

    @patch("omega.license._call_activate_api")
    def test_invalid_key(self, mock_api, clean_license):
        mock_api.return_value = {"valid": False, "reason": "Invalid license key"}

        result = activate("OMEGA-PRO-bad-key")
        assert result is False
        assert not clean_license.exists()

    @patch("omega.license._call_activate_api")
    def test_network_error(self, mock_api, clean_license):
        mock_api.side_effect = Exception("Connection refused")

        result = activate("OMEGA-PRO-test-key")
        assert result is False


class TestDeactivate:
    def test_deactivate_removes_file(self, clean_license):
        clean_license.write_text(json.dumps({
            "key": "OMEGA-PRO-test",
            "valid_until": time.time() + 86400,
            "activated_at": time.time(),
        }))
        deactivate()
        assert not clean_license.exists()

    def test_deactivate_no_file(self):
        # Should not raise
        deactivate()


class TestLicenseStatus:
    def test_no_license(self):
        status = license_status()
        assert status["active"] is False
        assert status["key"] is None

    def test_active_license(self, clean_license):
        future = time.time() + 86400
        clean_license.write_text(json.dumps({
            "key": "OMEGA-PRO-abcd1234-5678-90ab-cdef-1234567890ab",
            "valid_until": future,
            "activated_at": time.time(),
        }))
        status = license_status()
        assert status["active"] is True
        assert status["key"].startswith("OMEGA-PRO-abcd")
        assert status["key"].endswith("...90ab")
