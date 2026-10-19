from __future__ import annotations

import hashlib
import io
import json
import logging

import pytest

from backend.api.app import analysis_worker_consumer as worker_cli
from backend.api.app.services.model_bootstrap import (
    ALIGNMENT_EN_CHECKPOINT,
    ALIGNMENT_MMS_CHECKPOINT,
    DEMUCS_HTDEMUCS_CHECKPOINT,
    AssetRole,
    ModelBootstrap,
    ModelBootstrapError,
    approved_destinations,
    bootstrap_from_environment,
    manifest_key_for,
    parse_manifest,
)
from tests.test_aws_cloud_adapters import FakeAwsError


RELEASE = "test-2026.10.1"
BUCKET = "private-test-bucket"

# Synthetic stand-ins only: tiny byte strings, never real model data.
SYNTHETIC_FILES = {
    AssetRole.BTC_SOURCE: [("btc_model.py", b"# synthetic btc source\n")],
    AssetRole.BTC_CHECKPOINT: [("btc_model.pt", b"synthetic-btc-checkpoint")],
    AssetRole.WHISPERX_ASR: [
        ("refs/main", b"0123456789abcdef0123456789abcdef01234567"),
        ("snapshots/0123456789abcdef0123456789abcdef01234567/model.bin", b"asr"),
    ],
    AssetRole.ALIGNMENT_EN: [(ALIGNMENT_EN_CHECKPOINT, b"synthetic-alignment")],
    AssetRole.DEMUCS_HTDEMUCS: [(DEMUCS_HTDEMUCS_CHECKPOINT, b"synthetic-demucs")],
    AssetRole.ALIGNMENT_MMS: [(ALIGNMENT_MMS_CHECKPOINT, b"synthetic-mms")],
}


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.reads: list[str] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == BUCKET
        self.reads.append(Key)
        if Key not in self.objects:
            raise FakeAwsError("NoSuchKey")
        return {"Body": io.BytesIO(self.objects[Key])}


def _environment(tmp_path) -> dict[str, str]:
    return {
        "CHORDSYNC_BTC_SOURCE": str(tmp_path / "models/btc/source"),
        "CHORDSYNC_BTC_CHECKPOINT": str(tmp_path / "models/btc/btc_model.pt"),
        "HF_HOME": str(tmp_path / "cache/huggingface"),
        "TORCH_HOME": str(tmp_path / "cache/torch"),
        "CHORDSYNC_MODEL_RELEASE": RELEASE,
        "CHORDSYNC_MODEL_MANIFEST_KEY": manifest_key_for(RELEASE),
    }


def _manifest(s3: FakeS3, *, license_status="permissive", tamper=None) -> dict:
    assets = []
    for role, files in SYNTHETIC_FILES.items():
        entries = []
        for destination, content in files:
            key = f"models/test/{role.value}/{destination}"
            s3.objects[key] = content
            entries.append(
                {
                    "artifact_key": key,
                    "destination": destination,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            )
        assets.append(
            {
                "asset_name": f"synthetic-{role.value}",
                "role": role.value,
                "required": True,
                "source_project": "chordsync-test-fixture",
                "source_revision": "synthetic",
                "license_status": license_status,
                "files": entries,
            }
        )
    manifest = {"schema_version": 1, "release_id": RELEASE, "assets": assets}
    if tamper:
        tamper(manifest)
    s3.objects[manifest_key_for(RELEASE)] = json.dumps(manifest).encode()
    return manifest


def _bootstrap(tmp_path, s3: FakeS3) -> ModelBootstrap:
    return ModelBootstrap(
        s3,
        BUCKET,
        release_id=RELEASE,
        manifest_key=manifest_key_for(RELEASE),
        destinations=approved_destinations(_environment(tmp_path)),
    )


# --- manifest ---------------------------------------------------------------


def test_valid_manifest_parses_all_required_roles():
    s3 = FakeS3()
    manifest = parse_manifest(
        json.dumps(_manifest(s3)).encode(), expected_release_id=RELEASE
    )
    assert {asset.role for asset in manifest.assets} == set(AssetRole)


def test_manifest_missing_required_asset_is_rejected():
    s3 = FakeS3()
    payload = _manifest(
        s3,
        tamper=lambda m: m["assets"].__setitem__(
            slice(None), [a for a in m["assets"] if a["role"] != "demucs_htdemucs"]
        ),
    )
    with pytest.raises(ModelBootstrapError, match="missing required assets"):
        parse_manifest(json.dumps(payload).encode(), expected_release_id=RELEASE)


@pytest.mark.parametrize(
    "content",
    [b"not json", b"[]", json.dumps({"schema_version": 1}).encode()],
)
def test_malformed_manifest_is_rejected(content):
    with pytest.raises(ModelBootstrapError):
        parse_manifest(content, expected_release_id=RELEASE)


def test_manifest_for_another_release_is_rejected():
    s3 = FakeS3()
    payload = _manifest(s3)
    with pytest.raises(ModelBootstrapError, match="release_id"):
        parse_manifest(json.dumps(payload).encode(), expected_release_id="other")


@pytest.mark.parametrize(
    "destination",
    ["../escape.bin", "/etc/passwd", "a/../../b", "a\\b", "./x", "a//b", ""],
)
def test_unsafe_destination_is_rejected(destination):
    s3 = FakeS3()

    def tamper(manifest):
        manifest["assets"][0]["files"][0]["destination"] = destination

    payload = _manifest(s3, tamper=tamper)
    with pytest.raises(ModelBootstrapError, match="destination"):
        parse_manifest(json.dumps(payload).encode(), expected_release_id=RELEASE)


@pytest.mark.parametrize(
    "key",
    ["jobs/job-one/source/input.mp3", "models/../jobs/x", "models/releases/x/manifest.json"],
)
def test_artifact_key_outside_models_prefix_is_rejected(key):
    s3 = FakeS3()

    def tamper(manifest):
        manifest["assets"][0]["files"][0]["artifact_key"] = key

    payload = _manifest(s3, tamper=tamper)
    with pytest.raises(ModelBootstrapError, match="artifact_key"):
        parse_manifest(json.dumps(payload).encode(), expected_release_id=RELEASE)


def test_fixed_name_role_rejects_other_file_names(tmp_path):
    s3 = FakeS3()

    def tamper(manifest):
        demucs = next(a for a in manifest["assets"] if a["role"] == "demucs_htdemucs")
        demucs["files"][0]["destination"] = "other.th"

    _manifest(s3, tamper=tamper)
    with pytest.raises(ModelBootstrapError, match="approved file"):
        _bootstrap(tmp_path, s3).run()


# --- bootstrap --------------------------------------------------------------


def test_bootstrap_installs_and_verifies_synthetic_assets(tmp_path):
    s3 = FakeS3()
    _manifest(s3)

    report = _bootstrap(tmp_path, s3).run()

    assert report.files_installed == 6  # the on-demand aligner is not fetched
    assert (tmp_path / "models/btc/btc_model.pt").read_bytes() == b"synthetic-btc-checkpoint"
    assert (tmp_path / "models/btc/source/btc_model.py").exists()
    hub = tmp_path / "cache/huggingface/hub/models--Systran--faster-whisper-small"
    assert (hub / "refs/main").exists()
    checkpoints = tmp_path / "cache/torch/hub/checkpoints"
    assert (checkpoints / ALIGNMENT_EN_CHECKPOINT).exists()
    assert (checkpoints / DEMUCS_HTDEMUCS_CHECKPOINT).exists()
    assert not (checkpoints / ALIGNMENT_MMS_CHECKPOINT).exists()
    assert not list(tmp_path.rglob("*.partial"))

    second = _bootstrap(tmp_path, s3).run()
    assert second.files_installed == 0
    assert second.files_already_present == 6


def test_hash_mismatch_fails_and_leaves_no_file(tmp_path):
    s3 = FakeS3()
    _manifest(s3)
    # Same length as the original, so only the hash check can catch it.
    s3.objects["models/test/btc_checkpoint/btc_model.pt"] = b"SYNTHETIC-btc-checkpoint"

    with pytest.raises(ModelBootstrapError, match="SHA-256 mismatch"):
        _bootstrap(tmp_path, s3).run()
    assert not (tmp_path / "models/btc/btc_model.pt").exists()
    assert not list(tmp_path.rglob("*.partial"))


def test_size_mismatch_fails(tmp_path):
    s3 = FakeS3()
    _manifest(s3)
    s3.objects["models/test/btc_checkpoint/btc_model.pt"] += b"extra"

    with pytest.raises(ModelBootstrapError, match="larger than expected"):
        _bootstrap(tmp_path, s3).run()


def test_missing_s3_asset_fails(tmp_path):
    s3 = FakeS3()
    _manifest(s3)
    del s3.objects["models/test/alignment_en/" + ALIGNMENT_EN_CHECKPOINT]

    with pytest.raises(ModelBootstrapError, match="missing"):
        _bootstrap(tmp_path, s3).run()


def test_missing_manifest_fails(tmp_path):
    with pytest.raises(ModelBootstrapError, match="missing"):
        _bootstrap(tmp_path, FakeS3()).run()


def test_required_asset_marked_optional_is_incomplete(tmp_path):
    s3 = FakeS3()
    _manifest(s3, tamper=lambda m: m["assets"][1].update(required=False))

    with pytest.raises(ModelBootstrapError, match="missing required assets"):
        _bootstrap(tmp_path, s3).run()


def test_unresolved_license_is_never_installed(tmp_path):
    s3 = FakeS3()
    _manifest(s3, license_status="unresolved")

    with pytest.raises(ModelBootstrapError, match="unresolved licensing"):
        _bootstrap(tmp_path, s3).run()
    assert not (tmp_path / "models").exists()


def test_bootstrap_requires_release_configuration(tmp_path):
    environment = _environment(tmp_path)
    del environment["CHORDSYNC_MODEL_MANIFEST_KEY"]
    with pytest.raises(ModelBootstrapError, match="required"):
        bootstrap_from_environment(environment, bucket=BUCKET, s3_client=FakeS3())


def test_manifest_key_must_match_release(tmp_path):
    with pytest.raises(ModelBootstrapError, match="manifest key"):
        ModelBootstrap(
            FakeS3(),
            BUCKET,
            release_id=RELEASE,
            manifest_key="models/releases/other/manifest.json",
            destinations=approved_destinations(_environment(tmp_path)),
        )


# --- startup gate -----------------------------------------------------------


def _aws_environment(monkeypatch, tmp_path) -> None:
    for name, value in _environment(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CHORDSYNC_RUNTIME_MODE", "aws")
    monkeypatch.setenv("CHORDSYNC_DISPATCH_MODE", "queue")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    monkeypatch.setenv("CHORDSYNC_S3_BUCKET", BUCKET)
    monkeypatch.setenv("CHORDSYNC_DYNAMODB_JOB_TABLE", "jobs")
    monkeypatch.setenv("CHORDSYNC_SQS_ANALYSIS_QUEUE_URL", "https://sqs.example/queue")


class RecordingConsumer:
    def __init__(self) -> None:
        self.polled = False

    def process_once(self):
        self.polled = True


def test_consumer_is_never_built_when_bootstrap_fails(monkeypatch, tmp_path, caplog):
    _aws_environment(monkeypatch, tmp_path)
    s3 = FakeS3()
    _manifest(s3)
    s3.objects["models/test/demucs_htdemucs/" + DEMUCS_HTDEMUCS_CHECKPOINT] = b"bad"
    built = []

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exit_info:
        worker_cli.main(
            ["--once"],
            consumer_factory=lambda config: built.append(config),
            s3_client=s3,
        )

    assert exit_info.value.code == worker_cli.BOOTSTRAP_FAILED_EXIT_CODE
    assert built == []
    assert "queue not polled" in caplog.text


def test_consumer_polls_only_after_successful_bootstrap(monkeypatch, tmp_path):
    _aws_environment(monkeypatch, tmp_path)
    s3 = FakeS3()
    _manifest(s3)
    consumer = RecordingConsumer()

    worker_cli.main(["--once"], consumer_factory=lambda config: consumer, s3_client=s3)

    assert consumer.polled
    assert s3.reads[0] == manifest_key_for(RELEASE)


# --- the optional multilingual aligner (release 2026.10.2) -------------------------


def _without_mms(manifest: dict) -> None:
    manifest["assets"] = [
        asset for asset in manifest["assets"] if asset["role"] != "alignment_mms"
    ]


def test_a_release_without_the_multilingual_aligner_is_still_valid():
    s3 = FakeS3()
    manifest = parse_manifest(
        json.dumps(_manifest(s3, tamper=_without_mms)).encode(),
        expected_release_id=RELEASE,
    )

    assert AssetRole.ALIGNMENT_MMS not in {asset.role for asset in manifest.assets}


def test_the_multilingual_aligner_is_fetched_only_on_demand(tmp_path):
    s3 = FakeS3()
    _manifest(s3)
    installed = tmp_path / "cache/torch/hub/checkpoints" / ALIGNMENT_MMS_CHECKPOINT
    mms_key = f"models/test/{AssetRole.ALIGNMENT_MMS.value}/{ALIGNMENT_MMS_CHECKPOINT}"

    _bootstrap(tmp_path, s3).run()
    assert not installed.exists()
    assert mms_key not in s3.reads  # never even read at startup

    report = _bootstrap(tmp_path, s3).install_role(AssetRole.ALIGNMENT_MMS)

    assert installed.read_bytes() == b"synthetic-mms"  # where torchaudio looks
    assert (report.files_installed, report.files_already_present) == (1, 0)


def test_an_on_demand_install_is_not_repeated(tmp_path):
    s3 = FakeS3()
    _manifest(s3)
    bootstrap = _bootstrap(tmp_path, s3)
    bootstrap.install_role(AssetRole.ALIGNMENT_MMS)
    reads = len(s3.reads)

    again = bootstrap.install_role(AssetRole.ALIGNMENT_MMS)

    assert (again.files_installed, again.files_already_present) == (0, 1)
    assert not any("synthetic" in key and key.endswith("model.pt") for key in s3.reads[reads:])


def test_an_on_demand_install_is_verified_like_any_other(tmp_path):
    s3 = FakeS3()
    _manifest(s3)
    s3.objects[f"models/test/{AssetRole.ALIGNMENT_MMS.value}/{ALIGNMENT_MMS_CHECKPOINT}"] = b"tampered"

    with pytest.raises(ModelBootstrapError, match="mismatch"):
        _bootstrap(tmp_path, s3).install_role(AssetRole.ALIGNMENT_MMS)

    installed = tmp_path / "cache/torch/hub/checkpoints" / ALIGNMENT_MMS_CHECKPOINT
    assert not installed.exists()


def test_a_release_without_the_aligner_cannot_install_it(tmp_path):
    s3 = FakeS3()
    _manifest(s3, tamper=_without_mms)

    with pytest.raises(ModelBootstrapError, match="no alignment_mms asset"):
        _bootstrap(tmp_path, s3).install_role(AssetRole.ALIGNMENT_MMS)


def test_other_required_assets_are_still_required():
    s3 = FakeS3()

    def drop_asr(manifest):
        manifest["assets"] = [
            a for a in manifest["assets"] if a["role"] != "whisperx_asr"
        ]

    with pytest.raises(ModelBootstrapError):
        parse_manifest(
            json.dumps(_manifest(s3, tamper=drop_asr)).encode(),
            expected_release_id=RELEASE,
        )


# --- the worker's on-demand installer ------------------------------------------------


def test_the_on_demand_installer_fetches_the_aligner_from_the_private_bucket(
    tmp_path, monkeypatch
):
    from backend.api.app.services.cloud_runtime import CloudRuntimeConfig, RuntimeMode

    s3 = FakeS3()
    _manifest(s3)
    for name, value in _environment(tmp_path).items():
        monkeypatch.setenv(name, value)
    config = CloudRuntimeConfig(
        mode=RuntimeMode.AWS,
        storage_root=tmp_path,
        aws_region="ap-southeast-1",
        s3_bucket=BUCKET,
    )

    install = worker_cli.on_demand_model_installer(config, s3_client=s3)
    install(AssetRole.ALIGNMENT_MMS)

    installed = tmp_path / "cache/torch/hub/checkpoints" / ALIGNMENT_MMS_CHECKPOINT
    assert installed.read_bytes() == b"synthetic-mms"


def test_there_is_no_installer_outside_aws(tmp_path):
    from backend.api.app.services.cloud_runtime import CloudRuntimeConfig, RuntimeMode

    config = CloudRuntimeConfig(mode=RuntimeMode.LOCAL, storage_root=tmp_path)

    assert worker_cli.on_demand_model_installer(config) is None
