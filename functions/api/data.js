// Daily Tracker sync endpoint for Option 2 (Cloudflare Pages + KV, behind Access). See docs/DEPLOYMENT.md §3.
// GET returns the data, PUT replaces it. The whole data set is one KV value, plus a daily snapshot kept 90 days.

const JSON_HEADERS = { 'content-type': 'application/json', 'cache-control': 'no-store' };
const MAX_BODY = 10 * 1024 * 1024;

export async function onRequestGet({ env }) {
  return new Response(await env.KV.get('data') ?? '{}', { headers: JSON_HEADERS });
}

export async function onRequestPut({ request, env }) {
  const text = await request.text();
  if (text.length > MAX_BODY) return new Response(null, { status: 413 });
  let data;
  try { data = JSON.parse(text); } catch { data = null; }
  if (!data || typeof data !== 'object' || Array.isArray(data))
    return new Response('{"error":"body must be a JSON object"}', { status: 400, headers: JSON_HEADERS });
  await env.KV.put('data', text);
  await env.KV.put(`backup:${new Date().toISOString().slice(0, 10)}`, text,
                   { expirationTtl: 60 * 60 * 24 * 90 });   // last version of each day (UTC), kept 90 days
  return new Response(null, { status: 204 });
}
