const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const listeners = {}, elements = {}, calls = [], messages = [];
function element(id) {
  if (elements[id]) return elements[id];
  const value = {id, value: '', textContent: '', checked: true, className: '', style: {}, dataset: {}, children: [], innerHTML: '', scrollTop: 0,
    addEventListener(name, handler) {
      const key = `${id}:${name}`, previous = listeners[key];
      listeners[key] = previous ? function(...args) { const first = previous.apply(this, args); return handler.apply(this, args) ?? first; } : handler;
    },
    click() { return listeners[`${id}:click`]?.call(value); },
    appendChild(child) { this.children.push(child); if (id === 'voice-messages') messages.push(child.textContent); },
    remove() {}, classList: {add() {}, remove() {}}, querySelectorAll() { return []; }};
  return elements[id] = value;
}
for (const id of ['voice-input','send-cmd-btn','voice-messages','game-board','status','new-game-btn','backend-status','backend-status-dot','typesafe-status','typesafe-status-dot','asr-status','asr-status-dot','tts-status','tts-status-dot','mic-btn','tts-toggle']) element(id);
for (const name of ['backend','typesafe','asr','tts']) element(`${name}-status-dot`).nextElementSibling = element(`${name}-status-label`);
function quickButton(command) { const value = element(`quick-${command}`); value.getAttribute = name => name === 'data-cmd' ? command : null; return value; }
const quickButtons = ['start_game','show_board','check_status','quit'].map(quickButton);
const positionButton = element('position-top-center');
positionButton.getAttribute = name => ({'data-row': '0', 'data-col': '1'})[name] ?? null;

let commandResponse = {ok: true, status: 200, json: async () => ({success: true, message: 'Please confirm center.', intent: 'place_move', confidence: .7, clarification_required: true, position: 'center', pending: {}})};
let typeSafeStatus = 'unconfigured';
const game = {board: Array(9).fill(null), turn: 'X', winner: null, status: 'ongoing', gameOver: false};
async function fetch(url, options = {}) {
  calls.push({url, options});
  if (url === '/api/game/command') return commandResponse;
  if (url === '/api/game') return {ok: true, status: 200, json: async () => game};
  if (url === '/api/game/move') return {ok: true, status: 200, json: async () => ({...game, board: [null,'X',...Array(7).fill(null)], turn: 'O'})};
  if (url === '/api/game/depart') return {ok: true, status: 200, json: async () => ({message: 'Thanks for playing! Goodbye!'})};
  if (url === '/api/health/typesafe') return {ok: true, status: 200, json: async () => ({status: typeSafeStatus})};
  if (url.startsWith('/api/health')) return {ok: true, status: 200, json: async () => ({status: 'healthy'})};
  if (url === '/api/voice/transcribe') return {ok: true, status: 200, json: async () => ({text: 'move center'})};
  if (url === '/api/voice/synthesize') return {ok: true, status: 200, json: async () => ({audio: ''})};
  throw new Error(`Unexpected fetch: ${url}`);
}
class FakeAudioContext { constructor() { this.destination = {}; } async decodeAudioData() { return {}; } createBufferSource() { return {connect() {}, start() {}}; } }
let recognition;
class FakeSpeechRecognition { constructor() { recognition = this; } start() {} stop() { this.onend?.(); } }
const document = {
  getElementById: element, createElement: () => element(`created-${Object.keys(elements).length}`),
  querySelector(selector) {
    if (selector === '.voice-panel') return element('voice-panel');
    if (selector === '.quick-commands') return {querySelectorAll: () => quickButtons};
    if (selector === '.position-buttons') return {querySelectorAll: () => [positionButton]};
    if (selector === '.toast-container') return element('toast-container');
    return null;
  },
  addEventListener(name, handler) { listeners[`document:${name}`] = handler; },
};
const context = {console, document, fetch, Uint8Array,
  AbortController: class { constructor() { this.signal = {}; } abort() {} },
  setTimeout(handler) { Promise.resolve().then(handler); return 1; }, clearTimeout() {}, setInterval() { return 1; }, clearInterval() {},
  atob: () => '', btoa: () => '', localStorage: {getItem: () => null, setItem() {}}, window: {AudioContext: FakeAudioContext, SpeechRecognition: FakeSpeechRecognition, addEventListener() {}}};
context.globalThis = context;
vm.runInNewContext(fs.readFileSync('frontend/static/app.js', 'utf8'), context);
listeners['document:DOMContentLoaded']();
const flush = () => new Promise(resolve => setImmediate(resolve));
const commandCalls = () => calls.filter(call => call.url === '/api/game/command');

async function testNaturalLanguagePaths() {
  calls.length = 0; element('voice-input').value = 'move center'; await element('send-cmd-btn').click(); await flush();
  assert.deepStrictEqual(JSON.parse(commandCalls()[0].options.body), {control: 'move center'});
  assert(!calls.some(call => call.url === '/api/game' && call.options.method === 'POST'), 'natural language pre-created a game');
  assert(messages.some(message => message.includes('Please confirm center.')), 'clarification message was not rendered');
  assert(calls.some(call => call.url === '/api/game' && !call.options.method), 'current game state was not refreshed');
  calls.length = 0; await context.transcribeAudio('', 16000); await flush();
  assert(calls.some(call => call.url === '/api/voice/transcribe'), 'browser speech did not use transcription endpoint');
  assert.deepStrictEqual(JSON.parse(commandCalls()[0].options.body), {control: 'move center'});
  calls.length = 0; await element('mic-btn').click();
  recognition.onresult({results: [[{transcript: 'move center'}]]}); await flush();
  assert.deepStrictEqual(JSON.parse(commandCalls()[0].options.body), {control: 'move center'});
  calls.length = 0; commandResponse = {ok: false, status: 503, json: async () => ({detail: {code: 'typesafe_not_configured', request_id: 'safe'}})};
  context.handleTranscription('hello'); await flush();
  assert(messages.some(message => message.includes('typesafe_not_configured')), 'stable command failure was not rendered');
  assert.strictEqual(context.readErrorDetail({detail: 'Command service unavailable'}, 503), 'Command service unavailable');
  assert.strictEqual(context.readErrorDetail({detail: [{msg: 'control must not be blank'}]}, 422), 'control must not be blank');
}

async function testStructuredControlsBypassInference() {
  commandResponse = {ok: false, status: 503, json: async () => ({detail: {code: 'typesafe_service_unavailable'}})};
  for (const control of [element('new-game-btn'), ...quickButtons, positionButton]) {
    calls.length = 0; await control.click(); await flush();
    assert.strictEqual(commandCalls().length, 0, `${control.id} called Jev`);
    if (control === positionButton) assert(calls.some(call => call.url === '/api/game/move'), 'position control did not use direct move route');
    if (control === quickButtons[3]) assert(calls.some(call => call.url === '/api/game/depart'), 'quit did not use direct departure route');
  }
  assert(messages.some(message => message.includes('New game started. X goes first.')), 'structured start did not render confirmation');
}

async function testPassiveHealthStates() {
  for (const status of ['unconfigured','unverified','healthy','degraded','unavailable']) {
    typeSafeStatus = status; calls.length = 0;
    await context.checkServerHealth('typesafe', '/api/health/typesafe');
    assert(element('typesafe-status-label').textContent.includes(status.toUpperCase()), `${status} label was not rendered`);
    const expected = status === 'healthy' ? 'status-up' : status === 'unverified' ? 'status-checking' : 'status-down';
    assert(element('typesafe-status-dot').className.includes(expected), `${status} dot was not rendered honestly`);
    assert.strictEqual(commandCalls().length, 0, 'passive health called command inference');
  }
}

async function testTtsToggleAndPlayback() {
  calls.length = 0; context.playBotResponse('spoken response'); await flush();
  assert(calls.some(call => call.url === '/api/voice/synthesize'), 'enabled TTS did not synthesize');
  element('tts-toggle').checked = false; listeners['tts-toggle:change'].call(element('tts-toggle'));
  calls.length = 0; context.playBotResponse('silent response'); await flush();
  assert(!calls.some(call => call.url === '/api/voice/synthesize'), 'disabled TTS synthesized audio');
}

(async () => {
  await flush(); await testNaturalLanguagePaths(); await testStructuredControlsBypassInference(); await testPassiveHealthStates(); await testTtsToggleAndPlayback();
  console.log('browser controller smoke: passed');
})().catch(error => { console.error(error); process.exit(1); });
