# Job Search Agent

A script that pulls job listings from Adzuna, Greenhouse, and Lever,
scores each one against your resume using the Claude API, and can run
on a schedule with results emailed to you.

## 1. Install dependencies

```
pip install -r requirements.txt --break-system-packages
```

## 2. Get API keys

- **Adzuna**: free, ~2 minutes. https://developer.adzuna.com/ → gives you `app_id` and `app_key`.
- **Anthropic**: your existing `ANTHROPIC_API_KEY`.

## 3. Set up secrets with a `.env` file

Cron doesn't inherit your shell's environment variables, so secrets
go in a `.env` file instead of `export`.

```
cp .env.example .env
```

Then edit `.env` and fill in real values:

```
ANTHROPIC_API_KEY=sk-ant-...
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...

# Only needed if you turn on email (step 5):
EMAIL_FROM=you@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_TO=you@gmail.com
```

`.env` stays local to this folder and is only read by `run_job_agent.sh` —
never commit or share it.

## 4. Add your resume and configure search

Put your resume in this folder (`resume.pdf`, `resume.docx`, or `resume.txt`),
then open `job_agent.py` and edit the `CONFIG` dict:

- `resume_path` — your resume filename
- `adzuna.what` / `adzuna.where` — search keywords and location
- `greenhouse_companies` / `lever_companies` — company slugs to watch directly
  (e.g. `boards.greenhouse.io/stripe` → `"stripe"`)
- `min_score_to_show` — only surface matches at or above this (0–100)

Test it manually before scheduling:

```
python3 job_agent.py
```

## 5. Turn on email delivery

Gmail is the easiest option (works with any provider that supports SMTP,
just change `smtp_host`/`smtp_port`):

1. Generate a Gmail **App Password** (not your normal password):
   https://myaccount.google.com/apppasswords — requires 2FA enabled.
2. Add `EMAIL_FROM`, `EMAIL_PASSWORD`, `EMAIL_TO` to your `.env` file.
3. In `job_agent.py`, set:
   ```python
   "email": {
       "enabled": True,
       ...
   }
   ```

Run `python3 job_agent.py` again — you should get an email with any
matches above your threshold. If nothing arrives, check `run.log`
(once scheduled) or the console output for `Email: failed to send`.

**Not using Gmail?** Common SMTP settings:

| Provider | `smtp_host` | `smtp_port` |
|---|---|---|
| Gmail | smtp.gmail.com | 587 |
| Outlook/Office365 | smtp.office365.com | 587 |
| Yahoo | smtp.mail.yahoo.com | 587 |

## 6. Schedule it with cron

`run_job_agent.sh` is a wrapper that loads `.env`, runs the script, and
logs output to `run.log` — use this instead of calling `job_agent.py`
directly from cron.

Make it executable:

```
chmod +x run_job_agent.sh
```

Open your crontab:

```
crontab -e
```

Add a line to run it, e.g. every weekday at 7am:

```
0 7 * * 1-5 /full/path/to/job_agent/run_job_agent.sh
```

Cron time format is `minute hour day month weekday`. A few examples:

| Schedule | Cron line |
|---|---|
| Every weekday at 7am | `0 7 * * 1-5` |
| Once daily at 9am | `0 9 * * *` |
| Every 6 hours | `0 */6 * * *` |
| Twice a week (Mon & Thu, 8am) | `0 8 * * 1,4` |

**Use the full absolute path** to `run_job_agent.sh` — cron doesn't know
about your current directory. Find it with `pwd` while inside the
job_agent folder.

Verify it's scheduled:

```
crontab -l
```

Check `run.log` after the next scheduled time passes to confirm it ran.

## What it does each run

- Fetches listings from all enabled sources
- Skips anything already scored in a previous run (`seen_jobs.json`)
- Scores each new listing against your resume (0–100 + a one-line reason)
- Appends full results to `job_matches.csv` (a running log, including
  low scores, so you can review match quality over time)
- Emails you a formatted digest of matches above your threshold (if enabled)

## Troubleshooting

- **Cron job doesn't seem to run**: check `run.log` exists and has
  content; confirm the path in your crontab is absolute; check
  `crontab -l` shows the line you expect.
- **Email fails with an auth error**: Gmail requires an App Password,
  not your account password, and requires 2FA to be enabled first.
- **"No jobs fetched from any source"**: double check `.env` has valid
  Adzuna keys, and that you've listed at least one company in
  `greenhouse_companies` or `lever_companies` if relying on those.

## Next steps

- Add more sources (e.g. RSS from job alert emails)
- Route to Slack instead of/alongside email
- Track application status alongside match scores in the CSV
