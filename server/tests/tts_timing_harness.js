// V1 — the portal's listen path, timed.
//
// Loads the real <script> out of index.html into a stubbed DOM (as
// client_render_harness.js does), calls speak() against a stubbed /speak and
// an Audio stub that plays and ends, and prints every request the client made
// as JSON. Driven by test_v1_latency.py:
//   node tts_timing_harness.js static/index.html

'use strict';
const fs = require('fs');
const vm = require('vm');

const SCRIPT = fs.readFileSync(process.argv[2], 'utf8').split('<script>')[1].split('</script>')[0];

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

async function main() {
  const calls = [];
  let clock = 1000;
  const audios = [];
  function Audio() {
    const a = {
      handlers: {},
      addEventListener(name, f) { (a.handlers[name] = a.handlers[name] || []).push(f); },
      play() {
        clock += 40;
        (a.handlers.playing || []).forEach(f => f());
        clock += 900;
        (a.handlers.ended || []).forEach(f => f());
        if (a.onended) a.onended();
        return Promise.resolve();
      },
    };
    audios.push(a);
    return a;
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
        clock += 250;
        return Promise.resolve({
          ok: true, status: 200,
          headers: { get: h => (h.toLowerCase() === 'x-synth-ms' ? '180' : null) },
          blob: () => { clock += 10; return Promise.resolve({}); },
        });
      }
      if (String(url) === '/speak/timing') return Promise.resolve({ ok: true, status: 200 });
      return Promise.reject(new Error('offline'));
    },
    setInterval: () => 0, setTimeout: (f) => { f(); return 0; },
    Audio,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
    sessionStorage: { getItem: () => 's-1', setItem() {} },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox);
  const btn = el();
  await sandbox.speak('Give fentanyl 50 mcg IV.', btn, 'jts', 'fentanyl 50 mcg IV', 'q-42');
  await new Promise(r => setImmediate(r));
  process.stdout.write(JSON.stringify(calls.filter(c => c.url.indexOf('/speak') === 0)));
}

main().catch(e => { process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) })); });
