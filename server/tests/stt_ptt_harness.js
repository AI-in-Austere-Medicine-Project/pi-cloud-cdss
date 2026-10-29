// S1 — the portal's push-to-talk button.
//
// Loads the real <script> out of index.html into a stubbed DOM with a stub
// microphone (getUserMedia, a 48 kHz AudioContext and its script processor)
// and a stub /transcribe. Holds the button, feeds audio, releases, and prints
// what was sent where and what the question box holds, as JSON. Driven by
// test_s1_speech_in.py:
//   node stt_ptt_harness.js static/index.html <scenario>
// Scenarios: ok, append, short, denied, error, send; P1: insecure, nomic,
// early (let go before the microphone opened), silent (zeros), noaudio (no
// audio callbacks at all), neterr, empty.

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
  const warned = [];
  const boxSteps = [];
  let micOpen = null;         // "early": the microphone opens when the harness says

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
  const stream = { getTracks: () => [{ stop() { tracks.stopped++; } }] };
  const domError = (name, message) => Object.assign(new Error(message), { name });
  // P1: over http by IP the browser gives no navigator.mediaDevices at all.
  const navigator = SCENARIO === 'insecure' ? {} : {
    mediaDevices: {
      getUserMedia: () => {
        if (SCENARIO === 'denied') return Promise.reject(domError('NotAllowedError', 'Permission denied'));
        if (SCENARIO === 'nomic') return Promise.reject(domError('NotFoundError', 'Requested device not found'));
        if (SCENARIO === 'early') return new Promise(r => { micOpen = () => r(stream); });
        return Promise.resolve(stream);
      },
    },
  };
  const byId = {};
  const sandbox = {
    console: { log() {}, error() {}, warn(...a) { warned.push(a.map(String).join(' ')); } },
    isSecureContext: SCENARIO !== 'insecure',
    location: SCENARIO === 'insecure'
      ? { protocol: 'http:', host: '192.168.1.126:8000', hostname: '192.168.1.126', origin: 'http://192.168.1.126:8000' }
      : { protocol: 'https:', host: 'cdss.example', hostname: 'cdss.example', origin: 'https://cdss.example' },
    document: {
      getElementById: id => (byId[id] = byId[id] || el(id)),
      querySelector: () => el(),
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
        if (SCENARIO === 'neterr') return Promise.reject(new TypeError('Failed to fetch'));
        if (SCENARIO === 'empty')
          return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve({ text: '', audio_ms: 1000, transcribe_ms: 300, device: 'gpu' }) });
        if (SCENARIO === 'error')
          return Promise.resolve({ ok: false, status: 503,
            json: () => Promise.resolve({ detail: 'speech-in failed (ggml_cuda: out of memory)' }) });
        return Promise.resolve({ ok: true, status: 200,
          json: () => Promise.resolve({ text: TRANSCRIPT, audio_ms: 1000, transcribe_ms: 380, device: 'gpu' }) });
      }
      return Promise.reject(new Error('offline'));
    },
    setInterval: () => 0, clearInterval() {},
    // Run on the next microtask, without the wait, and keep what the box held
    // after each: the word-by-word reveal is a chain of these. (Run inline, a
    // chain would finish inside its first step and record only the last.)
    setTimeout: (f) => {
      Promise.resolve().then(() => {
        f();
        const v = (byId.q || {}).value;
        if (v !== undefined && v !== boxSteps[boxSteps.length - 1]) boxSteps.push(v);
      });
      return 0;
    },
    clearTimeout() {},
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
  // 1 s of audio at 48 kHz in 4096-sample blocks (0.1 s for "short"); none
  // at all for "noaudio" (a suspended AudioContext), zeros for "silent".
  const blocks = SCENARIO === 'short' ? 1 : SCENARIO === 'noaudio' ? 0 : 12;
  for (let i = 0; i < blocks && processor && processor.onaudioprocess; i++) {
    const data = new Float32Array(4096).fill(SCENARIO === 'silent' ? 0 : 0.5);
    processor.onaudioprocess({ inputBuffer: { getChannelData: () => data } });
  }
  const heldNote = (byId.talknote || {}).textContent || '';
  const heldRec = talk.classList.contains('rec');
  clock += SCENARIO === 'short' ? 100 : 1000;
  if (SCENARIO === 'early') {
    await talk.dispatch('pointerup');     // let go while the browser asks for the microphone
    micOpen();
    await held;
  } else {
    await held;
    await talk.dispatch('pointerup');
  }
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
    heldNote: heldNote, heldRec: heldRec, boxSteps: boxSteps, warned: warned,
    noteErr: !!(byId.talknote && byId.talknote.classList.contains('err')),
  }));
}

main().catch(e => { process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) })); });
