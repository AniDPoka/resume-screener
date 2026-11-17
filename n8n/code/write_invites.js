// Step 3: write each invite email with its 3 time buttons, and "send" it
// (in test mode: save it to the outbox page). Then answer the screener app.
const s = store();
const invited = [], skipped = [];
for (const item of $input.all()) {
  if (item.json.skipped) { skipped.push({ name: item.json.name, reason: item.json.skipped }); continue; }
  const invite = s.invites[item.json.invite_id];
  const buttons = slotButtons(invite);
  deliver(s, {
    kind: 'invite', to: invite.email, invite: invite.id,
    subject: `Interview invitation: ${invite.role}`,
    text: `Dear ${invite.name},\n\nThank you for applying for the ${invite.role} role. We would like to invite you ` +
          `to a ${SETTINGS.slotMinutes}-minute video interview with ${SETTINGS.interviewerName}.\n\n` +
          `Please choose one of these times:\n` + buttons.map(b => `- ${b.label}`).join('\n') +
          `\n\nIf none of these suit you, just reply and we will find another time.\n\nKind regards,\nRecruitment team`,
    buttons,
  });
  invited.push(invite.name);
}
return [{ json: { ok: true, invited, skipped, outbox: `${SETTINGS.baseUrl}/outbox`, test_mode: SETTINGS.testMode } }];
