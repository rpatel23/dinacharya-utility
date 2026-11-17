// Test for functions/api/data.js (Option 2) against an in-memory KV. Run: node tests/cf_function_test.mjs
import { onRequestGet, onRequestPut } from '../functions/api/data.js';

const check = (cond, msg) => { if (!cond) throw new Error('FAIL: ' + msg); console.log('ok  ', msg); };
const store = new Map(), puts = [];
const env = { KV: {
  get: async k => store.has(k) ? store.get(k) : null,
  put: async (k, v, opts) => { store.set(k, v); puts.push({ k, opts }); },
} };
const put = body => onRequestPut({ env, request: new Request('https://x/api/data', { method: 'PUT', body }) });

let r = await onRequestGet({ env });
check(r.status === 200 && await r.text() === '{}', 'GET starts as {}');
check(r.headers.get('cache-control') === 'no-store' && r.headers.get('content-type') === 'application/json', 'GET is JSON, never cached');

const doc = JSON.stringify({ app: 'daily-tracker', version: 3, days: { '2026-11-17': { v: { nasya: { n: 1, t: 5 } } } } });
r = await put(doc);
check(r.status === 204, 'PUT stores the data');
check(await (await onRequestGet({ env })).text() === doc, 'GET returns what was PUT');
const day = new Date().toISOString().slice(0, 10);
const snap = puts.find(p => p.k === `backup:${day}`);
check(snap && store.get(`backup:${day}`) === doc && snap.opts.expirationTtl === 7776000, 'daily snapshot kept 90 days');

for (const bad of ['not json', '[1,2]', '"text"', 'null']) {
  r = await put(bad);
  check(r.status === 400, `rejects body ${bad}`);
}
check(store.get('data') === doc, 'rejected PUTs leave the data unchanged');
