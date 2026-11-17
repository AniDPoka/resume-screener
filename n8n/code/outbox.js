// The outbox page: every email the workflow wrote (in test mode, instead of sending it), newest first,
// plus the simulated calendar. Clicking a time button here does exactly what it would do in a real email.
const s = store();
const calendar = Object.entries(s.bookings).sort().map(([slot, id]) =>
  `<tr><td>${esc(slotLabel(slot))}</td><td>${esc(s.invites[id].name)}</td><td>${esc(s.invites[id].role)}</td></tr>`).join('');
const emails = [...s.outbox].reverse().map(m => `<div class="card">
  <div class="muted">${esc(DateTime.fromISO(m.created).setZone(SETTINGS.timezone).toFormat('d LLL yyyy, HH:mm'))} · to ${esc(m.to)} · <span class="tag">${esc(m.kind)}</span>${m.sent ? '' : ' · <span class="tag">test mode: not sent</span>'}</div>
  <h3>${esc(m.subject)}</h3><div>${esc(m.text).replace(/\n/g, '<br>')}</div>
  ${(m.buttons || []).map(b => `<a class="button" href="${esc(b.link)}">${esc(b.label)}</a>`).join('')}
</div>`).join('');
const html = page('Interview outbox', `<h1>Interview outbox</h1>
<p class="muted">${SETTINGS.testMode ? 'Test mode: these emails were saved here instead of being sent. ' +
  'Click a time button to act as the candidate.' : 'Emails sent by the workflow.'}</p>
<h2>Calendar${SETTINGS.testMode ? ' (simulated)' : ''}</h2>
${calendar ? `<table><tr><th>When</th><th>Candidate</th><th>Role</th></tr>${calendar}</table>` : '<p class="muted">Nothing booked yet.</p>'}
<h2>Emails (${s.outbox.length})</h2>${emails || '<p class="muted">No emails yet.</p>'}`);
return [{ json: { html } }];
