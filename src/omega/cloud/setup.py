"""OMEGA Cloud Setup -- Configure Supabase connection for cloud sync.

Usage:
    omega cloud setup     # Interactive setup
    omega cloud status    # Check sync status
    omega cloud sync      # Run sync now
    omega cloud schema    # Print SQL schema for Supabase
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("omega.cloud.setup")


def _omega_home() -> Path:
    return Path(os.environ.get("OMEGA_HOME", str(Path.home() / ".omega")))


def setup_supabase(url: str, anon_key: str, service_key: str = "") -> str:
    """Configure Supabase connection credentials."""
    secrets_path = _omega_home() / "secrets.json"

    # Load existing secrets
    existing = {}
    if secrets_path.exists():
        with open(secrets_path) as f:
            existing = json.load(f)

    # Update with Supabase config
    existing["supabase_url"] = url.rstrip("/")
    existing["supabase_key"] = anon_key
    if service_key:
        existing["supabase_service_key"] = service_key

    # Write with restricted permissions
    secrets_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(secrets_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(existing, indent=2).encode())
    finally:
        os.close(fd)

    return f"Supabase config saved to {secrets_path}"


def get_schema_sql() -> str:
    """Read and return the Supabase SQL schema."""
    schema_path = Path(__file__).parent / "schema.sql"
    if schema_path.exists():
        return schema_path.read_text()
    return "Error: schema.sql not found"


def verify_connection() -> str:
    """Verify Supabase connection works."""
    try:
        from omega.cloud.sync import _get_supabase_client

        client = _get_supabase_client()
        # Try a simple query
        result = client.table("sync_state").select("table_name").limit(1).execute()
        return "Supabase connection verified successfully."
    except FileNotFoundError:
        return "Not configured. Run: omega cloud setup"
    except ImportError:
        return "supabase package not installed. Run: pip install supabase"
    except Exception as e:
        return f"Connection failed: {e}"
