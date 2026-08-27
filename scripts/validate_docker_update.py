"""Validate a managed-Docker update artifact without installing it."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.docker_launcher.contracts import (  # noqa: E402
    DOCKER_ASSET_RE,
    safe_extract_package,
    validate_package_tree,
)

FORBIDDEN_PARTS = {
    ".git", ".codex", ".claude", "data", "tests", "node_modules",
    "frontend-v2", "test-results", "playwright-report",
}


def validate_archive(archive: Path, expected_version: str | None = None) -> dict:
    match = DOCKER_ASSET_RE.fullmatch(archive.name)
    if not match:
        raise ValueError(f"invalid Docker update asset name: {archive.name}")
    filename_version = match.group("version")
    if expected_version and filename_version != expected_version.strip().lstrip("vV"):
        raise ValueError("Docker update filename version does not match the build version")
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            parts = set(Path(name.replace("\\", "/")).parts)
            if parts & FORBIDDEN_PARTS or Path(name).name.startswith(".env"):
                raise ValueError(f"Docker update contains forbidden content: {name}")

    temporary = Path(tempfile.mkdtemp(prefix="diceframe-docker-validate-"))
    try:
        package_root = safe_extract_package(archive, temporary)
        if package_root.name != archive.stem:
            raise ValueError("Docker update top-level directory must match the asset name")
        return validate_package_tree(package_root, expected_version=filename_version)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    manifest = validate_archive(args.archive.resolve(), args.version)
    print(
        f"valid Docker update: version={manifest['version']} "
        f"platform={manifest['platform']} runtime_api={manifest['runtime_api']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
