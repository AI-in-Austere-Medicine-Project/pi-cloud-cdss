// The teach page's recorder (owner, 2026-11-23): tap a word, say it, it stops by itself
// after a short silence or on a second tap; the microphone is asked for once.
//
// Loads the real <script> out of pocket_teach.html into a stubbed DOM with a stub
// microphone (getUserMedia counted, a 48 kHz AudioContext whose script processor the
// harness drives on a fake clock) and stub /pocket/teach endpoints. Prints, as JSON,
// every clip sent, how often the microphone was asked for, and the status line.
//   node teach_page_harness.js static/pocket_teach.html <scenario>
// Scenarios: silence, second_tap, two_words, nothing, done, busy_other.
'use strict';
const fs = require('fs');
const vm = require('vm');

const SCRIPT = fs.readFileSync(process.argv[2], 'utf8').split('<script>')[1].split('</script>')[0];
const SCENARIO = process.argv[3] || 'silence';
const RATE = 48000, CHUNK = 2048, CHUNK_MS = 1000 * CHUNK / RATE;

function el(id) {
  return {
    id, innerHTML: '', textContent: '', value: '', className: '', style: {}, dataset: {},
    _on: {}, addEventListener(t, f) { this._on[t] = f; },
    querySelector() { return { style: {} }; },
    classList: { add() {}, remove() {} },
  };
}
const els = {};
const document = {
  getElementById(id) { return els[id] || (els[id] = el(id)); },
  querySelectorAll() { return []; },
};
let clock = 1000, micAsks = 0, node = null;
const sent = [];
const WORDS = [
  { id: 'drug-ketamine', kind: 'drug', say: 'ketamine', show: 'ketamine', group: 'drugs', primary: true, recorded: [] },
  { id: 'control-no', kind: 'control', say: 'no', show: 'no', group: 'commands', recorded: [] },
  { id: 'medic-narcan', kind: 'medic', say: 'narcan', show: 'narcan', group: 'drugs', primary: false, recorded: [1, 2, 3] },
];
function json(body) { return { ok: true, status: 200, json: async () => body }; }
async function fetch(url, opts) {
  if (url.startsWith('/pocket/teach/hello')) return json({ role: 'contributor', speaker: 'speaker-2', speaker_key: 'k' });
  if (url.startsWith('/pocket/teach/words')) return json({ words: JSON.parse(JSON.stringify(WORDS)), takes: 3, pocket_commit: 'abc', bank_version: 'v' });
  if (url.startsWith('/pocket/teach/clip')) {
    const q = new URLSearchParams(url.split('?')[1]);
    const body = opts.body;
    const samples = (body.length - 44) / 2;
    sent.push({ word_id: q.get('word_id'), take: Number(q.get('take')), seconds: +(samples / 16000).toFixed(2) });
    return json({ take: Number(q.get('take')), pocket: { heard: 'heard it' }, as_itself: true });
  }
  return { ok: false, status: 404, json: async () => ({}) };
}
class AudioContext {
  constructor() { this.sampleRate = RATE; this.state = 'running'; }
  createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  createScriptProcessor() { node = { connect() {}, disconnect() {} }; return node; }
  get destination() { return {}; }
  resume() { return Promise.resolve(); }
}
const ctx = {
  document, fetch, AudioContext, console, URLSearchParams, setTimeout, Promise,
  performance: { now: () => clock },
  localStorage: { getItem: () => 'pw', setItem() {} },
  navigator: { mediaDevices: { getUserMedia: async () => { micAsks++; return { getTracks: () => [] }; } } },
};
ctx.window = ctx; ctx.window.isSecureContext = true;
vm.createContext(ctx);
vm.runInContext(SCRIPT, ctx);
const tick = () => new Promise(r => setImmediate(r));

async function feed(ms, level) {
  const n = Math.ceil(ms / CHUNK_MS);
  for (let k = 0; k < n; k++) {
    clock += CHUNK_MS;
    const c = new Float32Array(CHUNK).fill(level);
    node.onaudioprocess({ inputBuffer: { getChannelData: () => c } });
    await tick();
  }
}
async function settle() { for (let k = 0; k < 20; k++) await tick(); }

(async () => {
  await ctx.load(); await settle();
  await feed(200, 0.001);                               // the microphone is open and idle
  const t = i => { ctx.tap(i); };
  if (SCENARIO === 'silence') {
    t(0); await feed(500, 0.3); await feed(900, 0.001); await settle();
  } else if (SCENARIO === 'second_tap') {
    t(0); await feed(500, 0.3); t(0); await settle();
  } else if (SCENARIO === 'two_words') {
    t(0); await feed(400, 0.3); await feed(800, 0.001); await settle();
    t(1); await feed(400, 0.3); await feed(800, 0.001); await settle();
    t(0); await feed(400, 0.3); await feed(800, 0.001); await settle();
  } else if (SCENARIO === 'nothing') {
    t(0); await feed(4200, 0.001); await settle();
  } else if (SCENARIO === 'done') {
    t(2); await feed(500, 0.3); await feed(900, 0.001); await settle();
  } else if (SCENARIO === 'busy_other') {
    t(0); await feed(300, 0.3); t(1); await feed(900, 0.001); await settle();
  }
  process.stdout.write(JSON.stringify({ sent, micAsks, note: els.note.textContent, progress: els.progress.textContent }));
})();
