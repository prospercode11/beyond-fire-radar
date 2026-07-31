#!/usr/bin/env python3
"""Small, dependency-light developer command runner."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]


def run(command: List[str], *, env: Optional[Dict[str, str]] = None) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Beyond Fire Radar developer commands")
    parser.add_argument(
        "command", choices=["migrate", "api", "api-smoke", "test", "lint", "format"]
    )
    args = parser.parse_args()

    if args.command == "migrate":
        run([sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"])
    elif args.command == "api":
        run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "apps/api",
                "--host",
                os.getenv("API_HOST", "127.0.0.1"),
                "--port",
                os.getenv("API_PORT", "8000"),
                "--reload",
            ]
        )
    elif args.command == "api-smoke":
        run([sys.executable, "scripts/api_smoke.py"])
    elif args.command == "test":
        run([sys.executable, "-m", "pytest"])
    elif args.command == "lint":
        run([sys.executable, "-m", "ruff", "check", "apps/api", "scripts"])
    elif args.command == "format":
        run([sys.executable, "-m", "ruff", "format", "apps/api", "scripts"])


if __name__ == "__main__":
    main()
