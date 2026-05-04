// Tic-Tac-Toe Frontend - API Consumer

// TTS toggle state (module-level so both playBotResponse and toggle handler can access it)
let ttsEnabled = true;

// API endpoint constants
const GAME_ENDPOINT = '/api/game';
const MOVE_ENDPOINT = '/api/game/move';
const POLL_INTERVAL = 2000; // 2 seconds between game state polls

let currentGameData = null;

// Mutex guard to prevent double-submission of voice commands
let isProcessing = false;
const VOICE_COMMAND_TIMEOUT = 30000; // 30 second timeout for SLM responses (browser-friendly)

// Singleton AudioContext for TTS playback (avoids creating one per response)
let sharedAudioContext = null;
function getAudioContext() {
    if (!sharedAudioContext) {
        sharedAudioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    return sharedAudioContext;
}

// Determine which 3 cells form the winning line
function getWinningLine(board) {
    const combos = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],  // rows
        [0, 3, 6], [1, 4, 7], [2, 5, 8],  // cols
        [0, 4, 8], [2, 4, 6]              // diagonals
    ];
    for (const [a, b, c] of combos) {
        if (board[a] && board[a] === board[b] && board[a] === board[c]) {
            return [a, b, c];
        }
    }
    return null;
}

// Render game board from data
function renderGame(data) {
    const boardDiv = document.getElementById('game-board');
    if (!boardDiv) return;

    boardDiv.innerHTML = '';

    // Determine winning line for highlighting
    const winningLine = getWinningLine(data.board);
    const isDraw = data.status === 'draw' || (data.gameOver && !data.winner);

    // Create 9 cells for the board
    for (let i = 0; i < 9; i++) {
        const cell = document.createElement('div');
        cell.className = 'cell';

        if (data.board[i]) {
            cell.classList.add(data.board[i].toLowerCase());
        }

        if (winningLine && winningLine.includes(i)) {
            cell.classList.add('winning');
        }

        if (isDraw) {
            cell.classList.add('draw');
        }

        cell.dataset.position = i;

        if (data.board[i]) {
            const content = document.createElement('span');
            content.className = 'content';
            content.textContent = data.board[i];
            cell.appendChild(content);
        }

        cell.addEventListener('click', () => {
            if (!currentGameData || currentGameData.gameOver) return;
            makeMove(i);
        });

        boardDiv.appendChild(cell);
    }
}

// Render game status
function renderStatus(turn, winner, status) {
    const statusDiv = document.getElementById('status');
    if (!statusDiv) return;

    // Clear any previous status classes
    statusDiv.className = 'status';

    if (winner === 'X' || winner === 'O') {
        statusDiv.textContent = `${winner} Wins!`;
        statusDiv.classList.add('status-win');
    } else if (status === 'draw') {
        statusDiv.textContent = "It's a Draw!";
        statusDiv.classList.add('status-draw');
    } else {
        statusDiv.textContent = `Current turn: ${turn}`;
    }
}

// Make a move
function makeMove(position) {
    fetch(MOVE_ENDPOINT, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({position: position})
    })
    .then(async response => {
        const data = await response.json();
        if (!response.ok) {
            showToast(data.detail || 'Invalid move. Please try again.', 'error');
            return;
        }
        currentGameData = data;
        renderGame(data);
        renderStatus(data.turn, data.winner, data.status);
    })
    .catch(error => {
        console.error('Error making move:', error);
        showToast('Connection error. Please try again.', 'error');
    });
}

// Clear voice chat messages
function clearVoiceChat() {
    const messagesDiv = document.getElementById('voice-messages');
    if (messagesDiv) {
        messagesDiv.innerHTML = '';
    }
}

// Create a new game
function createGame() {
    fetch(GAME_ENDPOINT, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            clearVoiceChat();
            currentGameData = data;
            renderGame(data);
            renderStatus(data.turn, null, data.status);
        })
        .catch(error => {
            console.error('Error creating game:', error);
            showToast('Failed to create game. Please try again.', 'error');
        });
}

// ============================================================================
// Voice Command Functions - Defined once (not on every page load)
// ============================================================================

// Voice command response templates — loaded from backend to avoid duplication
let RESPONSE_TEMPLATES = {};

// Load response templates from backend API
async function loadTemplates() {
    try {
        const res = await fetch('/api/config/templates');
        if (res.ok) {
            const data = await res.json();
            RESPONSE_TEMPLATES = data.templates || {};
        }
    } catch (e) {
        console.warn('[Templates] Failed to load from backend, using defaults:', e);
        // Fallback defaults
        RESPONSE_TEMPLATES = {
            start_game: "New game started! You are player X. Your turn to place a mark.",
            get_board: "{board_description}",
            get_status: "{status_description}",
            place_move: "{move_result}",
            greeting: "Welcome to Tic-Tac-Toe! Say 'start' to begin a new game.",
            goodbye: "Thanks for playing! Goodbye!",
            thank_you: "You're welcome! Is there anything else I can help with?",
            intent_unclear: "I didn't quite understand that. I can help you start a game, place moves, check the board, or check the status."
        };
    }
}

// Toast notification system — replaces blocking alert()
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    const duration = type === 'error' ? 8000 : 5000;
    setTimeout(() => toast.remove(), duration);
}

// Position name mappings (for descriptions)
const POSITION_NAMES = [
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right"
];

// Add voice message to display
function addVoiceMessage(role, text) {
    const messagesDiv = document.getElementById('voice-messages');
    if (!messagesDiv) {
        console.warn('Voice messages container not found');
        return;
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    // Different colors: bot in blue, user commands in green
    if (role === 'bot') {
        messageDiv.style.color = '#0066cc';
        messageDiv.textContent = '🤖 ' + text;
    } else if (role === 'user') {
        messageDiv.style.color = '#009900';
        messageDiv.textContent = '🎤 ' + text;
    }
    
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Show thinking/loading indicator in voice chat
function showThinkingIndicator() {
    const messagesDiv = document.getElementById('voice-messages');
    if (!messagesDiv) return;
    hideThinkingIndicator();
    const msg = document.createElement('div');
    msg.className = 'message bot thinking';
    msg.id = 'thinking-indicator';
    msg.innerHTML = '<span class="dot-flashing"></span> Thinking...';
    messagesDiv.appendChild(msg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Remove thinking indicator
function hideThinkingIndicator() {
    const existing = document.getElementById('thinking-indicator');
    if (existing) existing.remove();
}

// Play bot response audio via TTS API
function playBotResponse(text) {
    if (!ttsEnabled) return;
    
    fetch('/api/voice/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
    })
    .then(async response => {
        if (!response.ok) {
            console.warn('[TTS] Synthesis failed:', response.status);
            return;
        }
        const data = await response.json();
        // Decode base64 WAV and play via AudioContext
        const audioBytes = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
        const audioContext = getAudioContext();
        const audioBuffer = await audioContext.decodeAudioData(audioBytes.buffer);
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start(0);
    })
    .catch(error => {
        console.warn('[TTS] Playback failed:', error);
    });
}

// Get position description from row/col
function getPositionDescription(row, col) {
    const position = row * 3 + col;
    return POSITION_NAMES[position];
}

// Execute voice command via SLM pipeline
async function executeVoiceCommand(functionName, cmdArgs) {
    // Only execute if voice panel exists
    const voicePanel = document.querySelector('.voice-panel');
    if (!voicePanel) {
        console.warn('Voice panel not found, skipping voice command');
        return;
    }
    
    // Prevent double-submission
    if (isProcessing) {
        showToast('Please wait — a command is already being processed.', 'warning');
        return;
    }
    isProcessing = true;
    
    // Read input field BEFORE any await to avoid race condition with input clearing
    const input = document.getElementById('voice-input');
    const commandText = input ? input.value.trim() : '';
    
    // Ensure a game exists before processing any command
    try {
        const gameCheck = await fetch(GAME_ENDPOINT);
        if (!gameCheck.ok) {
            // No game exists — create one
            console.log('[Voice] No game exists, creating one...');
            await createGame();
        }
    } catch (error) {
        console.error('[Voice] Error checking game state:', error);
        // Attempt to create a game so commands can still proceed
        try {
            console.log('[Voice] Attempting to create game after check failure...');
            await createGame();
        } catch (createError) {
            console.error('[Voice] Failed to create game:', createError);
            showToast('Could not connect to game server. Please refresh the page.', 'error');
            addVoiceMessage("bot", 'Could not connect to the game server. Please refresh the page and try again.');
            isProcessing = false;
            return;
        }
    }

    // Handle greeting — direct response (no SLM needed)
    if (functionName === "greeting") {
        addVoiceMessage("bot", RESPONSE_TEMPLATES.greeting);
        isProcessing = false;
        return;
    }
    
    // Handle goodbye — direct response with exit alert
    if (functionName === "goodbye") {
        addVoiceMessage("bot", RESPONSE_TEMPLATES.goodbye);
        showToast("Thanks for playing!", "success");
        isProcessing = false;
        return;
    }
    
    // Derive the natural language text to send to SLM
    let textToSend = '';
    
    // Priority 1: Input field text (captured above before any await)
    if (commandText) {
        textToSend = commandText;
    }
    
    // Priority 2: Place move from button click (overrides input)
    if (functionName === 'place_move' && cmdArgs && cmdArgs.row !== undefined) {
        const posDesc = getPositionDescription(cmdArgs.row, cmdArgs.col);
        textToSend = `place at ${posDesc}`;
    }
    
    // Priority 3: Map function name to natural language text
    if (!textToSend) {
        const cmdMap = {
            start_game: 'start game',
            show_board: 'show board', 
            check_status: 'check status',
            quit: 'quit',
            greeting: 'hello',
            place_move: 'place a move'
        };
        textToSend = cmdMap[functionName] || commandText;
    }
    
    // Don't send empty commands
    if (!textToSend) {
        addVoiceMessage("bot", "Please enter a command.");
        isProcessing = false;
        return;
    }
    
    try {
        console.log('[Voice] Sending command to SLM:', textToSend);
        showThinkingIndicator();

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), VOICE_COMMAND_TIMEOUT);

        const response = await fetch('/api/voice/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: textToSend }),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        console.log('[Voice] Response status:', response.status);

        if (!response.ok) {
            const errorText = await response.text();
            console.error('[Voice] API error:', errorText);
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        console.log('[Voice] API response:', JSON.stringify(data));

        hideThinkingIndicator();

        if (data.success && data.response) {
            addVoiceMessage("bot", data.response);
            playBotResponse(data.response);
        } else {
            addVoiceMessage("bot", data.response || "I didn't quite understand that. I can help you start a game, place moves, check the board, or check the status.");
            playBotResponse(data.response || "I didn't quite understand that.");
        }

        // Re-render game board if the command succeeded
        if (data.success) {
            const gameResponse = await fetch('/api/game');
            if (gameResponse.ok) {
                const gameData = await gameResponse.json();
                currentGameData = gameData;
                renderGame(gameData);
                renderStatus(gameData.turn, gameData.winner, gameData.status);
            }
        }
    } catch (error) {
        console.error('[Voice] Fetch error:', error);
        hideThinkingIndicator();
        addVoiceMessage("bot", "Error: " + error.message);
        if (error.name === 'AbortError') {
            addVoiceMessage("bot", "The request timed out. Please try again.");
        }
    } finally {
        isProcessing = false;
    }
}

// ============================================================================
// Server Health Check — Status Indicators
// ============================================================================

const BACKEND_HEALTH_URL = '/api/health';
const SLM_HEALTH_URL = '/api/health/slm';
const ASR_HEALTH_URL = '/api/health/asr';
const TTS_HEALTH_URL = '/api/health/tts';
const HEALTH_CHECK_INTERVAL = 15000; // 15 seconds
const HEALTH_CHECK_TIMEOUT = 5000; // 5 second timeout per health check fetch

const serverStatuses = {
    backend: { status: 'checking', lastChecked: null, error: null },
    slm: { status: 'checking', lastChecked: null, error: null },
    asr: { status: 'checking', lastChecked: null, error: null },
    tts: { status: 'checking', lastChecked: null, error: null }
};

async function checkServerHealth(serverName, url) {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT);
        const response = await fetch(url, { signal: controller.signal });
        clearTimeout(timeoutId);
        
        if (response.ok) {
            // For ASR/TTS, parse structured status
            if (serverName === 'asr' || serverName === 'tts') {
                try {
                    const data = await response.json();
                    const statusMap = { 'healthy': 'up', 'disabled': 'up', 'degraded': 'down', 'unavailable': 'down' };
                    serverStatuses[serverName].status = statusMap[data.status] || 'down';
                    serverStatuses[serverName].error = data.error || null;
                    serverStatuses[serverName].device = data.device || null;
                } catch {
                    serverStatuses[serverName].status = 'up';
                    serverStatuses[serverName].error = null;
                }
            } else {
                serverStatuses[serverName].status = 'up';
                serverStatuses[serverName].error = null;
            }
        } else {
            serverStatuses[serverName].status = 'down';
            serverStatuses[serverName].error = `HTTP ${response.status}`;
        }
    } catch (error) {
        serverStatuses[serverName].status = 'down';
        serverStatuses[serverName].error = error.message;
    }
    serverStatuses[serverName].lastChecked = new Date();
    updateServerStatusUI();
}

async function checkAllServers() {
    serverStatuses.backend.status = 'checking';
    serverStatuses.slm.status = 'checking';
    serverStatuses.asr.status = 'checking';
    serverStatuses.tts.status = 'checking';
    updateServerStatusUI();
    
    await Promise.all([
        checkServerHealth('backend', BACKEND_HEALTH_URL),
        checkServerHealth('slm', SLM_HEALTH_URL),
        checkServerHealth('asr', ASR_HEALTH_URL),
        checkServerHealth('tts', TTS_HEALTH_URL)
    ]);
}

function updateServerStatusUI() {
    for (const [serverName, status] of Object.entries(serverStatuses)) {
        const dot = document.getElementById(`${serverName}-status-dot`);
        const badge = document.getElementById(`${serverName}-status`);
        if (!dot || !badge) continue;
        
        dot.className = `status-dot status-${status.status}`;
        
        const deviceInfo = status.device ? ` [${status.device.toUpperCase()}]` : '';
        const timeStr = status.lastChecked 
            ? status.lastChecked.toLocaleTimeString() 
            : 'never';
        badge.title = `${serverName.charAt(0).toUpperCase() + serverName.slice(1)}: ${status.status.toUpperCase()}${deviceInfo}${status.error ? ' (' + status.error + ')' : ''} | Last checked: ${timeStr}`;
        
        const displayName = serverName.charAt(0).toUpperCase() + serverName.slice(1);
        const label = dot.nextElementSibling;
        if (label) {
            label.textContent = status.status === 'checking' 
                ? `${displayName}: Checking...` 
                : `${displayName}: ${status.status.toUpperCase()}${deviceInfo}`;
        }
    }
}

function startHealthCheckPolling() {
    // Only run if the status badges exist on the page
    if (!document.getElementById('backend-status')) return;
    
    checkAllServers();
    setInterval(checkAllServers, HEALTH_CHECK_INTERVAL);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Show prompt instead of auto-creating a game
    const statusEl = document.getElementById('status');
    if (statusEl) {
        statusEl.textContent = "Click 'New Game' to start";
    }
    
    // NEW GAME button listener - always registered for regular game page
    const newGameBtn = document.getElementById('new-game-btn');
    if (newGameBtn) {
        newGameBtn.addEventListener('click', createGame);
    }
    
    // ============================================================================
    // Server Health Check Polling
    // ============================================================================
    startHealthCheckPolling();

    // ============================================================================
    // Auto-Polling for Real-Time Updates from Voice Game
    // ============================================================================
    // Poll the API every 2 seconds to detect updates from the voice game
    // This ensures the frontend shows the current state when the voice game makes moves
    
    let pollingInterval = null;
    let lastGameDataHash = '';
    
    function calculateGameHash(data) {
        // Create a simple hash from game state to detect changes
        const boardStr = data.board.join('|');
        return `${boardStr}-${data.turn}-${data.status}-${data.winner || ''}`;
    }
    
    async function pollForUpdates() {
        try {
            const response = await fetch(GAME_ENDPOINT);
            if (!response.ok) return;
            
            const data = await response.json();
            
            // Stop polling if game is over
            if (data.gameOver) {
                clearInterval(pollingInterval);
                pollingInterval = null;
            }
            
            // Only update if game state has changed
            const currentHash = calculateGameHash(data);
            if (currentHash !== lastGameDataHash) {
                lastGameDataHash = currentHash;
                currentGameData = data;
                renderGame(data);
                renderStatus(data.turn, data.winner, data.status);
            }
        } catch (error) {
            // Silently ignore polling errors
            console.debug('Polling error:', error);
        }
    }
    
    // Start polling every 2 seconds
    pollingInterval = setInterval(pollForUpdates, POLL_INTERVAL);
    
    // Clear polling interval when page is unloaded
    window.addEventListener('beforeunload', () => {
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }
    });
    
    // Only initialize voice controls if voice panel exists (index.html page)
    const voicePanel = document.querySelector('.voice-panel');
    if (!voicePanel) {
        // Not on voice game page, exit early
        return;
    }

    // ============================================================================
    // Voice Command Event Listeners - Only registered on index.html
    // ============================================================================

    // Initialize voice control event listeners (only if elements exist)
    const micBtn = document.getElementById('mic-btn');
    if (micBtn) {
        let mediaStream = null;
        let audioContext = null;
        let scriptProcessor = null;
        let audioChunks = [];       // accumulated Float32Array chunks
        let isRecording = false;
        let isTranscribing = false;
        
        micBtn.addEventListener('click', async function() {
            if (isRecording) {
                // STOP recording and transcribe
                stopRecording();
                return;
            }
            
            if (isTranscribing) return;  // Don't interrupt ongoing transcription
            
            try {
                // Request microphone access
                mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                
                // Set up AudioContext for raw PCM capture
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const source = audioContext.createMediaStreamSource(mediaStream);
                
                // ScriptProcessorNode to get raw float32 samples
                // Buffer size 4096, 1 channel (mono)
                scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
                audioChunks = [];
                
                scriptProcessor.onaudioprocess = function(event) {
                    const input = event.inputBuffer.getChannelData(0);
                    // Make a copy so the buffer isn't overwritten
                    audioChunks.push(new Float32Array(input));
                };
                
                source.connect(scriptProcessor);
                scriptProcessor.connect(audioContext.destination);
                
                isRecording = true;
                micBtn.classList.add('listening');
                micBtn.textContent = '⏹️ Stop';
                micBtn.style.background = 'linear-gradient(145deg, #d46a4a, #b85030)';
                
            } catch (err) {
                console.error('Microphone access error:', err);
                if (err.name === 'NotAllowedError') {
                    showToast('Microphone access denied. Please allow microphone permissions.', 'error');
                    addVoiceMessage("bot", 'Microphone access was denied. Please enable it in your browser settings and try again.');
                } else {
                    showToast('Could not access microphone: ' + err.message, 'error');
                    addVoiceMessage("bot", 'Could not access microphone. Please check your device and try again.');
                }
            }
        });
        
        function stopRecording() {
            isRecording = false;
            
            // Disconnect audio nodes
            if (scriptProcessor) {
                scriptProcessor.disconnect();
            }
            if (mediaStream) {
                mediaStream.getTracks().forEach(track => track.stop());
            }
            if (audioContext) {
                audioContext.close();
            }
            
            // Reset UI
            micBtn.classList.remove('listening');
            micBtn.textContent = '🎤';
            micBtn.style.background = '';
            
            // Concatenate all chunks into one Float32Array
            const totalLength = audioChunks.reduce((sum, chunk) => sum + chunk.length, 0);
            const combined = new Float32Array(totalLength);
            let offset = 0;
            for (const chunk of audioChunks) {
                combined.set(chunk, offset);
                offset += chunk.length;
            }
            
            // Resample from browser sample rate (usually 48kHz) to 16kHz
            const browserSampleRate = audioContext?.sampleRate || 48000;
            // ASR expects 16kHz; TTS uses 24kHz (config/voice.conf tts.sample_rate)
            const targetSampleRate = 16000;
            const resampled = resampleAudio(combined, browserSampleRate, targetSampleRate);
            
            // Encode as base64
            const bytes = new Uint8Array(resampled.buffer);
            // Chunked base64 encoding to avoid call stack limits with large audio buffers
            let base64Audio = '';
            // 8KB chunk for base64 encoding (balanced memory vs iteration)
            const chunkSize = 8192;
            for (let i = 0; i < bytes.length; i += chunkSize) {
                const chunk = bytes.subarray(i, Math.min(i + chunkSize, bytes.length));
                base64Audio += String.fromCharCode.apply(null, chunk);
            }
            base64Audio = btoa(base64Audio);
            
            // Transcribe via backend
            transcribeAudio(base64Audio, targetSampleRate);
        }
        
        // Simple linear interpolation resampler
        function resampleAudio(audioData, fromRate, toRate) {
            if (fromRate === toRate) return audioData;
            const ratio = fromRate / toRate;
            const newLength = Math.floor(audioData.length / ratio);
            const result = new Float32Array(newLength);
            
            for (let i = 0; i < newLength; i++) {
                const pos = i * ratio;
                const idx = Math.floor(pos);
                const frac = pos - idx;
                
                if (idx + 1 < audioData.length) {
                    result[i] = audioData[idx] * (1 - frac) + audioData[idx + 1] * frac;
                } else {
                    result[i] = audioData[idx] || 0;
                }
            }
            return result;
        }
        
        function transcribeAudio(base64Audio, sampleRate) {
            isTranscribing = true;
            micBtn.textContent = '⏳';  // loading indicator
            
            const audioDuration = (base64Audio.length / 4 * 3 / sampleRate).toFixed(2);
            console.log(`[Transcribe] Sending audio: ~${audioDuration}s, base64 size: ${base64Audio.length} chars`);
            
            fetch('/api/voice/transcribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ audio: base64Audio, sample_rate: sampleRate })
            })
            .then(async response => {
                console.log(`[Transcribe] Response status: ${response.status}`);
                if (!response.ok) {
                    const errText = await response.text();
                    console.error(`[Transcribe] Error response:`, errText);
                    throw new Error(errText || `HTTP ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log(`[Transcribe] Response data:`, JSON.stringify(data));
                const text = data.text?.trim();
                if (text) {
                    console.log(`[Transcribe] Transcribed: "${text}"`);
                    // Populate voice input and auto-submit
                    const voiceInput = document.getElementById('voice-input');
                    if (voiceInput) voiceInput.value = text;
                    
                    const sendBtn = document.getElementById('send-cmd-btn');
                    if (sendBtn) {
                        // 300ms delay to let the input field populate before triggering send
                        setTimeout(() => sendBtn.click(), 300);
                    }
                } else {
                    console.warn('[Transcribe] Empty transcription result');
                    addVoiceMessage("bot", "I didn't hear anything. Please try again.");
                }
            })
            .catch(error => {
                console.error('[Transcribe] Failed:', error);
                showToast('Transcription failed: ' + error.message, 'error');
                addVoiceMessage("bot", 'Transcription failed. Please try again.');
            })
            .finally(() => {
                isTranscribing = false;
                if (isRecording) {
                    // If still recording (shouldn't happen), restore button state
                    micBtn.textContent = '⏹️ Stop';
                } else {
                    micBtn.textContent = '🎤';
                }
            });
        }
    }

    // Send button triggers command via SLM pipeline
    const sendBtn = document.getElementById('send-cmd-btn');
    if (sendBtn) {
        sendBtn.addEventListener('click', function() {
            const input = document.getElementById('voice-input');
            if (!input) return;
            const text = input.value.trim();
            if (!text) return;
            
            // Show user command
            addVoiceMessage("user", text);
            
            // Execute via SLM pipeline
            executeVoiceCommand(text, {});
            
            // Clear input
            input.value = '';
        });
    }

    // Enter key submits command
    const voiceInput = document.getElementById('voice-input');
    if (voiceInput && sendBtn) {
        voiceInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendBtn.click();
            }
        });
    }

    // Quick command buttons
    const quickCommandsContainer = document.querySelector('.quick-commands');
    if (quickCommandsContainer) {
        quickCommandsContainer.querySelectorAll('button').forEach(button => {
            button.addEventListener('click', function() {
                const cmd = this.getAttribute('data-cmd');
                
                // Map quick commands to actual command text
                const cmdMap = {
                    'start_game': 'start game',
                    'show_board': 'show board',
                    'check_status': 'check status',
                    'quit': 'quit'
                };
                
                const text = cmdMap[cmd];
                if (!text) return;
                
                // Show user command
                addVoiceMessage("user", text);
                
                // Execute via SLM pipeline
                executeVoiceCommand(cmd, {});
            });
        });
    }

    // Position buttons
    const positionButtonsContainer = document.querySelector('.position-buttons');
    if (positionButtonsContainer) {
        positionButtonsContainer.querySelectorAll('button').forEach(button => {
            button.addEventListener('click', function() {
                const row = this.getAttribute('data-row');
                const col = this.getAttribute('data-col');
                if (!row || !col) return;
                
                const posDesc = getPositionDescription(parseInt(row), parseInt(col));
                
                // Show user command
                addVoiceMessage("user", `place at ${posDesc}`);
                
                // Execute move via SLM pipeline
                executeVoiceCommand('place_move', { row: parseInt(row), col: parseInt(col) });
            });
        });
    }

    // TTS toggle
    const ttsToggle = document.getElementById('tts-toggle');
    if (ttsToggle) {
        ttsEnabled = localStorage.getItem('tts_enabled') !== 'false';
        ttsToggle.checked = ttsEnabled;
        ttsToggle.addEventListener('change', function() {
            ttsEnabled = this.checked;
            localStorage.setItem('tts_enabled', this.checked ? 'true' : 'false');
        });
    }

    // Load templates from backend
    loadTemplates();
});