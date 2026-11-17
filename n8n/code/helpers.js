// ===== Shared settings and helpers. build_workflow.py puts this at the top of every Code node. =====
// To change a setting: edit it here, run  .venv/bin/python n8n/build_workflow.py  and import again.

const SETTINGS = {
  testMode: true,             // true: emails are saved to the outbox page, never sent; calendar is simulated
  timezone: 'Europe/London',  // interview times are UK working hours
  workdayStartHour: 9,        // first slot starts 09:00
  workdayEndHour: 17,         // last slot must end by 17:00
  slotMinutes: 45,            // length of an interview
  slotsPerInvite: 3,          // how many times each candidate is offered
  workingDaysAhead: 5,        // offer times from the next 5 working days (Monday to Friday)
  reminderHoursBefore: 24,    // reminder email this long before the interview
  followUpAfterHours: 72,     // one polite reminder if no time is picked within 3 days
  alertRecruiterAfterHours: 120, // after 5 days with no answer, tell the recruiter (never reject automatically)
  requestMaxAgeMinutes: 10,   // an invite request older than this is refused
  baseUrl: 'http://localhost:5678/webhook/interview',
  recruiterEmail: 'recruiter@example.com',
  interviewerName: 'the People Analytics team',
};

const crypto = require('crypto');
const SECRET = $env.INTERVIEW_SECRET;  // shared with the screener app; set by start_n8n.sh, never written down here

// A signature only the screener app and this workflow can make (HMAC-SHA256 with the shared secret).
function sign(text) {
  return crypto.createHmac('sha256', SECRET).update(text).digest('hex');
}

// Compares two signatures safely (in constant time, so nobody can guess one by timing the answers).
function sameSignature(a, b) {
  a = String(a || ''); b = String(b || '');
  return a.length === b.length && a.length > 0 && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
}

// Everything the workflow remembers between runs: invites, bookings (the simulated calendar),
// the outbox (emails that would have been sent) and the audit log. n8n keeps this with the workflow.
function store() {
  const s = $getWorkflowStaticData('global');
  s.invites = s.invites || {};       // invite id -> who, which times were offered, status
  s.bookings = s.bookings || {};     // slot start time -> invite id (the simulated calendar)
  s.outbox = s.outbox || [];         // every email, in order
  s.log = s.log || [];               // every step, in order
  s.seenRequests = s.seenRequests || {};  // request ids already used (each request works once)
  return s;
}

function now() {
  return DateTime.now().setZone(SETTINGS.timezone);
}

function isoTime(dt) {
  return dt.toISO({ suppressMilliseconds: true });
}

function log(s, event, details) {
  s.log.push({ time: isoTime(now()), event, ...details });
}

// Text from a resume or a request is always escaped before it goes into a web page.
function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function slotLabel(iso) {
  return DateTime.fromISO(iso, { zone: SETTINGS.timezone }).toFormat("cccc d LLLL 'at' HH:mm");
}

// The next free interview times: Monday to Friday, within working hours, starting tomorrow.
// A time is not free if it is booked, or offered to someone who has not answered yet.
function freeSlots(s, count, from) {
  const taken = new Set(Object.keys(s.bookings));
  for (const invite of Object.values(s.invites)) {
    if (invite.status === 'invited') invite.offered.forEach(slot => taken.add(slot));
  }
  const slots = [];
  let day = from.plus({ days: 1 }).startOf('day');
  let workingDays = 0;
  while (slots.length < count && workingDays < SETTINGS.workingDaysAhead) {
    if (day.weekday <= 5) {  // 1 = Monday ... 5 = Friday
      workingDays++;
      for (let hour = SETTINGS.workdayStartHour;
           hour * 60 + SETTINGS.slotMinutes <= SETTINGS.workdayEndHour * 60 && slots.length < count; hour++) {
        const slot = isoTime(day.set({ hour }));
        if (!taken.has(slot)) slots.push(slot);
      }
    }
    day = day.plus({ days: 1 });
  }
  return slots;
}

// The link behind each time button. The signature means a link cannot be made up or changed.
function bookingLink(inviteId, slot) {
  const sig = sign(`book|${inviteId}|${slot}`);
  return `${SETTINGS.baseUrl}/book?invite=${encodeURIComponent(inviteId)}&slot=${encodeURIComponent(slot)}&sig=${sig}`;
}

// "Sends" an email. In test mode it is only saved to the outbox page and the log.
// To send for real, connect a Gmail node after the node that calls this (see n8n/README.md).
function deliver(s, email) {
  const message = { id: `email-${s.outbox.length + 1}`, created: isoTime(now()), sent: !SETTINGS.testMode, ...email };
  s.outbox.push(message);
  log(s, SETTINGS.testMode ? 'email_saved_to_outbox' : 'email_sent', { to: email.to, subject: email.subject, kind: email.kind });
  return message;
}

// The time buttons in an invite or follow-up email, as plain text and as a small web page.
function slotButtons(invite) {
  return invite.offered.map(slot => ({ label: slotLabel(slot), link: bookingLink(invite.id, slot) }));
}

function page(title, body) {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title><style>
body{font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#f5f9ff;color:#14315c;max-width:760px;margin:32px auto;padding:0 16px;line-height:1.5}
h1{font-size:1.5rem} .card{background:#fff;border:1px solid #d6e2f5;border-radius:12px;padding:16px 20px;margin:14px 0}
a.button{display:inline-block;background:#1f5fd6;color:#fff;text-decoration:none;padding:8px 14px;border-radius:8px;margin:4px 6px 4px 0}
.muted{color:#5b7299;font-size:.9rem} .tag{background:#e6efff;border-radius:6px;padding:2px 8px;font-size:.8rem}
table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #d6e2f5;padding:6px;text-align:left}
</style></head><body>${body}</body></html>`;
}
// ===== end of shared helpers =====
