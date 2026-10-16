"""Build the worker dispatcher Lambda zip (pure Python; boto3 comes from the runtime).

    python scripts/build_dispatcher_package.py [output.zip]

The zip holds ``backend/__init__.py`` and ``backend/dispatcher/*.py`` only, with
fixed timestamps so the same source always produces the same bytes.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build/dispatcher/chordsync-dispatcher.zip"
_FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def package_files() -> list[Path]:
    files = [ROOT / "backend/__init__.py"]
    files += sorted((ROOT / "backend/dispatcher").glob("*.py"))
    return files


def build(output: Path = DEFAULT_OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in package_files():
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), _FIXED_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return output


if __name__ == "__main__":
    target = build(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT)
    print(f"{target} ({target.stat().st_size} bytes)")
