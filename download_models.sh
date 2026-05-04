#!/bin/bash
#
# Download models: Qwen ASR, Kokoro TTS, and Gemma SLM
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="${SCRIPT_DIR}/models"
ASR_MODEL_PATH="${BASE_DIR}/Qwen3-ASR-0.6B"
ASR_FILENAME="Qwen3-ASR-0.6B"

# Model repositories
ASR_MODEL="Qwen/Qwen3-ASR-0.6B"

# SLM (Small Language Model) Configuration
SLM_DIR="${BASE_DIR}/gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf"
SLM_MODEL="moe249/google_gemma-4-E4B-it-tictactoe"

# Kokoro TTS Configuration
KOKORO_MODEL="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx"
KOKORO_VOICES="https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin"
KOKORO_DIR="${BASE_DIR}"
KOKORO_MODEL_FILE="${KOKORO_DIR}/kokoro-v1.0.onnx"
KOKORO_VOICES_FILE="${KOKORO_DIR}/voices-v1.0.bin"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependency() {
    local cmd="$1"
    local name="$2"
    
    if ! command -v "$cmd" &> /dev/null; then
        log_error "$name (command: $cmd) is not installed."
        log_error "Please install it first and try again."
        exit 1
    fi
}

verify_huggingface_cli() {
    if ! hf version &> /dev/null; then
        log_error "hf is not properly installed or configured."
        log_error "Please install it with: uv pip install hf"
        exit 1
    fi
}

ensure_directories() {
    log_info "Creating model directories..."
    
    if ! mkdir -p "$ASR_MODEL_PATH"; then
        log_error "Failed to create directory: $ASR_MODEL_PATH"
        exit 1
    fi
    
    log_info "Directories created successfully."
}

download_model() {
    local model_name="$1"
    local local_dir="$2"
    local output_dir="$3"
    
    log_info "Starting download of $model_name..."
    log_info "Downloading to: $local_dir"
    
    # Check if directory already exists and has content
    if [ -d "$local_dir" ] && [ "$(ls -A "$local_dir" 2>/dev/null)" ]; then
        log_warn "Directory already exists with content: $local_dir"
        read -p "Do you want to skip this download? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping download for $model_name"
            return 0
        fi
    fi
    
    # Download the model
    if ! hf download "$model_name" --local-dir "$local_dir" 2>&1 | tee /dev/tty; then
        log_error "Failed to download $model_name"
        return 1
    fi
    
    # Verify download was successful
    if [ -d "$local_dir" ] && [ "$(ls -A "$local_dir" 2>/dev/null)" ]; then
        log_info "Successfully downloaded $model_name"
        return 0
    else
        log_error "Download verification failed for $model_name"
        return 1
    fi
}

download_kokoro() {
    local url="$1"
    local filename="$2"
    local local_path="${KOKORO_DIR}/${filename}"
    
    log_info "Downloading Kokoro $filename..."
    
    # Check if file already exists
    if [ -f "$local_path" ]; then
        local size_mb
        size_mb=$(du -m "$local_path" 2>/dev/null | cut -f1)
        log_warn "Kokoro $filename already exists (${size_mb}MB)"
        read -p "Do you want to re-download? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "$local_path"
        else
            log_info "Skipping Kokoro $filename"
            return 0
        fi
    fi
    
    # Download the file
    if ! wget -q --show-progress -O "$local_path" "$url" 2>&1 | tee /dev/tty; then
        log_error "Failed to download $filename from $url"
        return 1
    fi
    
    # Verify download
    if [ -f "$local_path" ]; then
        local size_mb
        size_mb=$(du -m "$local_path" 2>/dev/null | cut -f1)
        log_info "✓ Kokoro $filename downloaded (${size_mb}MB)"
        return 0
    else
        log_error "Kokoro $filename verification failed!"
        return 1
    fi
}

verify_downloads() {
    log_info "Verifying downloaded models..."
    
    local all_verified=true
    
    # Verify ASR model
    if [ -d "$ASR_MODEL_PATH" ] && [ "$(ls -A "$ASR_MODEL_PATH" 2>/dev/null)" ]; then
        log_info "ASR model directory ($ASR_MODEL_PATH) contains:"
        ls -la "$ASR_MODEL_PATH"
        log_info "✓ ASR model verified successfully"
    else
        log_error "ASR model verification failed!"
        all_verified=false
    fi
    
    # Verify SLM model
    SLM_FILE="${BASE_DIR}/gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf"
    if [ -f "$SLM_FILE" ]; then
        local size_mb
        size_mb=$(du -m "$SLM_FILE" 2>/dev/null | cut -f1)
        log_info "SLM model verified: $SLM_FILE (${size_mb}MB)"
        log_info "✓ SLM model verified successfully"
    else
        log_warn "SLM model not found at $SLM_FILE (may need manual download)"
    fi
    
    # Verify Kokoro models
    if [ -f "$KOKORO_MODEL_FILE" ] && [ -f "$KOKORO_VOICES_FILE" ]; then
        local model_size_mb voices_size_mb
        model_size_mb=$(du -m "$KOKORO_MODEL_FILE" 2>/dev/null | cut -f1)
        voices_size_mb=$(du -m "$KOKORO_VOICES_FILE" 2>/dev/null | cut -f1)
        log_info "Kokoro TTS models verified: kokoro-v1.0.onnx (${model_size_mb}MB), voices-v1.0.bin (${voices_size_mb}MB)"
        log_info "✓ Kokoro TTS models verified successfully"
    else
        log_warn "Kokoro TTS models not found (may need manual download from GitHub releases)"
    fi
    
    if [ "$all_verified" = "true" ]; then
        return 0
    else
        return 1
    fi
}

main() {
    log_info "=========================================="
    log_info "Tic-Tac-Toe Models Downloader"
    log_info "=========================================="
    
    # Check dependencies
    check_dependency "hf" "hf CLI"
    verify_huggingface_cli
    
    # Ensure directories
    ensure_directories
    
    # Download models
    log_info ""
    log_info "Starting model downloads..."
    log_info ""
    
    download_model "$ASR_MODEL" "$ASR_MODEL_PATH" "$ASR_MODEL_PATH"
    ASR_STATUS=$?
    
    # Download SLM model
    log_info ""
    log_info "Downloading SLM model..."
    log_info ""
    
    # Check if file already exists
    if [ -f "$SLM_DIR" ]; then
        log_warn "SLM model already exists: $SLM_DIR"
        read -p "Do you want to skip this download? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping SLM download"
        else
            log_info "Downloading $SLM_MODEL..."
            if ! hf download "$SLM_MODEL" --include "gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf" --local-dir "$BASE_DIR" 2>&1 | tee /dev/tty; then
                log_error "Failed to download SLM model"
            else
                log_info "✓ SLM model download completed"
            fi
        fi
    else
        log_info "Downloading $SLM_MODEL..."
        if ! hf download "$SLM_MODEL" --include "gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf" --local-dir "$BASE_DIR" 2>&1 | tee /dev/tty; then
            log_error "Failed to download SLM model"
        else
            log_info "✓ SLM model download completed"
        fi
    fi
    
    # Download Kokoro TTS models
    log_info ""
    log_info "Downloading Kokoro TTS models..."
    log_info ""
    
    download_kokoro "$KOKORO_MODEL" "$(basename "$KOKORO_MODEL")"
    KOKORO_STATUS=$?
    
    download_kokoro "$KOKORO_VOICES" "$(basename "$KOKORO_VOICES")"
    KOKORO_VOICES_STATUS=$?
    
    # Verify downloads
    verify_downloads
    VERIFY_STATUS=$?
    
    # Summary
    log_info ""
    log_info "=========================================="
    log_info "Download Summary"
    log_info "=========================================="
    
    if [ $ASR_STATUS -eq 0 ]; then
        log_info "✓ ASR model download completed"
    else
        log_error "✗ ASR model download failed"
    fi
    
    if [ $KOKORO_STATUS -eq 0 ]; then
        log_info "✓ Kokoro TTS model download completed"
    else
        log_error "✗ Kokoro TTS model download failed"
    fi
    
    if [ $KOKORO_VOICES_STATUS -eq 0 ]; then
        log_info "✓ Kokoro voices download completed"
    else
        log_error "✗ Kokoro voices download failed"
    fi
    
    if [ $VERIFY_STATUS -eq 0 ]; then
        log_info "✓ All verifications passed"
        log_info ""
        log_info "Models are ready to use!"
        exit 0
    else
        log_error "✗ Some verifications failed"
        exit 1
    fi
}

# Run main function
main "$@"
