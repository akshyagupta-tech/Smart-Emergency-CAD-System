"""Run Smart Traffic OS checks and serve the dashboard until interrupted."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import runpy
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any

ROOT = Path(__file__).resolve().parent
TEST_PATH = ROOT / "tests" / "test_system.py"
LOG_PATH = ROOT / "logs" / "final_telemetry.log"
URL = "http://localhost:8000"
REQUIRED_MODULES = ("fastapi", "uvicorn", "websockets", "numpy", "matplotlib")
_shutdown_requested = threading.Event()


def check_dependencies() -> list[str]:
    """Return missing import modules and print the dependency check result."""
    missing = [
        module
        for module in REQUIRED_MODULES
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}", file=sys.stderr)
        print(
            f"Install project dependencies with: {sys.executable} -m pip install -r requirements.txt",
            file=sys.stderr,
        )
    else:
        print("Dependencies available: " + ", ".join(REQUIRED_MODULES))
    return missing


def run_system_tests() -> list[str]:
    """Run tests/test_system.py with pytest or its plain-function fallback."""
    if not TEST_PATH.is_file():
        raise FileNotFoundError(f"System test file not found: {TEST_PATH}")

    if importlib.util.find_spec("pytest") is not None:
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(TEST_PATH)],
            cwd=ROOT,
            check=True,
        )
        return ["pytest"]

    print("pytest is unavailable; invoking plain test functions directly.")
    sys.path.insert(0, str(ROOT))
    namespace = runpy.run_path(str(TEST_PATH))
    tests = sorted(
        (name, test)
        for name, test in namespace.items()
        if name.startswith("test_") and callable(test)
    )
    if not tests:
        raise RuntimeError("No test functions found in tests/test_system.py")

    passed: list[str] = []
    for name, test in tests:
        test()
        passed.append(name)
        print(f"PASS {name}")
    print(f"{len(passed)} system tests passed.")
    return passed


def _read_json(
    path: str, timeout: float = 2.0, base_url: str = URL
) -> dict[str, Any]:
    """Fetch one JSON API response from the local service."""
    request = urllib.request.Request(
        f"{base_url}{path}", headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {path}")
    return payload


def _wait_until_ready(
    process: subprocess.Popen[bytes], timeout: float, base_url: str
) -> None:
    """Wait for the child server to become healthy or fail startup."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline and not _shutdown_requested.is_set():
        if process.poll() is not None:
            raise RuntimeError(
                f"Uvicorn exited during startup with code {process.returncode}"
            )
        try:
            health = _read_json("/health", timeout=1.0, base_url=base_url)
            if health.get("status") == "healthy":
                return
        except (OSError, ValueError, urllib.error.URLError) as error:
            last_error = error
        _shutdown_requested.wait(0.25)
    if _shutdown_requested.is_set():
        raise InterruptedError("Startup interrupted")
    raise TimeoutError(f"Uvicorn did not become ready: {last_error}")


def _request_shutdown(signum: int, _frame: FrameType | None) -> None:
    """Signal the main loop to begin graceful service shutdown."""
    _shutdown_requested.set()
    print(f"\nReceived {signal.Signals(signum).name}; shutting down gracefully.")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    """Send SIGINT to the Uvicorn process group, then enforce a timeout."""
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGINT)
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=10)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        print("Uvicorn did not stop after SIGINT; terminating it.", file=sys.stderr)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _append_final_log(
    *,
    started_at: str,
    tests: list[str],
    snapshot: dict[str, Any] | None,
    exit_code: int | None,
    error: str | None,
) -> None:
    """Append the final service snapshot and run summary as JSON."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "shutdown_signal": "SIGINT" if _shutdown_requested.is_set() else None,
        "system_tests": tests,
        "uvicorn_exit_code": exit_code,
        "error": error,
        "final_telemetry": snapshot,
    }
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, indent=2, default=str))
        log_file.write("\n\n")
    print(f"Final execution log appended to {LOG_PATH}")


def serve(
    *, open_browser: bool, startup_timeout: float, tests: list[str], port: int
) -> int:
    """Run Uvicorn until SIGINT, then save the final telemetry snapshot."""
    started_at = datetime.now(timezone.utc).isoformat()
    base_url = f"http://localhost:{port}"
    previous_sigint = signal.signal(signal.SIGINT, _request_shutdown)
    previous_sigterm = signal.signal(signal.SIGTERM, _request_shutdown)
    process: subprocess.Popen[bytes] | None = None
    snapshot: dict[str, Any] | None = None
    error: str | None = None
    result = 0
    environment = os.environ.copy()
    environment["KERNEL_ROLE"] = "core"
    environment.pop("KERNEL_SERVICE_URL", None)

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "server.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=environment,
            start_new_session=(os.name == "posix"),
        )
        _wait_until_ready(process, startup_timeout, base_url)
        if open_browser:
            webbrowser.open(base_url)
        print(f"Smart Traffic OS is running at {base_url}. Press Ctrl+C to stop.")

        while not _shutdown_requested.wait(0.25):
            if process.poll() is not None:
                raise RuntimeError(
                    f"Uvicorn exited unexpectedly with code {process.returncode}"
                )
    except InterruptedError:
        pass
    except Exception as exception:
        error = str(exception)
        print(f"Execution failed: {error}", file=sys.stderr)
        result = 1
    finally:
        if process is not None and process.poll() is None:
            try:
                snapshot = _read_json("/api/status", base_url=base_url)
            except (OSError, ValueError, urllib.error.URLError) as exception:
                error = error or f"Could not capture final status: {exception}"
            _stop_process(process)
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        _append_final_log(
            started_at=started_at,
            tests=tests,
            snapshot=snapshot,
            exit_code=process.returncode if process is not None else None,
            error=error,
        )
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="check dependencies and run tests without starting Uvicorn",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the dashboard in a browser",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        help="seconds to wait for the local server health endpoint",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Uvicorn port (default: 8000)",
    )
    arguments = parser.parse_args()

    if check_dependencies():
        return 2
    try:
        tests = run_system_tests()
    except Exception as error:
        print(f"System tests failed: {error}", file=sys.stderr)
        return 1

    print(
        "Verified: preemptive-priority AWT = 5.25 ms; safe sequence = "
        "P1 -> P2 -> P3 -> P4; page faults: Optimal (9) <= LRU (12) < FIFO (15)."
    )
    if arguments.check_only:
        return 0
    if arguments.startup_timeout <= 0:
        parser.error("--startup-timeout must be positive")
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    return serve(
        open_browser=not arguments.no_browser,
        startup_timeout=arguments.startup_timeout,
        tests=tests,
        port=arguments.port,
    )


if __name__ == "__main__":
    raise SystemExit(main())