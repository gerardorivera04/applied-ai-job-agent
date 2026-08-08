#!/usr/bin/env python3
"""
Job Search Agent
=================

Pulls job listings from:
  1. Adzuna (broad job board aggregator API)
  2. Greenhouse (per-company career pages)
  3. Lever (per-company career pages)

...then scores each listing against your resume using the Claude API,
and prints/saves a ranked shortlist.

SETUP
-----
1. Install dependencies:
     pip install requests anthropic pdfplumber python-docx --break-system-packages

2. Set environment variables (or edit CONFIG below):
     export ANTHROPIC_API_KEY="sk-ant-..."
     export ADZUNA_APP_ID="..."
     export ADZUNA_APP_KEY="..."

   Get free Adzuna API credentials at: https://developer.adzuna.com/

3. Edit the CONFIG section below with your search terms, location,
   target companies, and resume file path.

4. Run:
     python3 job_agent.py

OUTPUT
------
Prints a ranked list to the console and writes results to
`job_matches.csv` in the same directory (new listings only get
re-scored on future runs -- already-seen jobs are cached in
`seen_jobs.json` so you don't pay for re-scoring or get duplicates).
"""

import os
import re
import json
import csv
import sys
import time
from datetime import datetime

import requests

# ============================================================
# CONFIG -- edit this section
# ============================================================

CONFIG = {
    # --- Resume ---
    "resume_path": "resume.pdf",  # .pdf, .docx, or .txt

    # --- Adzuna search ---
    "adzuna": {
        "enabled": True,
        "country": "us",             # e.g. "us", "gb", "au"
        "what": "software engineer", # search keywords
        "where": "remote",           # location or "remote"
        "results_per_page": 20,
        "max_pages": 2,              # 2 pages = up to 40 listings
        "salary_min": None,          # e.g. 120000, or None
    },

    # --- Greenhouse target companies ---
    # Find a company's slug from their careers URL, e.g.
    # boards.greenhouse.io/stripe -> "stripe"
    "greenhouse_companies": [
        # "stripe",
        # "airbnb",
    ],

    # --- Lever target companies ---
    # Find a company's slug from their careers URL, e.g.
    # jobs.lever.co/netflix -> "netflix"
    "lever_companies": [
        # "netflix",
    ],

    # --- Matching ---
    "min_score_to_show": 60,   # only show matches scoring >= this (0-100)
    "claude_model": "claude-sonnet-4-6",

    # --- Output ---
    "csv_path": "job_matches.csv",
    "seen_jobs_path": "seen_jobs.json",
}

# ============================================================
# RESUME LOADING
# ============================================================

def load_resume_text(path: str) -> str:
    if not os.path.exists(path):
        print(f"ERROR: resume file not found at '{path}'. "
              f"Set CONFIG['resume_path'] to a valid .pdf, .docx, or .txt file.")
        sys.exit(1)

    ext = os.path.splitext(path)[1].lower()

    if ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    elif ext == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            print("Install pdfplumber: pip install pdfplumber --break-system-packages")
            sys.exit(1)
        text = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)

    elif ext == ".docx":
        try:
            import docx
        except ImportError:
            print("Install python-docx: pip install python-docx --break-system-packages")
            sys.exit(1)
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)

    else:
        print(f"Unsupported resume format: {ext}")
        sys.exit(1)


# ============================================================
# SOURCE: ADZUNA
# ============================================================

def fetch_adzuna_jobs(cfg: dict) -> list:
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        print("Skipping Adzuna: set ADZUNA_APP_ID and ADZUNA_APP_KEY env vars.")
        return []

    a = cfg["adzuna"]
    if not a["enabled"]:
        return []

    jobs = []
    country = a["country"]

    for page in range(1, a["max_pages"] + 1):
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": a["what"],
            "where": a["where"],
            "results_per_page": a["results_per_page"],
            "content-type": "application/json",
        }
        if a.get("salary_min"):
            params["salary_min"] = a["salary_min"]

        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"Adzuna request failed on page {page}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        for r in results:
            jobs.append({
                "source": "adzuna",
                "id": f"adzuna-{r.get('id')}",
                "title": r.get("title", "").strip(),
                "company": (r.get("company") or {}).get("display_name", "Unknown"),
                "location": (r.get("location") or {}).get("display_name", ""),
                "url": r.get("redirect_url", ""),
                "description": re.sub(r"\s+", " ", r.get("description", "")).strip(),
                "posted": r.get("created", ""),
            })

    print(f"Adzuna: fetched {len(jobs)} listings.")
    return jobs


# ============================================================
# SOURCE: GREENHOUSE
# ============================================================

def fetch_greenhouse_jobs(companies: list) -> list:
    jobs = []
    for slug in companies:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        try:
            resp = requests.get(url, params={"content": "true"}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"Greenhouse fetch failed for '{slug}': {e}")
            continue

        for j in data.get("jobs", []):
            desc = re.sub(r"<[^>]+>", " ", j.get("content", ""))
            desc = re.sub(r"\s+", " ", desc).strip()
            jobs.append({
                "source": "greenhouse",
                "id": f"greenhouse-{j.get('id')}",
                "title": j.get("title", "").strip(),
                "company": slug,
                "location": (j.get("location") or {}).get("name", ""),
                "url": j.get("absolute_url", ""),
                "description": desc,
                "posted": j.get("updated_at", ""),
            })

    print(f"Greenhouse: fetched {len(jobs)} listings from {len(companies)} companies.")
    return jobs


# ============================================================
# SOURCE: LEVER
# ============================================================

def fetch_lever_jobs(companies: list) -> list:
    jobs = []
    for slug in companies:
        url = f"https://api.lever.co/v0/postings/{slug}"
        try:
            resp = requests.get(url, params={"mode": "json"}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"Lever fetch failed for '{slug}': {e}")
            continue

        for j in data:
            desc_parts = [j.get("descriptionPlain", "")]
            for l in j.get("lists", []):
                desc_parts.append(l.get("text", ""))
                for item in l.get("content", []):
                    if isinstance(item, str):
                        desc_parts.append(item)
            desc = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()

            jobs.append({
                "source": "lever",
                "id": f"lever-{j.get('id')}",
                "title": j.get("text", "").strip(),
                "company": slug,
                "location": (j.get("categories") or {}).get("location", ""),
                "url": j.get("hostedUrl", ""),
                "description": desc,
                "posted": j.get("createdAt", ""),
            })

    print(f"Lever: fetched {len(jobs)} listings from {len(companies)} companies.")
    return jobs


# ============================================================
# MATCHING (Claude API)
# ============================================================

def score_job_against_resume(job: dict, resume_text: str, model: str) -> dict:
    """Returns {'score': int 0-100, 'reason': str}"""
    try:
        import anthropic
    except ImportError:
        print("Install the anthropic SDK: pip install anthropic --break-system-packages")
        sys.exit(1)

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    prompt = f"""You are helping a job seeker evaluate whether a job listing is a good match for their resume.

RESUME:
{resume_text[:6000]}

JOB LISTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {job['description'][:3000]}

Score this job's fit for the candidate from 0-100, considering:
- Relevant skills/experience overlap
- Seniority match (not wildly over/under-qualified)
- Role type alignment (not just keyword overlap -- actual responsibilities)

Respond ONLY with valid JSON, no other text, in this exact format:
{{"score": <int 0-100>, "reason": "<one sentence, under 25 words, explaining the score>"}}"""

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        return {"score": int(parsed["score"]), "reason": parsed["reason"]}
    except Exception as e:
        print(f"  Scoring failed for '{job['title']}' at {job['company']}: {e}")
        return {"score": 0, "reason": "scoring failed"}


# ============================================================
# DEDUPE / CACHE
# ============================================================

def load_seen_jobs(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_seen_jobs(path: str, seen: dict):
    with open(path, "w") as f:
        json.dump(seen, f, indent=2)


# ============================================================
# OUTPUT
# ============================================================

def write_csv(path: str, rows: list):
    if not rows:
        return
    fieldnames = ["score", "reason", "title", "company", "location", "source", "url", "posted"]
    write_header = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def print_results(rows: list, min_score: int):
    shown = [r for r in rows if r["score"] >= min_score]
    shown.sort(key=lambda r: r["score"], reverse=True)

    print("\n" + "=" * 70)
    print(f"MATCHES (score >= {min_score}): {len(shown)}")
    print("=" * 70)
    for r in shown:
        print(f"\n[{r['score']}] {r['title']} @ {r['company']} ({r['source']})")
        print(f"    {r['location']}")
        print(f"    {r['reason']}")
        print(f"    {r['url']}")

    if not shown:
        print("No new matches above threshold this run.")


# ============================================================
# MAIN
# ============================================================

def main():
    print("Loading resume...")
    resume_text = load_resume_text(CONFIG["resume_path"])
    print(f"Resume loaded ({len(resume_text)} characters).\n")

    all_jobs = []
    all_jobs += fetch_adzuna_jobs(CONFIG)
    all_jobs += fetch_greenhouse_jobs(CONFIG["greenhouse_companies"])
    all_jobs += fetch_lever_jobs(CONFIG["lever_companies"])

    if not all_jobs:
        print("\nNo jobs fetched from any source. Check your CONFIG and API keys.")
        return

    seen = load_seen_jobs(CONFIG["seen_jobs_path"])
    new_jobs = [j for j in all_jobs if j["id"] not in seen]
    print(f"\n{len(all_jobs)} total listings fetched, {len(new_jobs)} are new.")

    if not new_jobs:
        print("No new listings since last run.")
        return

    print(f"\nScoring {len(new_jobs)} new listings against your resume...")
    results = []
    for i, job in enumerate(new_jobs, 1):
        print(f"  [{i}/{len(new_jobs)}] {job['title']} @ {job['company']}")
        score_data = score_job_against_resume(job, resume_text, CONFIG["claude_model"])
        job.update(score_data)
        results.append(job)
        seen[job["id"]] = {"scored_at": datetime.now().isoformat(), "score": score_data["score"]}
        time.sleep(0.3)  # gentle rate limiting

    save_seen_jobs(CONFIG["seen_jobs_path"], seen)
    write_csv(CONFIG["csv_path"], results)
    print_results(results, CONFIG["min_score_to_show"])
    print(f"\nAll scored results appended to: {CONFIG['csv_path']}")


if __name__ == "__main__":
    main()
