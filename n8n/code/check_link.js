// Booking step 1: is this a genuine link from one of our emails?
// The signature covers the invite and the time, so changing either makes the link invalid.
const s = store();
const q = $input.first().json.query || {};
const genuine = q.invite && q.slot && sameSignature(sign(`book|${q.invite}|${q.slot}`), q.sig) && s.invites[q.invite];
if (!genuine) {
  log(s, 'booking_link_refused', { invite: q.invite || null });
  return [{ json: { ok: false, html: page('Link not valid', '<h1>This link is not valid</h1>' +
    '<p>It may have been changed or copied wrongly. Please use the buttons in your invitation email.</p>') } }];
}
return [{ json: { ok: true, invite_id: q.invite, slot: q.slot } }];
