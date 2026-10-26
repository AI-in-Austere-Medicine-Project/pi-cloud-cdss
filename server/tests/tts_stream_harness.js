// V3 — the portal's listen path, streamed sentence by sentence.
//
// Loads the real <script> out of index.html into a stubbed DOM (as
// tts_timing_harness.js does), with a stub Web Audio and a /speak whose body
// arrives in pieces that cut across frame boundaries. Prints what was
// requested, what was scheduled to play and when, and the timing record, as
// JSON. Driven by test_v3_voice.py:
//   node tts_stream_harness.js static/index.html [error]

'use strict';
const fs = require('fs');
const vm = require('vm');

const SCRIPT = fs.readFileSync(process.argv[2], 'utf8').split('<script>')[1].split('</script>')[0];
const WITH_ERROR = process.argv[3] === 'error';

function el() {
  const node = {
    innerHTML: '', textContent: '', value: 'tok', title: '', className: '',
    style: {}, dataset: {}, disabled: false, checked: true,
    scrollTop: 0, scrollHeight: 0, children: [], _q: {},
    appendChild(c) { node.children.push(c); return c; },
    querySelector(sel) { return (node._q[sel] = node._q[sel] || el()); },
    querySelectorAll() { return []; },
    addEventListener() {}, removeEventListener() {},
    closest() { return el(); }, remove() {}, focus() {}, blur() {},
  };
  return node;
}

function frame(kind, bytes) {
  const out = new Uint8Array(5 + bytes.length);
  out[0] = kind.charCodeAt(0);
  out[1] = (bytes.length >>> 24) & 255; out[2] = (bytes.length >>> 16) & 255;
  out[3] = (bytes.length >>> 8) & 255; out[4] = bytes.length & 255;
  out.set(bytes, 5);
  return out;
}

async function main() {
  const calls = [];
  const started = [];
  let clock = 1000;
  // Two sentences, then (optionally) an error frame. The "WAV" bodies carry
  // their duration in seconds as their first byte, for the stub decoder.
  const parts = [frame('A', Uint8Array.from([2, 9, 9])), frame('A', Uint8Array.from([3, 9]))];
  if (WITH_ERROR) parts.push(frame('E', Buffer.from('local voice failed (boom)')));
  const whole = Buffer.concat(parts.map(p => Buffer.from(p)));
  // Delivered in 4-byte pieces: every frame header is split across reads.
  const pieces = [];
  for (let i = 0; i < whole.length; i += 4) pieces.push(new Uint8Array(whole.subarray(i, i + 4)));

  function AudioContext() {
    const ctx = {
      get currentTime() { return clock / 1000; },
      destination: {},
      resume() { return Promise.resolve(); },
      close() {},
      decodeAudioData(ab) { return Promise.resolve({ duration: new Uint8Array(ab)[0] }); },
      createBufferSource() {
        const src = {
          buffer: null, connect() {},
          start(at) { started.push({ at: at, duration: src.buffer.duration, clock: clock }); },
        };
        Object.defineProperty(src, 'onended', { set(f) { clock += 5000; f(); } });
        return src;
      },
    };
    return ctx;
  }
  const byId = {};
  const sandbox = {
    console: { log() {}, error() {}, warn() {} },
    document: {
      getElementById: id => (byId[id] = byId[id] || el()),
      querySelector: () => el(), querySelectorAll: () => [], createElement: () => el(),
    },
    performance: { now: () => clock },
    fetch: (url, opts) => {
      calls.push({ url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null });
      if (String(url) === '/speak') {
        clock += 120;
        let i = 0;
        return Promise.resolve({
          ok: true, status: 200,
          headers: { get: h => (h.toLowerCase() === 'x-synth-ms' ? '110' : null) },
          body: { getReader: () => ({
            read: () => { clock += 10; return Promise.resolve(
              i < pieces.length ? { done: false, value: pieces[i++] } : { done: true }); },
          }) },
        });
      }
      if (String(url) === '/speak/timing') return Promise.resolve({ ok: true, status: 200 });
      return Promise.reject(new Error('offline'));
    },
    setInterval: () => 0, setTimeout: (f) => { f(); return 0; },
    AudioContext,
    ReadableStream: function () {},
    TextDecoder,
    Uint8Array,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
    sessionStorage: { getItem: () => 's-1', setItem() {} },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox);
  const btn = el();
  await sandbox.speak('Give fentanyl 50 mcg IV. Reassess.', btn, 'jts', '', 'q-7');
  await new Promise(r => setImmediate(r));
  process.stdout.write(JSON.stringify({
    calls: calls.filter(c => c.url.indexOf('/speak') === 0), started: started,
    button: btn.textContent, title: btn.title }));
}

main().catch(e => { process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) })); });
