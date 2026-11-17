// Step 1 of the invite flow: is this request genuine?
// It must be signed with the shared secret, be less than 10 minutes old, and not have been used before.
const s = store();
const incoming = $input.first().json.body || {};
const fail = reason => {
  log(s, 'invite_request_refused', { reason });
  return [{ json: { ok: false, reason } }];
};

if (!SECRET) return fail('The workflow has no secret set (start n8n with n8n/start_n8n.sh).');
if (typeof incoming.body !== 'string' || !sameSignature(sign(incoming.body), incoming.signature)) {
  return fail('The signature does not match, so this did not come from the screener app.');
}
const request = JSON.parse(incoming.body);
const age = now().diff(DateTime.fromISO(request.sent_at), 'minutes').minutes;
if (!(age >= -2 && age <= SETTINGS.requestMaxAgeMinutes)) return fail('The request is too old (or its time is wrong).');
if (s.seenRequests[request.request_id]) return fail('This request was already used.');
s.seenRequests[request.request_id] = isoTime(now());
if (!Array.isArray(request.candidates) || request.candidates.length === 0) return fail('No candidates in the request.');

log(s, 'invite_request_accepted', { request_id: request.request_id, role: request.role, candidates: request.candidates.length });
return [{ json: { ok: true, request } }];
