#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="${ROOT}/models"
ASR_DIR="${MODEL_DIR}/Qwen3-ASR-0.6B"
mkdir -p "${ASR_DIR}"
command -v hf >/dev/null || { echo "Install hf before downloading ASR" >&2; exit 1; }
hf download Qwen/Qwen3-ASR-0.6B --local-dir "${ASR_DIR}"
test -s "${ASR_DIR}/config.json" || {
  echo "ASR model is missing config.json" >&2
  exit 1
}
test -n "$(find "${ASR_DIR}" -maxdepth 1 -type f -name '*.safetensors' -size +0c -print -quit)" || {
  echo "ASR model is missing safetensors weights" >&2
  exit 1
}
curl --fail --location --output "${MODEL_DIR}/kokoro-v1.0.onnx" \
  https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx
curl --fail --location --output "${MODEL_DIR}/voices-v1.0.bin" \
  https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin
test -s "${MODEL_DIR}/kokoro-v1.0.onnx"
test -s "${MODEL_DIR}/voices-v1.0.bin"
echo "ASR and TTS models downloaded and verified."
