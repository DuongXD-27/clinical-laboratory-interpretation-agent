"""Fail verification when clearly generated artifacts are tracked by Git."""

from __future__ import annotations

import subprocess
from pathlib import PurePosixPath

FORBIDDEN_DIRECTORY_NAMES = {
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}


def is_forbidden(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    return (
        any(part in FORBIDDEN_DIRECTORY_NAMES for part in parts)
        or normalized.startswith("eval/raw/pytest_tmp_")
        or normalized.endswith((".log", ".pyc", ".pyo"))
    )


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    )
    offenders = sorted(path for path in result.stdout.split("\0") if path and is_forbidden(path))
    if offenders:
        print("Tracked generated artifacts are forbidden:")
        for path in offenders:
            print(f"- {path}")
        return 1
    print("Tracked generated artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
