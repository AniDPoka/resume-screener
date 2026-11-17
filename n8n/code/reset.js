// Test mode only: empty the outbox, calendar, invites and log, for a fresh demo.
// Needs a signed link (made by n8n/try_flow.py), so nobody else can wipe it.
const s = store();
const q = $input.first().json.query || {};
if (!SETTINGS.testMode || !sameSignature(sign(`reset|${q.at}`), q.sig) ||
    Math.abs(now().diff(DateTime.fromISO(q.at || ''), 'minutes').minutes) > SETTINGS.requestMaxAgeMinutes) {
  return [{ json: { ok: false, reason: 'Reset refused.' } }];
}
for (const key of ['invites', 'bookings', 'outbox', 'log', 'seenRequests']) delete s[key];
return [{ json: { ok: true, reason: 'Everything was cleared.' } }];
