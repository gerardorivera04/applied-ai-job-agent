# Job Search Agent

A script that pulls job listings from Adzuna, Greenhouse, and Lever, then
scores each one against your resume using the Claude API.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt --break-system-packages
   ```

2. Get a free Adzuna API key: https://developer.adzuna.com/
   (takes ~2 minutes, gives you `app_id` and `app_key`)

3. Set environment variables:
   ```
   export ANTHROPIC_API_KEY="sk-ant-..."
   export ADZUNA_APP_ID="..."
   export ADZUNA_APP_KEY="..."
   ```

4. Put your resume in this folder (e.g. `resume.pdf`, `resume.docx`, or `resume.txt`).

5. Open `job_agent.py` and edit the `CONFIG` dict near the top:
   - `resume_path` — path to your resume file
   - `adzuna.what` / `adzuna.where` — your search keywords and location
   - `greenhouse_companies` / `lever_companies` — slugs of companies you
     want to watch directly (find the slug in their careers page URL,
     e.g. `boards.greenhouse.io/stripe` → `"stripe"`,
     `jobs.lever.co/netflix` → `"netflix"`)
   - `min_score_to_show` — only show matches at or above this score (0-100)

6. Run it:
   ```
   python3 job_agent.py
   ```

## What it does

- Fetches listings from all enabled sources
- Skips anything already scored in a previous run (`seen_jobs.json`)
- Scores each new listing against your resume (0-100 + a one-line reason)
- Prints matches above your threshold, sorted best-first
- Appends full results to `job_matches.csv` (a running log, including
  low scores, so you can review your matching quality over time)

## Notes

- **Company slugs matter more than you'd think.** The Greenhouse/Lever
  sources only work for companies that actually use those platforms —
  not every company does. Adzuna covers a much broader net but with
  more noise.
- **Scoring costs a small amount per listing** (one Claude API call
  each). The `seen_jobs.json` cache prevents re-scoring the same
  listing on every run.
- **Next steps once this feels solid:** wire it into a daily cron job,
  pipe results to email/Slack instead of the console, or add more
  sources (e.g. RSS from job alert emails).
