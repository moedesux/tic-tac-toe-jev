#!/bin/bash
#
# Voice Tic-Tac-Toe Game Launcher
# Production-ready launcher with server management, health checks, and cleanup
#
# Usage:
#   ./voice_game.sh          # Start all servers and launch game
#   ./voice_game.sh stop     # Stop all running servers
#   ./voice_game.sh status   # Show server status
#   ./voice_game.sh restart  # Restart all servers and launch game
#

set -euo pipefail

# ============================================================================
# Config Reader — reads INI-style config files
# ============================================================================
read_config_value() {
    local file="$1"
    local section="$2"
    local key="$3"
    sed -n "/^\[${section}\]/,/^\[/p" "$file" | grep "^${key}" | head -1 | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr -d '"'
}

# ============================================================================
# Configuration
# ============================================================================
readonly PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly BACKEND_PID_FILE="${PROJECT_DIR}/.backend.pid"
readonly BACKEND_SCRIPT="${PROJECT_DIR}/backend/main.py"
readonly BACKEND_CONF="${PROJECT_DIR}/config/voice.conf"

readonly SLM_PID_FILE="${PROJECT_DIR}/.llama.pid"
readonly RAW_MODEL_PATH="$(read_config_value "$BACKEND_CONF" "slm" "model_path")"
readonly MODEL_PATH="${PROJECT_DIR}/${RAW_MODEL_PATH#./}"

readonly VOICE_SCRIPT="${PROJECT_DIR}/voice_tic_tac_toe.py"
readonly UV_RUN="uv run --with-requirements ${PROJECT_DIR}/requirements.txt"

readonly MAX_WAIT_SECONDS=60
readonly PROGRESS_INTERVAL=5
readonly PREWARM_TIMEOUT=45

# ============================================================================
# Load ports from config
# ============================================================================
readonly BACKEND_PORT="$(read_config_value "$BACKEND_CONF" "backend" "port")"
readonly SLM_PORT="$(read_config_value "$BACKEND_CONF" "slm" "port")"
readonly BACKEND_HEALTH_URL="http://localhost:${BACKEND_PORT}/api/health"
readonly SLM_HEALTH_URL="http://localhost:${SLM_PORT}/v1/models"

# ============================================================================
# Color-coded Output Functions
# ============================================================================
log_info() {
    echo -e "\033[0;34m[INFO]\033[0m $1"
}

log_success() {
    echo -e "\033[0;32m[SUCCESS]\033[0m $1"
}

log_warning() {
    echo -e "\033[1;33m[WARNING]\033[0m $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

# ============================================================================
# Model Pre-warming
# ============================================================================
prewarm_models() {
    local timeout="${PREWARM_TIMEOUT:-45}"
    
    log_info "Pre-warming voice models (ASR + TTS)..."
    echo ""
    
    # Check if TTS is enabled via config
    local tts_enabled=true
    if [ -f "${PROJECT_DIR}/config/voice.conf" ]; then
        local tts_flag
        tts_flag=$(python3 -c "
import configparser, sys
c = configparser.ConfigParser()
c.read('${PROJECT_DIR}/config/voice.conf')
print(c.get('tts', 'tts_enabled', fallback='true').lower())
" 2>/dev/null || echo "true")
        [ "$tts_flag" = "false" ] && tts_enabled=false
    fi
    
    # Pre-warm ASR
    log_info "  [1/2] Pre-warming ASR model..."
    local asr_start=$(date +%s)
    if curl -s -f --max-time "${timeout}" "${BACKEND_HEALTH_URL}/asr" > /dev/null 2>&1; then
        local asr_elapsed=$(( $(date +%s) - asr_start ))
        log_success "  ASR ready (${asr_elapsed}s)"
    else
        local asr_elapsed=$(( $(date +%s) - asr_start ))
        log_warning "  ASR pre-warm timed out or failed (${asr_elapsed}s) — will load on first request"
    fi
    
    # Pre-warm TTS (only if enabled)
    if [ "$tts_enabled" = "true" ]; then
        log_info "  [2/2] Pre-warming TTS model..."
        local tts_start=$(date +%s)
        if curl -s -f --max-time "${timeout}" "${BACKEND_HEALTH_URL}/tts" > /dev/null 2>&1; then
            local tts_elapsed=$(( $(date +%s) - tts_start ))
            log_success "  TTS ready (${tts_elapsed}s)"
        else
            local tts_elapsed=$(( $(date +%s) - tts_start ))
            log_warning "  TTS pre-warm timed out or failed (${tts_elapsed}s) — will load on first request"
        fi
    else
        log_info "  [2/2] TTS disabled — skipping"
    fi
    
    echo ""
}

# ============================================================================
# Server Detection Functions
# ============================================================================
is_port_in_use() {
    local port="$1"
    if command -v lsof &> /dev/null; then
        lsof -i :"${port}" &> /dev/null
    elif command -v ss &> /dev/null; then
        ss -tln | grep -q ":${port} "
    elif command -v netstat &> /dev/null; then
        netstat -tln | grep -q ":${port} "
    else
        # Fallback: try curl
        curl -s -f "http://localhost:${port}" &> /dev/null
    fi
}

is_backend_running() {
    is_port_in_use "${BACKEND_PORT}"
}

is_llama_running() {
    is_port_in_use "${SLM_PORT}"
}

# ============================================================================
# Health Check Functions
# ============================================================================
check_backend_health() {
    curl -s -f "${BACKEND_HEALTH_URL}" > /dev/null 2>&1
}

check_llama_health() {
    curl -s -f "${SLM_HEALTH_URL}" > /dev/null 2>&1
}

wait_for_server() {
    local server_name="$1"
    local health_check_fn="$2"
    local max_wait="$3"
    local elapsed=0
    
    log_info "Waiting for ${server_name} to become healthy (up to ${max_wait}s)..."
    
    while [ "$elapsed" -lt "$max_wait" ]; do
        if $health_check_fn; then
            log_success "${server_name} is healthy!"
            return 0
        fi
        
        sleep 1
        elapsed=$((elapsed + 1))
        
        # Progress indicator every 5 seconds
        if [ "$((elapsed % PROGRESS_INTERVAL))" -eq 0 ]; then
            log_info "Still waiting for ${server_name}... (${elapsed}s/${max_wait}s)"
        fi
    done
    
    log_error "${server_name} failed to become healthy within ${max_wait} seconds"
    return 1
}

# ============================================================================
# Server Start Functions
# ============================================================================
get_existing_pid() {
    local pid_file="$1"
    if [ -f "${pid_file}" ]; then
        local pid
        pid=$(cat "${pid_file}" 2>/dev/null)
        if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
            echo "${pid}"
            return 0
        fi
    fi
    return 1
}

start_backend() {
    # Check if already running
    if is_backend_running; then
        local existing_pid
        if existing_pid=$(get_existing_pid "${BACKEND_PID_FILE}"); then
            log_info "Backend server already running with PID ${existing_pid}"
            return 0
        fi
        log_warning "Backend appears to be running but PID file missing or invalid"
    fi
    
    log_info "Starting backend FastAPI server on port ${BACKEND_PORT}..."
    
    # Verify uvicorn is available
    if ! command -v uvicorn &> /dev/null; then
        log_error "uvicorn not found. Please install: uv pip install uvicorn fastapi"
        return 1
    fi
    
    # Verify backend script exists
    if [ ! -f "${BACKEND_SCRIPT}" ]; then
        log_error "Backend script not found at ${BACKEND_SCRIPT}"
        return 1
    fi
    
    # Ensure we're in the project directory
    cd "${PROJECT_DIR}"
    
    # Read backend host from config (default to 0.0.0.0)
    local backend_host
    backend_host="$(read_config_value "$BACKEND_CONF" "backend" "host")"
    backend_host="${backend_host:-0.0.0.0}"

    # Start the backend server with nohup
    nohup uv run --with fastapi --with uvicorn uvicorn backend.main:app --host "${backend_host}" --port "${BACKEND_PORT}" > "${PROJECT_DIR}/logs/backend.log" 2>&1 &
    local backend_pid=$!
    
    # Save PID
    echo "${backend_pid}" > "${BACKEND_PID_FILE}"
    
    log_success "Backend started with PID ${backend_pid}"
    log_info "Logs available at: ${PROJECT_DIR}/logs/backend.log"
}

start_llama_server() {
    # Check if already running
    if is_llama_running; then
        local existing_pid
        if existing_pid=$(get_existing_pid "${SLM_PID_FILE}"); then
            log_info "LLaMA server already running with PID ${existing_pid}"
            return 0
        fi
        log_warning "LLaMA server appears to be running but PID file missing or invalid"
    fi
    
    log_info "Starting LLaMA server with Gemma4 model on port ${SLM_PORT}..."
    
    # Verify llama-server is available
    if ! command -v llama-server &> /dev/null; then
        log_error "llama-server not found. Please install llama.cpp and build llama-server"
        return 1
    fi
    
    # Verify model file exists
    if [ ! -f "${MODEL_PATH}" ]; then
        log_error "Model file not found at ${MODEL_PATH}"
        log_info "Available models in ${PROJECT_DIR}/models:"
        ls -la "${PROJECT_DIR}/models/" 2>/dev/null || log_info "(directory doesn't exist)"
        return 1
    fi
    
    # Ensure logs directory exists
    mkdir -p "${PROJECT_DIR}/logs"
    
    # Start the LLaMA server with nohup
    nohup llama-server \
        -m "${MODEL_PATH}" \
        --port "${SLM_PORT}" \
        --host 0.0.0.0 \
        --threads 4 \
        --verbose \
        > "${PROJECT_DIR}/logs/llama.log" 2>&1 &
    local llama_pid=$!
    
    # Save PID
    echo "${llama_pid}" > "${SLM_PID_FILE}"
    
    log_success "LLaMA server started with PID ${llama_pid}"
    log_info "Logs available at: ${PROJECT_DIR}/logs/llama.log"
}

# ============================================================================
# Voice Game Launcher
# ============================================================================
launch_voice_game() {
    log_info "Launching Voice Tic-Tac-Toe game..."
    
    # Verify voice script exists
    if [ ! -f "${VOICE_SCRIPT}" ]; then
        log_error "Voice game script not found at ${VOICE_SCRIPT}"
        return 1
    fi
    
    # Run the voice game with all parameters
    cd "${PROJECT_DIR}"
    
    # Check for simulation mode argument
    local simulation_mode=false
    local game_args=()
    
    for arg in "${@:-}"; do
        case "$arg" in
            --simulation)
                simulation_mode=true
                log_info "Running in simulation mode (text-based)"
                ;;
            --debug)
                game_args+=("--debug")
                ;;
            *)
                game_args+=("$arg")
                ;;
        esac
    done
    
    if [ "${simulation_mode}" = false ]; then
        log_info "Running in full audio mode (requires microphone and speaker)"
    fi
    
    # Pre-flight: ensure kokoro_onnx is installed
    if ! python -c "import kokoro_onnx" 2>/dev/null; then
        log_info "kokoro_onnx not found in environment. Installing..."
        uv pip install kokoro_onnx || {
            log_error "Failed to install kokoro_onnx. Voice game may not work."
        }
    fi

    # Build the python command — all defaults come from config.py
    local python_cmd="${UV_RUN} python ${VOICE_SCRIPT}"
    
    # Add any additional arguments
    for arg in "${game_args[@]}"; do
        python_cmd+=" ${arg}"
    done
    
    # Ensure logs directory exists
    mkdir -p "${PROJECT_DIR}/logs"
    
    # Launch the voice game in background with output redirected to log file
    nohup ${python_cmd} >> "${PROJECT_DIR}/logs/voice_game.log" 2>&1 &
    local voice_game_pid=$!
    
    # Save PID to file
    echo "${voice_game_pid}" > "${PROJECT_DIR}/.voice_game.pid"
    
    log_success "Voice game started with PID ${voice_game_pid}"
    log_info "Logs available at: ${PROJECT_DIR}/logs/voice_game.log"
}

# ============================================================================
# Helper Functions for Process Tree Cleanup
# ============================================================================

# Kill all direct child processes of a given PID
kill_children() {
    local parent_pid="$1"
    local children
    children=$(ps --ppid "${parent_pid}" -o pid= 2>/dev/null) || true
    for child_pid in ${children}; do
        kill -9 "${child_pid}" 2>/dev/null || true
    done
}

# Kill ALL processes listening on a given port
kill_port_processes() {
    local port="$1"
    if command -v lsof &> /dev/null && [ -n "${port}" ]; then
        local port_pids
        port_pids=$(lsof -t -i :"${port}" 2>/dev/null) || true
        
        if [ -n "${port_pids}" ]; then
            for port_pid in ${port_pids}; do
                log_info "Killing process on port ${port} (PID ${port_pid})..."
                kill -9 "${port_pid}" 2>/dev/null || true
            done
            return 0
        fi
    fi
    return 1
}

# Wait for a PID to die. Returns 0 if dead, 1 if still alive.
wait_for_death() {
    local pid="$1"
    local max_wait="${2:-5}"
    local wait_count=0
    while kill -0 "${pid}" 2>/dev/null && [ "$wait_count" -lt "$max_wait" ]; do
        sleep 1
        wait_count=$((wait_count + 1))
    done
    if kill -0 "${pid}" 2>/dev/null; then
        return 1
    fi
    return 0
}

# ============================================================================
# Server Stop Functions
# ============================================================================
stop_server() {
    local server_name="$1"
    local pid_file="$2"
    local port="$3"
    
    local stopped=false
    
    # Method 1: Try to stop via PID file
    if [ -f "${pid_file}" ]; then
        local pid
        pid=$(cat "${pid_file}" 2>/dev/null)
        
        if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
            log_info "Stopping ${server_name} via PID file (PID ${pid})..."
            kill -9 "${pid}" 2>/dev/null || true
            
            # Also kill all child processes (uv run spawns children)
            kill_children "${pid}"
            
            if wait_for_death "${pid}"; then
                log_success "${server_name} stopped"
                stopped=true
            else
                log_warning "${server_name} main process (PID ${pid}) may still be running"
            fi
        fi
        
        rm -f "${pid_file}"
    fi
    
    # Method 2: Try to find and kill ALL processes via port
    if [ "${stopped}" = false ]; then
        if kill_port_processes "${port}"; then
            log_info "Waiting for port ${port} to be released..."
            sleep 2
            
            if ! is_port_in_use "${port}"; then
                log_success "${server_name} stopped (via port ${port})"
                stopped=true
            else
                log_warning "${server_name} may still be holding port ${port}"
            fi
        fi
    fi
    
    if [ "${stopped}" = false ]; then
        log_info "${server_name} was not running"
    fi
}

stop_all_servers() {
    log_info "Stopping all servers..."
    
    stop_server "Backend" "${BACKEND_PID_FILE}" "${BACKEND_PORT}" || true
    stop_server "LLaMA" "${SLM_PID_FILE}" "${SLM_PORT}" || true
    stop_server "Voice Game" "${PROJECT_DIR}/.voice_game.pid" "" || true
    
    log_success "All servers stopped"
}

cleanup_pid_files() {
    rm -f "${BACKEND_PID_FILE}" "${SLM_PID_FILE}" "${PROJECT_DIR}/.voice_game.pid"
    log_info "Cleaned up PID files"
}

# ============================================================================
# Status Display
# ============================================================================
show_status() {
    echo ""
    echo "=============================================="
    echo "Voice Tic-Tac-Toe Server Status"
    echo "=============================================="
    echo ""
    
    # Backend status
    if is_backend_running; then
        local pid
        if pid=$(get_existing_pid "${BACKEND_PID_FILE}"); then
            echo -e "Backend Server: \033[0;32mRunning\033[0m (PID: ${pid})"
        else
            echo -e "Backend Server: \033[0;32mRunning\033[0m (PID file not found)"
        fi
    else
        echo -e "Backend Server: \033[0;31mNot Running\033[0m"
    fi
    
    # LLaMA status
    if is_llama_running; then
        local pid
        if pid=$(get_existing_pid "${SLM_PID_FILE}"); then
            echo -e "LLaMA Server:   \033[0;32mRunning\033[0m (PID: ${pid})"
        else
            echo -e "LLaMA Server:   \033[0;32mRunning\033[0m (PID file not found)"
        fi
    else
        echo -e "LLaMA Server:   \033[0;31mNot Running\033[0m"
    fi
    
    # ASR status (query backend endpoint)
    if is_backend_running; then
        local asr_response
        asr_response=$(curl -s --max-time 3 "${BACKEND_HEALTH_URL}/asr" 2>/dev/null || echo '{"status":"error"}')
        local asr_status
        asr_status=$(echo "$asr_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','error'))" 2>/dev/null || echo "error")
        local asr_device
        asr_device=$(echo "$asr_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('device','?'))" 2>/dev/null || echo "?")
        case "$asr_status" in
            healthy) echo -e "ASR Service:     \033[0;32mHealthy\033[0m (device: ${asr_device})" ;;
            degraded) echo -e "ASR Service:     \033[1;33mDegraded\033[0m (device: ${asr_device})" ;;
            disabled) echo -e "ASR Service:     \033[0;36mN/A\033[0m (not loaded)" ;;
            *) echo -e "ASR Service:     \033[0;31mNot Available\033[0m" ;;
        esac
    else
        echo -e "ASR Service:     \033[0;31mNot Running\033[0m (backend down)"
    fi
    
    # TTS status (query backend endpoint)
    if is_backend_running; then
        local tts_response
        tts_response=$(curl -s --max-time 3 "${BACKEND_HEALTH_URL}/tts" 2>/dev/null || echo '{"status":"error"}')
        local tts_status
        tts_status=$(echo "$tts_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','error'))" 2>/dev/null || echo "error")
        local tts_device
        tts_device=$(echo "$tts_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('device','?'))" 2>/dev/null || echo "?")
        case "$tts_status" in
            healthy) echo -e "TTS Service:     \033[0;32mHealthy\033[0m (device: ${tts_device})" ;;
            degraded) echo -e "TTS Service:     \033[1;33mDegraded\033[0m (device: ${tts_device})" ;;
            disabled) echo -e "TTS Service:     \033[0;36mDisabled\033[0m (tts_enabled = false)" ;;
            *) echo -e "TTS Service:     \033[0;31mNot Available\033[0m" ;;
        esac
    else
        echo -e "TTS Service:     \033[0;31mNot Running\033[0m (backend down)"
    fi
    
    echo ""
    echo "Ports:"
    echo "  - Backend API:  ${BACKEND_PORT}"
    echo "  - LLaMA Server: ${SLM_PORT}"
    echo ""
    echo "PID Files:"
    if [ -f "${BACKEND_PID_FILE}" ]; then
        echo -e "  - Backend: \033[0;32mexists\033[0m"
    else
        echo -e "  - Backend: \033[0;31mnot found\033[0m"
    fi
    if [ -f "${SLM_PID_FILE}" ]; then
        echo -e "  - LLaMA:   \033[0;32mexists\033[0m"
    else
        echo -e "  - LLaMA:   \033[0;31mnot found\033[0m"
    fi
    echo ""
    echo "=============================================="
}

# ============================================================================
# Help/Usage
# ============================================================================
show_help() {
    echo ""
    echo "Voice Tic-Tac-Toe Game Launcher"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  (none)          Start servers and launch game"
    echo "  start           Start servers, pre-warm models, launch game"
    echo "  stop            Stop all running servers"
    echo "  restart         Restart all servers and launch game"
    echo "  status          Show server status"
    echo "  help            Show this help message"
    echo ""
    echo "Options (when starting game):"
    echo "  --simulation    Run game in text-only simulation mode"
    echo "  --debug         Enable debug logging in game"
    echo ""
    echo "Examples:"
    echo "  $0                    # Start servers and launch game (audio mode)"
    echo "  $0 --simulation       # Start servers and launch text-only game"
    echo "  $0 stop               # Stop all servers"
    echo "  $0 restart --debug    # Restart servers and launch with debug mode"
    echo "  $0 status             # Check server status"
    echo ""
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    local command="${1:-start}"
    shift || true
    
    # Parse game options
    local game_args=()
    local simulation_mode=false
    
    for arg in "$@"; do
        case "$arg" in
            --simulation)
                simulation_mode=true
                game_args+=("--simulation")
                ;;
            --debug)
                game_args+=("--debug")
                ;;
            *)
                game_args+=("$arg")
                ;;
        esac
    done
    
    case "${command}" in
        start| "")
            log_info "=============================================="
            log_info "Starting Voice Tic-Tac-Toe Servers"
            log_info "=============================================="
            echo ""
            
            # Ensure logs directory exists
            mkdir -p "${PROJECT_DIR}/logs"
            
            # Start backend
            start_backend || {
                log_error "Failed to start backend server"
                exit 1
            }
            echo ""
            
            # Start LLaMA server
            start_llama_server || {
                log_error "Failed to start LLaMA server"
                exit 1
            }
            echo ""
            
            # Wait for health checks
            log_info "Waiting for servers to be healthy..."
            echo ""
            
            if ! wait_for_server "Backend API" "check_backend_health" "${MAX_WAIT_SECONDS}"; then
                log_error "Backend API health check failed"
                log_error "Check logs at: ${PROJECT_DIR}/logs/backend.log"
                exit 1
            fi
            
            if ! wait_for_server "LLaMA Server" "check_llama_health" "${MAX_WAIT_SECONDS}"; then
                log_error "LLaMA Server health check failed"
                log_error "Check logs at: ${PROJECT_DIR}/logs/llama.log"
                exit 1
            fi
            
            echo ""
            log_success "All servers are running and healthy!"
            echo ""
            
            # Pre-warm voice models (ASR + TTS)
            prewarm_models
            
            # Launch voice game
            launch_voice_game "${game_args[@]}"
            ;;
            
        start-only)
            # Start servers without launching the voice game.
            # Useful for starting the backend + SLM for browser mode only,
            # then launching the game separately with --simulation or --debug.
            # Usage: ./voice_game.sh start-only
            log_info "Starting servers without launching game..."
            echo ""
            
            mkdir -p "${PROJECT_DIR}/logs"
            start_backend || { log_error "Backend start failed"; exit 1; }
            echo ""
            start_llama_server || { log_error "LLaMA start failed"; exit 1; }
            echo ""
            
            wait_for_server "Backend API" "check_backend_health" "${MAX_WAIT_SECONDS}" || exit 1
            wait_for_server "LLaMA Server" "check_llama_health" "${MAX_WAIT_SECONDS}" || exit 1
            
            # Pre-warm voice models (ASR + TTS)
            prewarm_models
            
            log_success "Servers started successfully!"
            echo ""
            log_info "To launch the game, run: $0 --simulation or $0 --debug"
            echo ""
            show_status
            ;;
            
        stop)
            stop_all_servers
            cleanup_pid_files
            ;;
            
        restart)
            stop_all_servers
            cleanup_pid_files
            sleep 2
            # Re-run start
            if [ ${#game_args[@]} -gt 0 ]; then
                "$0" start "${game_args[@]}"
            else
                "$0" start
            fi
            ;;
            
        status)
            show_status
            ;;
            
        help|--help|-h)
            show_help
            ;;
            
        *)
            log_error "Unknown command: ${command}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
