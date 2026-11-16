"""Build the Group 02 OS PBL submission archive with an audit table."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
ARCHIVE_NAME = "Group_02_OS_PBL_Final_Submission.zip"
ARCHIVE_PATH = ROOT / ARCHIVE_NAME

SOURCE_DIRECTORIES = (
    "core",
    "scheduling",
    "concurrency",
    "memory",
    "telemetry",
    "tests",
)
REQUIRED_FILES = (
    "output/traffic_gantt_chart.png",
    "output/memory_benchmark_chart.png",
    "FINAL_PBL_REPORT_REVIEW_3.md",
    "VIVA_DEFENSE_CHEATSHEET.md",
    "README.md",
    "OS_PBL_Final_Presentation.pptx",
)
OPTIONAL_DIRECTORIES = ("logs",)
OPTIONAL_FILES = (
    "run_master.py",
    "app_dashboard.py",
    "generate_final_report.py",
    "generate_viva_cards.py",
    "generate_presentation_deck.py",
    "deploy_containers.py",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore",
    "record_demo.sh",
    ".github/workflows/os_pbl_ci.yml",
    "package_submission.py",
)
EXCLUDED_DIRECTORY_NAMES = {"__pycache__", ".pytest_cache", ".git"}
EXCLUDED_FILE_NAMES = {".DS_Store"}
EXCLUDED_PATTERNS = (
    "*.tmp",
    "*.temp",
    "*.swp",
    "*.swo",
    "*.pyc",
    "*.bak",
    "*.orig",
    "*.rej",
    "*.part",
    "*.crdownload",
    ".#*",
    "*~",
)


def main() -> None:
    """Create the archive and print its contents with SHA256 checksums."""
    files = collect_files()
    if ARCHIVE_PATH.exists():
        ARCHIVE_PATH.unlink()

    with ZipFile(ARCHIVE_PATH, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, arcname=path.relative_to(ROOT).as_posix())

    print(f"Created: {ARCHIVE_PATH}")
    print(f"Files:   {len(files)}")
    print()
    print(f"{'Bundled file':<62} {'Bytes':>12}  SHA256")
    print("-" * 145)
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        print(f"{relative:<62} {path.stat().st_size:>12}  {_sha256(path)}")
    print("-" * 145)
    print(f"Archive bytes: {ARCHIVE_PATH.stat().st_size}")


def collect_files() -> list[Path]:
    """Collect required and available optional files deterministically."""
    files: set[Path] = set()
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        missing_list = ", ".join(missing)
        raise FileNotFoundError(f"Required submission artifacts are missing: {missing_list}")
    if not (ROOT / "logs").is_dir():
        raise FileNotFoundError("Required submission log directory is missing: logs")

    for directory in SOURCE_DIRECTORIES + OPTIONAL_DIRECTORIES:
        directory_path = ROOT / directory
        if directory_path.is_dir():
            files.update(_iter_clean_files(directory_path))

    for file_name in REQUIRED_FILES + OPTIONAL_FILES:
        path = ROOT / file_name
        if path.is_file() and _is_allowed(path):
            files.add(path)

    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def _iter_clean_files(directory: Path) -> set[Path]:
    files: set[Path] = set()
    for path in directory.rglob("*"):
        if path.is_file() and _is_allowed(path):
            files.add(path)
    return files


def _is_allowed(path: Path) -> bool:
    """Return whether a path is safe for the submission archive."""
    relative_parts = path.relative_to(ROOT).parts
    if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative_parts):
        return False
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    return not any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_PATTERNS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()