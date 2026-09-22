"""Credential-safe process launcher for the patched TCX add-on."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

RUNTIME_OPTION_KEYS = (
    "log_level",
    "WS_TRACE",
    "AUTO_RECONNECT",
    "RECONNECT_TIMER",
    "PING_TIMER",
    "POOL_SHAPE",
    "POOL_LENGTH_FT",
    "POOL_WIDTH_FT",
    "POOL_SHALLOW_FT",
    "POOL_DEEP_FT",
    "POOL_VOLUME",
    "HEATER_BTU",
    "OUTDOOR_TEMP_ENTITY",
)


def load_options(path: Path) -> dict[str, str]:
    """Load only the options consumed by the TCX process."""
    document = json.loads(path.read_text(encoding="utf-8"))
    username = document.get("JANDY_USERNAME")
    password = document.get("JANDY_PASSWORD")
    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        raise ValueError("Jandy credentials are not configured")

    environment = {
        "JANDY_USERNAME": username,
        "JANDY_PASSWORD": password,
    }
    for key in RUNTIME_OPTION_KEYS:
        value = document.get(key)
        if value is not None and value != "":
            environment[key] = str(value)
    return environment


def main() -> None:
    """Start Gunicorn with the configured environment without logging secrets."""
    environment = os.environ.copy()
    environment.update(load_options(Path("/data/options.json")))
    os.chdir("/opt/jandy")
    gunicorn = shutil.which("gunicorn")
    if gunicorn is None:
        raise RuntimeError("Gunicorn executable is unavailable")
    print(f"Starting the TCX service with {gunicorn}", flush=True)
    result = subprocess.run(
        (
            gunicorn,
            "--log-level",
            "debug",
            "--error-logfile",
            "-",
            "--bind",
            "0.0.0.0:5050",
            "main:app",
        ),
        check=False,
        env=environment,
    )
    print(f"TCX service exited with code {result.returncode}", flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
