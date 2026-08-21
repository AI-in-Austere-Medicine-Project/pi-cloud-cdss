// EdgeCDSS — client render harness.
//
// The web client is one static file with no build step and no browser in CI, so
// the only way to test its render path is to run it: this loads the real
// <script> out of index.html into a stubbed DOM and drives ask() against
// canned /query payloads, then prints what landed in the DOM as JSON.
//
// It exists because a string-grep contract test cannot catch the failure it was
// written for. v4.3 shipped a strip that called esc() with a JSON number; the
// TypeError unwound into ask()'s catch and replaced an already-rendered SEPSIS
// card with REQUEST FAILED. Every grep assertion still passed.
//
// Driven by test_client_render.py:  node client_render_harness.js static/index.html

'use strict';
const fs = require('fs');
const vm = require('vm');

const CLIENT = process.argv[2];
const SCRIPT = fs.readFileSync(CLIENT, 'utf8').split('<script>')[1].split('</script>')[0];

// ── DOM stub ────────────────────────────────────────────────────────────────
// Enough of an element to render into and read back: querySelector memoises so
// the '.bubble' the client writes to is the '.bubble' the test reads.
function el() {
  const node = {
    innerHTML: '', textContent: '', value: '', title: '', className: '',
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

// A sandbox per scenario: patientCtx is module state and must not leak between
// cases.
function load(fetchImpl) {
  const byId = {};
  const getElementById = id => (byId[id] = byId[id] || el());
  const sandbox = {
    console: { log() {}, error() {}, warn() {} },
    document: {
      getElementById,
      querySelector: () => el(),
      querySelectorAll: () => [],
      createElement: () => el(),
    },
    fetch: fetchImpl,
    setInterval: () => 0, setTimeout: (f) => { f(); return 0; },
    Audio: function () { return { play: () => Promise.resolve() }; },
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox);
  return { sandbox, byId, getElementById };
}

function jsonResponse(payload, ok) {
  return Promise.resolve({
    ok: ok !== false,
    status: ok === false ? 500 : 200,
    json: () => Promise.resolve(payload),
    blob: () => Promise.resolve({}),
  });
}

// Only /query matters here; the status and model polls fired at load are
// allowed to fail into their own catch blocks, exactly as they do offline.
function queryOnly(payload, ok) {
  return url => (String(url).indexOf('/query') === 0
    ? jsonResponse(payload, ok)
    : Promise.reject(new Error('offline')));
}

// A scenario that throws records the throw and moves on, so one broken render
// path fails one assertion instead of blanking the whole report.
async function probe(out, name, fn) {
  try { out[name] = await fn(); }
  catch (e) { out[name] = { error: String(e && e.message || e) }; }
}

async function ask(env, text) {
  env.getElementById('q').value = text;
  await vm.runInContext('ask()', env.sandbox);
  const chat = env.getElementById('chat');
  const pending = chat.children[chat.children.length - 1];
  return {
    bubble: pending ? pending.querySelector('.bubble').innerHTML : '',
    ctx: env.getElementById('ctx').innerHTML,
  };
}

// ── The response the server actually served ─────────────────────────────────
// Shape from server/logs/sessions/cdss_session_2026-08-21.jsonl, the
// "hypotensive, BP 90/30, fever 104, IV established, 75 kg" turn, brought up to
// log schema 6: the same pressure now also carries the MAP the server derives
// from it. Note the numbers: confirmed_weight_kg and every vital value are JSON
// numbers.
const SEPSIS_PAYLOAD = {
  response: '**SEPSIS**\n- Treat as suspected sepsis/septic shock.\n\n**TREAT**\n1. Oxygen, monitor, IV/IO access.',
  sources: [{ title: 'Sepsis Management CPG', page: 4, confidence: 0.62 }],
  query_type: 'chromadb',
  processing_time_ms: 1,
  voice_mode: 'brief',
  rate_limit_remaining: 999,
  validator_result: 'SAFE',
  validator_issues: [],
  model: '',
  source: 'jts',
  vitals_cautions: [],
  patient_context: {
    age_years: null,
    confirmed_weight_kg: 75.0,
    estimated_weight_kg: null,
    weight_source: 'confirmed_kg',
    sex: null,
    is_pediatric: false,
    provider_scope: 'MEDIC',
    access_state: 'CONFIRMED_IV_IO',
    route_preference: 'IV',
    pending_question: null,
    vitals: {
      sbp: { value: 90.0, unit: 'mmHg', ts: null, raw: 'blood pressure is 90/30', derived: false },
      dbp: { value: 30.0, unit: 'mmHg', ts: null, raw: 'blood pressure is 90/30', derived: false },
      map: { value: 50.0, unit: 'mmHg', ts: null, raw: 'derived from 90/30', derived: true },
    },
    vitals_superseded: [],
    vitals_rejected: [],
    boundary_reset_reason: null,
  },
};

function clone(o) { return JSON.parse(JSON.stringify(o)); }

(async () => {
  const out = {};

  // 1. esc() on everything a JSON body can hand it.
  await probe(out, 'esc', () => {
    const env = load(queryOnly(SEPSIS_PAYLOAD));
    return vm.runInContext(`({
      undef: esc(undefined), nul: esc(null), num: esc(75), float: esc(101.2),
      amp: esc('a & b'), lt: esc('<script>'), str: esc('plain')
    })`, env.sandbox);
  });
  await probe(out, 'num', () => {
    const env = load(queryOnly(SEPSIS_PAYLOAD));
    return vm.runInContext(`({
      float: num(75.0), decimal: num(101.2), nul: num(null), undef: num(undefined),
      empty: num(''), text: num('abc'), zero: num(0)
    })`, env.sandbox);
  });

  // 2. The regression: the real payload must render the answer AND the strip.
  await probe(out, 'real', () => {
    const env = load(queryOnly(SEPSIS_PAYLOAD));
    return ask(env, 'hypotensive, BP 90/30, fever 104, IV established, 75 kg');
  });

  // 3. A patient_context whose fields went missing or changed name: absent
  //    weight, a vital with no value, a vital renamed out from under the
  //    client. The answer must survive; broken chips must be omitted.
  await probe(out, 'degraded', () => {
    const p = clone(SEPSIS_PAYLOAD);
    p.patient_context.confirmed_weight_kg = undefined;
    p.patient_context.access_state = undefined;
    p.patient_context.vitals = {
      hr: {},                                     // no value, no unit, no ts
      sbp: { value: null, unit: 'mmHg' },         // value went away
      systolic_bp: { value: 90, unit: 'mmHg' },   // renamed field the client does not know
      temp: { value: 104, unit: 'F', ts: null, value_c: 40, value_f: 104 },
      map: { value: null, unit: 'mmHg' },         // derived off a pressure that went away
    };
    const env = load(queryOnly(p));
    return ask(env, 'same patient');
  });

  // 4. patient_context absent entirely — an older server, or a rollback.
  await probe(out, 'no_context', () => {
    const p = clone(SEPSIS_PAYLOAD);
    delete p.patient_context;
    delete p.sources;
    delete p.model;
    const env = load(queryOnly(p));
    return ask(env, 'same patient');
  });

  // 4b. MAP at and below the colour threshold, and with no pressure to sit
  //     beside. 65 is green — the boundary belongs to the safe side, the same
  //     way the server's caution arms strictly below it.
  function withVitals(vitals) {
    const p = clone(SEPSIS_PAYLOAD);
    p.patient_context.vitals = vitals;
    return p;
  }
  const bp = (sbp, dbp, ts) => ({
    sbp: { value: sbp, unit: 'mmHg', ts: ts || null, raw: '', derived: false },
    dbp: { value: dbp, unit: 'mmHg', ts: ts || null, raw: '', derived: false },
  });
  await probe(out, 'map_at_threshold', () => {
    // 100/48 -> (100 + 96) / 3 -> 65
    const env = load(queryOnly(withVitals(Object.assign(bp(100, 48), {
      map: { value: 65.0, unit: 'mmHg', ts: null, raw: 'derived from 100/48', derived: true },
    }))));
    return ask(env, 'same patient');
  });
  await probe(out, 'map_below_threshold', () => {
    // 100/46 -> (100 + 92) / 3 -> 64
    const env = load(queryOnly(withVitals(Object.assign(bp(100, 46), {
      map: { value: 64.0, unit: 'mmHg', ts: null, raw: 'derived from 100/46', derived: true },
    }))));
    return ask(env, 'same patient');
  });
  await probe(out, 'live_2026_08_21', () => {
    // "Ok now his pressure is getting soft 90/50", logged 14:51:31Z. The exact
    // reading, with the exact timestamp the session recorded it at.
    const env = load(queryOnly(withVitals(Object.assign(bp(90, 50), {
      map: { value: 63.0, unit: 'mmHg', ts: '2026-08-21T14:51:31.895Z',
             raw: 'derived from 90/50', derived: true },
    }))));
    return ask(env, 'Ok now his pressure is getting soft 90/50');
  });
  await probe(out, 'map_without_a_pressure', () => {
    // A stated MAP off an arterial line. Nothing to ride inside.
    const env = load(queryOnly(withVitals({
      map: { value: 70.0, unit: 'mmHg', ts: null, raw: 'map 70', derived: false },
    })));
    return ask(env, 'same patient');
  });
  await probe(out, 'map_absent', () => {
    // A schema 5 server, or a rollback: a pressure and no MAP at all.
    const env = load(queryOnly(withVitals(bp(90, 30))));
    return ask(env, 'same patient');
  });

  // 5. Belt and braces: even if the strip itself throws, the answer stays.
  await probe(out, 'strip_throws', () => {
    const env = load(queryOnly(SEPSIS_PAYLOAD));
    vm.runInContext("renderCtx = function () { throw new TypeError('s.replace is not a function'); };", env.sandbox);
    return ask(env, 'same patient');
  });

  // 6. The hardening must not swallow a real failure: an HTTP error still says
  //    REQUEST FAILED, because that one is true.
  await probe(out, 'http_error', () => {
    const env = load(queryOnly(SEPSIS_PAYLOAD, false));
    return ask(env, 'anything');
  });

  process.stdout.write(JSON.stringify(out, null, 1));
})().catch(e => {
  process.stdout.write(JSON.stringify({ harness_error: String(e && e.stack || e) }));
  process.exitCode = 1;
});
