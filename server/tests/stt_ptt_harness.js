// S1 — the portal's push-to-talk button.
//
// Loads the real <script> out of index.html into a stubbed DOM with a stub
// microphone (getUserMedia, a 48 kHz AudioContext and its script processor)
// and a stub /transcribe. Holds the button, feeds audio, releases, and prints
// what was sent where and what the question box holds, as JSON. Driven by
// test_s1_speech_in.py:
//   node stt_ptt_harness.js static/index.html <scenario>
// Scenarios: ok, append, short, denied, error, send.

'use strict';
const fs = require('fs');
const vm = require('vm');

const SCRIPT = fs.readFileSync(process.argv[2], 'utf8').split('<script>')[1].split('</script>')[0];
const SCENARIO = process.argv[3] || 'ok';
const TRANSCRIPT = 'Eighty kilo adult, cefazolin dose?';

function el(id) {
  const node = {
    id: id, innerHTML: '', textContent: '', value: '', title: '', className: '',
    style: {}, dataset: {}, disabled: false, checked: true,
    scrollTop: 0, scrollHeight: 0, children: [], _q: {}, _on: {}, focused: 0,
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); }, toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); },
    },
    appendChild(c) { node.children.push(c); return c; },
    querySelector(sel) { return (node._q[sel] = node._q[sel] || el()); },
    querySelectorAll() { return []; },
    addEventListener(type, fn) { (node._on[type] = node._on[type] || []).push(fn); },
    removeEventListener() {},
    dispatch(type, ev) {
      return Promise.all((node._on[type] || []).map(f => f(Object.assign(
        { type: type, preventDefault() {}, repeat: false }, ev || {}))));
    },
    closest() { return el(); }, remove() {}, focus() { node.focused++; }, blur() {},
    setAttribute() {},
  };
  return node;
}

async function main() {
  const calls = [];
  const tracks = { stopped: 0 };
  let processor = null;
  let clock = 1000;

  function AudioContext() {
    return {
      sampleRate: 48000, destination: {}, state: 'running',
      resume() { return Promise.resolve(); }, close() { return Promise.resolve(); },
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; },
      createScriptProcessor() {
        processor = { connect() {}, disconnect() {}, onaudioprocess: null };
        return processor;
      },
    };
  }
  const navigator = {
    mediaDevices: {
      getUserMedia: () => SCENARIO === 'denied'
        ? Promise.reject(new Error('Permission denied'))
        : Promise.resolve({ getTracks: () => [{ stop() { tracks.stopped++; } }] }),
    },
  };
  const byId = {};
  const sandbox = {
    console: { log() {}, error() {}, warn() {} },
    document: {
      getElementById: id => (byId[id] = byId[id] || el(id)),
      querySelector: sel => (sel === 'input[name=mode]:checked' ? { value: 'brief' } : el()),
      querySelectorAll: () => [], createElement: () => el(),
    },
    navigator,
    performance: { now: () => clock },
    fetch: (url, opts) => {
      const u = String(url);
      const body = opts && opts.body;
      calls.push({ url: u, headers: (opts && opts.headers) || {},
                   body: body instanceof Uint8Array ? Array.from(body.subarray(0, 44)) : (body ? JSON.parse(body) : null),
                   bytes: body instanceof Uint8Array ? body.length : null });
      if (u === '/transcribe') {
        clock += 400;
        if (SCENARIO === 'error')
          return Promise.resolve({ ok: false, status: 503,
            json: () => Promise.resolve({ detail: 'speech-in failed (ggml_cuda: out of memory)' }) });
        return Promise.resolve({ ok: true, status: 200,
          json: () => Promise.resolve({ text: TRANSCRIPT, audio_ms: 1000, transcribe_ms: 380, device: 'gpu' }) });
      }
      return Promise.reject(new Error('offline'));
    },
    setInterval: () => 0, setTimeout: (f) => { f(); return 0; },
    AudioContext, webkitAudioContext: AudioContext,
    Float32Array, Int16Array, Uint8Array, DataView, ArrayBuffer, TextDecoder,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
    sessionStorage: { getItem: () => 's-1', setItem() {} },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox);
  const settle = () => new Promise(r => setImmediate(r));

  const talk = byId.talk;
  const q = byId.q;
  if (!talk) throw new Error('no #talk button');
  if (SCENARIO === 'append') q.value = '80 kg adult,';

  const held = talk.dispatch('pointerdown');
  await settle();
  const recording = talk.textContent;
  // 1 s of audio at 48 kHz in 4096-sample blocks (0.1 s for "short").
  const blocks = SCENARIO === 'short' ? 1 : 12;
  for (let i = 0; i < blocks && processor && processor.onaudioprocess; i++) {
    const data = new Float32Array(4096).fill(0.5);
    processor.onaudioprocess({ inputBuffer: { getChannelData: () => data } });
  }
  await held;
  await talk.dispatch('pointerup');
  for (let i = 0; i < 5; i++) await settle();

  if (SCENARIO === 'send') {
    await byId.send.onclick();
    for (let i = 0; i < 5; i++) await settle();
  }
  process.stdout.write(JSON.stringify({
    calls: calls.filter(c => c.url === '/transcribe' || c.url === '/query'),
    box: q.value, recording: recording, button: talk.textContent, disabled: talk.disabled,
    note: (byId.talknote || {}).textContent || '', tracksStopped: tracks.stopped,
    focused: q.focused,
  }));
}

main().catch(e => { process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) })); });
