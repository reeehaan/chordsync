#!/bin/bash
# Prove the worker image's lyrics stage (WhisperX transcription + alignment)
# runs fully offline, and that a missing NLTK resource cannot trigger a
# network download. Uses synthetic macOS text-to-speech, never a song.
#
# Usage: scripts/worker_offline_lyrics_smoke.sh <image>
# Requires locally cached faster-whisper-small and wav2vec2 checkpoints
# (the same files staged in model release 2026.10.1), mounted read-only.
set -euo pipefail

IMAGE="${1:?usage: $0 <image>}"
HF_MODEL="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-small"
TORCH_CHECKPOINTS="$HOME/.cache/torch/hub/checkpoints"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say -o "$WORK/speech.aiff" "This is a synthetic recording for an offline test. \
The lyrics stage must align every word without the internet. \
Each sentence is split by the punkt tokenizer."
ffmpeg -loglevel error -y -i "$WORK/speech.aiff" -ac 1 -ar 16000 "$WORK/speech.wav"

# Runs WhisperX exactly as the lyrics stage does, inside the processor's
# offline stage environment.
STAGE='
import json, os, subprocess, sys
from backend.api.app.services.real_analysis_processor import offline_stage_environment
command = [os.environ["CHORDSYNC_WHISPERX_EXECUTABLE"], "/in/speech.wav", "--model", "small",
           "--device", "cpu", "--compute_type", "int8", "--output_dir", "/tmp/out",
           "--output_format", "json", "--verbose", "False"]
done = subprocess.run(command, env=offline_stage_environment(os.environ),
                      capture_output=True, text=True, timeout=900)
print("exit", done.returncode)
if done.returncode:
    print(done.stderr[-1500:]); sys.exit(done.returncode)
result = json.load(open("/tmp/out/speech.json"))
words = [w for s in result["segments"] for w in s.get("words", [])]
timed = [w for w in words if "start" in w and "end" in w]
print("language", result.get("language"), "| segments", len(result["segments"]),
      "| words", len(words), "| timed words", len(timed))
assert result["segments"] and timed, "alignment produced no word timings"
'

run_stage() {
  docker run --rm --platform linux/arm64 "$@" \
    -v "$WORK:/in:ro" \
    -v "$HF_MODEL:/opt/chordsync/cache/huggingface/hub/models--Systran--faster-whisper-small:ro" \
    -v "$TORCH_CHECKPOINTS:/opt/chordsync/cache/torch/hub/checkpoints:ro" \
    "$IMAGE" python -c "$STAGE"
}

echo "== 1. Network disabled: transcription + alignment must succeed"
run_stage --network none

echo "== 2. Network available, punkt_tab hidden: must fail without downloading"
# 2a. The stage fails instead of silently fetching the missing resource.
if output="$(run_stage -e NLTK_DATA=/nonexistent -e HOME=/tmp \
      --mount type=tmpfs,destination=/opt/chordsync/share/nltk_data 2>&1)"; then
  echo "$output"; echo "FAIL: stage succeeded without punkt_tab"; exit 1
fi
echo "$output" | grep -q "Resource 'punkt_tab' not found" \
  || { echo "$output" | tail -20; echo "FAIL: unexpected stage error"; exit 1; }
echo "PASS: stage failed closed on the missing resource"

# 2b. WhisperX calls nltk.download(quiet=True), which hides why it failed.
# Run the same download with errors surfaced, in the same offline environment.
PROBE='
import os, subprocess, sys
from backend.api.app.services.real_analysis_processor import offline_stage_environment
code = "import nltk\ntry:\n    nltk.download(\"punkt_tab\", download_dir=\"/tmp/nd\", raise_on_error=True)\n    print(\"DOWNLOADED\")\nexcept Exception as error:\n    print(error)\n"
out = subprocess.run(["/opt/chordsync/venvs/whisperx/bin/python", "-c", code],
                     env=offline_stage_environment(os.environ), capture_output=True, text=True)
print(out.stdout.strip()[:200])
sys.exit(0 if "Security Violation [pathsec.urlopen]: refusing a proxied fetch" in out.stdout else 1)
'
if docker run --rm --platform linux/arm64 -e HOME=/tmp "$IMAGE" python -c "$PROBE"; then
  echo "PASS: NLTK refused the download before connecting"
else
  echo "FAIL: NLTK download was not refused"; exit 1
fi
