"""Manage the Smart Traffic OS Docker Compose deployment."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = ROOT / "docker-compose.yml"


def run_compose(*arguments: str, check: bool = True) -> int:
    """Run Docker Compose from the repository root."""
    command = ["docker", "compose", "-f", str(COMPOSE_FILE), *arguments]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if check and completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.returncode


def validate_tools() -> None:
    """Validate Docker and Compose availability before deployment."""
    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI was not found on PATH")
    result = subprocess.run(
        ["docker", "compose", "version"], cwd=ROOT, check=False
    )
    if result.returncode != 0:
        raise RuntimeError("Docker Compose is unavailable")


def main() -> int:
    """Parse a deployment action and execute it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("build", "up", "down", "restart", "status", "logs", "config"),
        nargs="?",
        default="up",
    )
    parser.add_argument("--follow", action="store_true", help="Follow logs")
    args = parser.parse_args()

    try:
        validate_tools()
        if args.action == "build":
            return run_compose("build", "--pull")
        if args.action == "up":
            return run_compose("up", "-d", "--build", "--remove-orphans")
        if args.action == "down":
            return run_compose("down", "--remove-orphans")
        if args.action == "restart":
            run_compose("up", "-d", "--build", "--force-recreate", "--remove-orphans")
            return 0
        if args.action == "status":
            return run_compose("ps")
        if args.action == "logs":
            return run_compose("logs", "-f" if args.follow else "--tail=100")
        return run_compose("config")
    except RuntimeError as error:
        print(f"Deployment error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())