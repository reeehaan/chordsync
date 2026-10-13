from __future__ import annotations

import subprocess
import sys

from backend.api.app.services.real_analysis_processor import (
    BLACKHOLE_PROXY,
    AnalysisPipelineConfig,
    LocalSubprocessRunner,
    RealAnalysisProcessor,
    offline_stage_environment,
)

_FETCH = (
    "import urllib.request, sys\n"
    "try:\n"
    "    urllib.request.urlopen('http://example.com/', timeout=5)\n"
    "except Exception as error:\n"
    "    print(type(error).__name__, getattr(error, 'reason', error))\n"
    "    sys.exit(3)\n"
    "sys.exit(0)\n"
)


def test_offline_environment_routes_every_proxy_to_loopback_blackhole():
    environment = offline_stage_environment(
        {
            "PATH": "/usr/bin",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "NLTK_ALLOW_PROXIED_URLOPEN": "1",
            "HF_HUB_OFFLINE": "0",
        }
    )

    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        assert environment[name] == BLACKHOLE_PROXY
        assert environment[name.lower()] == BLACKHOLE_PROXY
    assert "NO_PROXY" not in environment and "no_proxy" not in environment
    assert "NLTK_ALLOW_PROXIED_URLOPEN" not in environment
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["PATH"] == "/usr/bin"


def test_offline_environment_does_not_mutate_the_worker_environment():
    base = {"PATH": "/usr/bin"}
    offline_stage_environment(base)
    assert base == {"PATH": "/usr/bin"}


def test_http_fallback_in_a_stage_subprocess_fails_without_leaving_the_host():
    environment = offline_stage_environment({"PATH": "/usr/bin:/bin"})

    completed = subprocess.run(
        [sys.executable, "-I", "-c", _FETCH],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 3, completed.stdout + completed.stderr
    assert "URLError" in completed.stdout
    assert "refused" in completed.stdout.casefold()


def test_runner_passes_the_offline_environment_to_subprocesses():
    runner = LocalSubprocessRunner(offline_stage_environment({"PATH": "/usr/bin:/bin"}))

    result = runner.run(
        [sys.executable, "-I", "-c", "import os; print(os.environ['HTTPS_PROXY'])"],
        cwd=__import__("pathlib").Path("."),
        timeout=30,
    )

    assert result.stdout.strip() == BLACKHOLE_PROXY


def test_stage_network_flag_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("CHORDSYNC_STAGE_NETWORK", "disabled")
    assert AnalysisPipelineConfig.local().stage_network_disabled is True

    monkeypatch.setenv("CHORDSYNC_STAGE_NETWORK", "enabled")
    assert AnalysisPipelineConfig.local().stage_network_disabled is False

    monkeypatch.delenv("CHORDSYNC_STAGE_NETWORK")
    assert AnalysisPipelineConfig.local().stage_network_disabled is False


def test_processor_uses_offline_runner_only_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTPS_PROXY", "http://corporate-proxy.invalid:3128")
    monkeypatch.setenv("CHORDSYNC_STAGE_NETWORK", "disabled")
    guarded = RealAnalysisProcessor(AnalysisPipelineConfig.local())
    assert guarded._runner._environment["HTTPS_PROXY"] == BLACKHOLE_PROXY

    monkeypatch.delenv("CHORDSYNC_STAGE_NETWORK")
    unguarded = RealAnalysisProcessor(AnalysisPipelineConfig.local())
    assert unguarded._runner._environment is None
