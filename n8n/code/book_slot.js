// Booking step 2: book the chosen time, or explain what happened.
// - already booked: show the existing booking (clicking twice is harmless)
// - the time was just taken by someone else: offer 3 new times by email
// - otherwise: put it in the calendar, send a confirmation, and show "You're booked"
const s = store();
const { invite_id, slot } = $input.first().json;
const invite = s.invites[invite_id];
let html;

if (invite.status === 'booked') {
  html = page('Already booked', `<h1>You're already booked</h1><div class="card">Your interview is on <b>${esc(slotLabel(invite.slot))}</b>.</div>`);
} else if (!invite.offered.includes(slot)) {
  html = page('Time not offered', '<h1>That time was not offered to you</h1><p>Please use the buttons in your latest email.</p>');
} else if (s.bookings[slot]) {
  // Someone else booked this time a moment ago: offer fresh times.
  invite.offered = freeSlots(s, SETTINGS.slotsPerInvite, now());  // the old times are given up
  log(s, 'slot_clash', { invite: invite.id, name: invite.name, wanted: slot, new_offer: invite.offered });
  deliver(s, {
    kind: 'new_times', to: invite.email, invite: invite.id, subject: `New interview times: ${invite.role}`,
    text: `Dear ${invite.name},\n\nSorry, the time you chose was taken just before you clicked. Here are new times:\n` +
          slotButtons(invite).map(b => `- ${b.label}`).join('\n') + `\n\nKind regards,\nRecruitment team`,
    buttons: slotButtons(invite),
  });
  html = page('Time just taken', '<h1>Sorry, that time was just taken</h1><p>We have emailed you three new times.</p>');
} else {
  s.bookings[slot] = invite.id;           // the simulated calendar
  invite.status = 'booked';
  invite.slot = slot;
  invite.booked_at = isoTime(now());
  invite.reminded = false;
  const end = DateTime.fromISO(slot, { zone: SETTINGS.timezone }).plus({ minutes: SETTINGS.slotMinutes });
  log(s, 'calendar_event_created', { invite: invite.id, name: invite.name, start: slot, end: isoTime(end),
                                     calendar: SETTINGS.testMode ? 'simulated' : 'Google Calendar' });
  deliver(s, {
    kind: 'confirmation', to: invite.email, invite: invite.id, subject: `Interview confirmed: ${invite.role}`,
    text: `Dear ${invite.name},\n\nYour interview is confirmed for ${slotLabel(slot)} (${SETTINGS.slotMinutes} minutes, ` +
          `UK time). The video link will be in the calendar invitation.\n\nKind regards,\nRecruitment team`,
  });
  html = page('Interview booked', `<h1>You're booked</h1><div class="card">Your interview is on <b>${esc(slotLabel(slot))}</b>` +
              ` (${SETTINGS.slotMinutes} minutes, UK time). A confirmation email is on its way.</div>`);
}
return [{ json: { html } }];
