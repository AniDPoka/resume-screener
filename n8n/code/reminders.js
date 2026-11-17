// Every 15 minutes: send reminders and follow-ups. Nobody is ever rejected here.
// - 24 hours before a booked interview: a reminder to the candidate
// - no time picked after 3 days: one polite follow-up with the same times
// - still nothing after 5 days: a note to the recruiter, who decides what to do
// In test mode the "Run checks" link can pretend it is later (?hours_later=48), so this can be tried now.
const s = store();
const q = ($input.first().json || {}).query || {};
const later = SETTINGS.testMode ? Number(q.hours_later || 0) : 0;
const at = now().plus({ hours: later });
const done = [];

for (const invite of Object.values(s.invites)) {
  if (invite.status === 'booked' && !invite.reminded) {
    const start = DateTime.fromISO(invite.slot, { zone: SETTINGS.timezone });
    const hoursToGo = start.diff(at, 'hours').hours;
    if (hoursToGo > 0 && hoursToGo <= SETTINGS.reminderHoursBefore) {
      deliver(s, { kind: 'reminder', to: invite.email, invite: invite.id, subject: `Reminder: interview ${slotLabel(invite.slot)}`,
                   text: `Dear ${invite.name},\n\nA reminder that your interview is on ${slotLabel(invite.slot)}.\n\nKind regards,\nRecruitment team` });
      invite.reminded = true;
      done.push(`reminder to ${invite.name}`);
    }
  }
  if (invite.status === 'invited') {
    const waited = at.diff(DateTime.fromISO(invite.invited_at), 'hours').hours;
    if (waited >= SETTINGS.followUpAfterHours && !invite.followed_up) {
      deliver(s, { kind: 'follow_up', to: invite.email, invite: invite.id, subject: `Interview times still available: ${invite.role}`,
                   text: `Dear ${invite.name},\n\nJust checking you saw our invitation. These times are still held for you:\n` +
                         slotButtons(invite).map(b => `- ${b.label}`).join('\n') + `\n\nKind regards,\nRecruitment team`,
                   buttons: slotButtons(invite) });
      invite.followed_up = true;
      done.push(`follow-up to ${invite.name}`);
    }
    if (waited >= SETTINGS.alertRecruiterAfterHours && !invite.recruiter_alerted) {
      deliver(s, { kind: 'recruiter_alert', to: SETTINGS.recruiterEmail, invite: invite.id,
                   subject: `No answer from ${invite.name}`,
                   text: `${invite.name} has not picked an interview time after ${SETTINGS.alertRecruiterAfterHours / 24} days ` +
                         `and one follow-up. Please decide whether to call, wait, or close this invitation.` });
      invite.recruiter_alerted = true;
      done.push(`recruiter told about ${invite.name}`);
    }
  }
}
log(s, 'checks_ran', { pretend_hours_later: later, actions: done });
return [{ json: { ok: true, pretend_hours_later: later, actions: done } }];
