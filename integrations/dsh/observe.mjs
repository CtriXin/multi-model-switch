// Request metadata only. Never record headers, prompt bodies, or credentials.
import { appendFileSync, readFileSync } from 'node:fs';
const file = process.env.MMS_DSH_ROUTES;
if (file) {
  const metadata = JSON.parse(readFileSync(file, 'utf8'));
  const upstreamFetch = globalThis.fetch;
  globalThis.fetch = async function(input, init) {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url);
    const candidates = metadata.routes.filter(r => {
      const base = new URL(r.base_url);
      const suffix = r.protocol === 'anthropic_messages' ? '/v1/messages'
        : r.protocol === 'openai_responses' ? '/responses' : '/chat/completions';
      return url.origin === base.origin && url.pathname === base.pathname.replace(/\/$/, '') + suffix;
    });
    if (!candidates.length) return upstreamFetch(input, init);
    let body;
    try { body = JSON.parse(init?.body ?? 'null'); } catch { /* no payload logging */ }
    const exact = candidates.find(r => r.model === body?.model);
    const evidence = {schema: 'cache_transport_evidence.v1', timestamp: new Date().toISOString(),
      route_source: metadata.route_source, component_revisions: metadata.revisions,
      provider_id: exact?.provider_id ?? null, model_id: body?.model ?? null,
      request_url: url.origin + url.pathname, request_path: url.pathname,
      protocol: candidates[0].protocol, fallback_reason: exact?.fallback_reason ?? '',
      reasoning_effort: body?.reasoning_effort ?? body?.reasoning?.effort ?? body?.output_config?.effort ?? null,
      thinking_type: body?.thinking?.type ?? null, thinking_budget_tokens: body?.thinking?.budget_tokens ?? null};
    try {
      const response = await upstreamFetch(input, init);
      appendFileSync(process.env.MMS_DSH_EVIDENCE, JSON.stringify({...evidence, status: response.status}) + '\n', {mode: 0o600});
      return response;
    } catch (error) {
      appendFileSync(process.env.MMS_DSH_EVIDENCE, JSON.stringify({...evidence, error: 'transport_failed'}) + '\n', {mode: 0o600});
      throw error;
    }
  };
}
