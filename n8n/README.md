# Interview scheduling with n8n

After the screener ranks candidates, **a recruiter decides who to interview**. One click in the app then
hands those people to an n8n workflow, which does the paperwork: invite emails with 3 interview times,
booking, confirmation, a reminder the day before, one follow-up, and a note to the recruiter if someone
never answers. **Nothing tells anyone "no" automatically.**

```
Screener app (your Mac)                 n8n workflow (your Mac)
──────────────────────                  ───────────────────────────────────────────────────────
Recruiter ticks candidates  ──signed──► 1. Invites: check the request is genuine, hold 3 free times
and clicks "Send invites"     request      per person (no overlaps), write the invite emails
                                        2. Booking: candidate clicks a time (signed link), the time is
                                           booked, a confirmation is written; if it was just taken,
                                           3 new times are offered
                                        3. Every 15 minutes: reminder 24 h before, one follow-up after
                                           3 days, a note to the recruiter after 5 days
                                        4. Pages: /outbox (emails + calendar), /log (audit log)
```

## Test mode (how it ships)

The candidates are made up, so **no email is ever sent**: every email is saved to the **outbox** page,
and the calendar is **simulated**. The time buttons in the outbox work exactly like they would in a real
email, so you can act as the candidate and watch the whole flow.

## Safety, in plain words

- **Only the recruiter's click starts it.** The app signs each request with a secret shared only with
  n8n (`N8N_SECRET` in `.streamlit/secrets.toml`, never committed). Unsigned, old (over 10 minutes) or
  repeated requests are refused.
- **Only what's needed leaves the screener:** name, email and job title. Scores, flags and the AI's
  reasons stay in the app.
- **Booking links are signed**, so a candidate cannot edit a link to take someone else's time.
- **Nobody is invited twice**, and two people are never offered the same time.
- **No automatic rejections.** The workflow only writes: invite, new times, confirmation, reminder,
  follow-up, and a note to the recruiter (`tests.py` checks this list).

## Run it

Node.js 24 and n8n 2.48.4 were installed for this project in `~/.local` (n8n's data is in
`~/.local/n8n-data`). To remove them, delete `~/.local/node`, `~/.local/node-v24*`, `~/.local/n8n-app`
and `~/.local/n8n-data`.

1. Start n8n (leave this Terminal window open):
   ```bash
   cd ~/Documents/resume-screener && sh n8n/start_n8n.sh
   ```
2. In a second Terminal window, start the app:
   ```bash
   cd ~/Documents/resume-screener && .venv/bin/streamlit run app.py
   ```
3. On the **Shortlist** tab, scroll to **Send interview invites (n8n)**, pick candidates, click **Send invites**.
4. Click **Open the n8n outbox**, then click a time button to act as the candidate.
5. To see the workflow itself, open http://localhost:5678. The first time, n8n asks you to create an
   owner account for this Mac (only you can see it).

Check every step automatically (needs n8n running; it clears the test data first):
```bash
cd ~/Documents/resume-screener && .venv/bin/python n8n/try_flow.py
```

## Change it

The workflow is built from readable files in `n8n/code/` (one per step; `helpers.js` holds the
settings: working hours, interview length, reminder and follow-up times). After a change:
stop n8n (Ctrl+C), run `sh n8n/load_workflow.sh`, start n8n again. Reloading clears the test data.

## Going live later (not built yet)

To send real emails and use a real calendar you would: set `testMode: false` in `helpers.js`; in n8n,
connect a Gmail account and add a **Gmail** node after "Write and save invite emails" and after "Book it
or offer new times"; add a **Google Calendar** node that creates the event (with a Meet link); and run
n8n somewhere that is always on with a public address, so candidates' clicks can reach it. Real
candidates also need to be told how their data is used, and the hiring laws in the main README apply.

## Limits

- Runs only while your Mac is on; the public Streamlit app has no invite box.
- The "time was just taken" path only happens if two clicks race; it is in the workflow but the test
  script cannot trigger it, because the workflow never offers the same time to two people.
- Times are offered on the hour, Monday to Friday, UK time; bank holidays are not skipped.
