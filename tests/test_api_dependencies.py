"""Guards on the API image's dependency surface (S7-T02A, S7-T02B).

The internet-facing API must stay light: no media codec stack, no ML packages,
digest-pinned images, and nothing that the ML worker would silently inherit.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_DOCKERFILE = ROOT / "backend/api/Dockerfile"
WORKER_DOCKERFILE = ROOT / "backend/worker/Dockerfile"
API_REQUIREMENT_FILES = [
    ROOT / "backend/api/requirements.txt",
    ROOT / "backend/api/requirements-runtime.txt",
]
HEAVY_PACKAGES = {
    "torch",
    "torchaudio",
    "torchcodec",
    "numpy",
    "scipy",
    "librosa",
    "whisperx",
    "faster-whisper",
    "ctranslate2",
    "demucs",
    "madmom",
    "pyannote-audio",
    "nltk",
    "soundfile",
    "pydub",
}
# Media inspection is in-house; no third-party media parser (copyleft or not)
# belongs in the API image.
MEDIA_PARSER_PACKAGES = {
    "mutagen",
    "tinytag",
    "eyed3",
    "pymediainfo",
    "pytaglib",
    "audioread",
    "ffmpeg-python",
    "av",
}


def _code_lines(path: Path) -> list[str]:
    """Non-comment, non-blank lines (comments may mention what is absent)."""
    return [
        line
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _pinned(path: Path) -> dict[str, str]:
    pins = {}
    for line in _code_lines(path):
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s\\;]+)", line.strip())
        if match:
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def test_api_dockerfile_installs_no_ffmpeg_or_ffprobe():
    code = "\n".join(_code_lines(API_DOCKERFILE)).casefold()
    assert "ffmpeg" not in code
    assert "ffprobe" not in code
    assert "apt-get install" not in code, "the API image should add no OS packages"


def test_api_dockerfile_pins_every_image_by_digest_and_never_uses_latest():
    code = "\n".join(_code_lines(API_DOCKERFILE))
    from_lines = [line for line in code.splitlines() if line.startswith("FROM ")]
    assert len(from_lines) == 2
    assert all(re.search(r"@sha256:[0-9a-f]{64}", line) for line in from_lines)
    assert ":latest" not in code


def test_api_dockerfile_runs_as_a_fixed_non_root_user():
    code = "\n".join(_code_lines(API_DOCKERFILE))
    assert re.search(r"^USER 10001$", code, re.MULTILINE)


@pytest.mark.parametrize("path", API_REQUIREMENT_FILES, ids=lambda p: p.name)
def test_api_requirements_contain_no_ml_or_media_codec_packages(path):
    assert HEAVY_PACKAGES.isdisjoint(_pinned(path))


@pytest.mark.parametrize("path", API_REQUIREMENT_FILES, ids=lambda p: p.name)
def test_api_requirements_have_no_third_party_media_parser(path):
    assert MEDIA_PARSER_PACKAGES.isdisjoint(_pinned(path))


def test_the_separate_media_requirements_file_is_gone():
    assert not (ROOT / "backend/api/requirements-media.txt").exists()
    assert "requirements-media" not in API_DOCKERFILE.read_text()


def test_api_image_installs_without_hash_mode_extras():
    code = "\n".join(_code_lines(API_DOCKERFILE))
    assert "--no-deps" not in code and "--require-hashes" not in code


def test_media_inspection_modules_import_only_the_standard_library():
    allowed = {"backend", "__future__"}
    stdlib = set(sys.stdlib_module_names)
    for name in ("media_inspection", "mpeg_audio", "mp4_audio", "media_errors"):
        tree = ast.parse((ROOT / f"backend/api/app/services/{name}.py").read_text())
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                top = module.split(".")[0]
                assert top in stdlib or top in allowed, f"{name} imports {module}"


def test_api_code_never_invokes_ffmpeg_or_ffprobe():
    offenders = []
    for path in (ROOT / "backend/api/app").rglob("*.py"):
        if path.name == "media_inspection.py":  # explains why they are absent
            continue
        text = path.read_text().casefold()
        if "ffprobe" in text or "ffmpeg" in text:
            offenders.append(path.name)
    assert offenders == []


def _run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    # -I ignores PYTHONPATH and the working directory, so add the repo explicitly.
    return subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r})\n{code}"],
        cwd=ROOT,
        env={"PATH": ""},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_importing_the_api_loads_no_media_tooling_and_builds_no_pipeline():
    result = _run_isolated(
        "import sys\n"
        "import backend.api.app.main\n"
        "assert 'analysis.preprocessing.audio_preprocessor' not in sys.modules\n"
        "for heavy in ('torch', 'numpy', 'librosa', 'whisperx', 'demucs', 'madmom'):\n"
        "    assert heavy not in sys.modules, heavy\n"
    )
    assert result.returncode == 0, result.stderr


def test_media_inspection_runs_with_every_third_party_media_package_blocked():
    result = _run_isolated(
        "import sys\n"
        "for name in ('mutagen', 'numpy', 'librosa', 'soundfile', 'pydub'):\n"
        "    sys.modules[name] = None  # makes `import <name>` fail\n"
        "import backend.api.app.analysis_worker_consumer\n"
        "import backend.api.app.services.analysis_input_storage\n"
        "import backend.api.app.services.cloud_runtime\n"
        "import backend.api.app.services.media_inspection\n"
    )
    assert result.returncode == 0, result.stderr
