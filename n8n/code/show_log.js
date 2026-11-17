// The audit log: every step the workflow took, in order (no secrets are ever written to it).
const s = store();
return [{ json: { log: s.log, invites: Object.values(s.invites), calendar: s.bookings } }];
