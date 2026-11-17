// Step 2: for each approved candidate, hold 3 free interview times.
// Each candidate gets different times, so two people are never offered the same slot.
// Someone already invited or booked is skipped, so nobody gets two invites.
const s = store();
const { request } = $input.first().json;
const results = [];
for (const c of request.candidates) {
  const already = Object.values(s.invites).find(i => i.email === c.email && i.status !== 'closed');
  if (already) {
    log(s, 'candidate_skipped', { name: c.name, reason: `already ${already.status}` });
    results.push({ json: { name: c.name, skipped: `already ${already.status}` } });
    continue;
  }
  const offered = freeSlots(s, SETTINGS.slotsPerInvite, now());
  if (offered.length < SETTINGS.slotsPerInvite) {
    log(s, 'candidate_skipped', { name: c.name, reason: 'not enough free times in the next working days' });
    results.push({ json: { name: c.name, skipped: 'not enough free times' } });
    continue;
  }
  const id = `inv-${request.request_id.slice(0, 8)}-${c.id}`;
  s.invites[id] = {
    id, candidate_id: c.id, name: c.name, email: c.email, role: request.role,
    offered, status: 'invited', invited_at: isoTime(now()),
    followed_up: false, recruiter_alerted: false,
  };
  log(s, 'slots_offered', { invite: id, name: c.name, offered });
  results.push({ json: { invite_id: id, name: c.name } });
}
return results;
