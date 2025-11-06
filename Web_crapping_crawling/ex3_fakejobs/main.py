#!/usr/bin/env python3
"""
ex3_fakejobs/scraper_fakejobs.py
Scraper pour https://realpython.github.io/fake-jobs/
Filtre: n'affiche que les offres contenant 'Python' (case-insensitive)
Sortie: ex3_fakejobs/data/fakejobs_python.csv
"""
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import urljoin
import os, csv, time, random, argparse
from datetime import datetime
from dateutil import parser as dateparser
from collections import defaultdict

BASE = "https://realpython.github.io/fake-jobs/"

def create_session_with_retries(total=3, backoff_factor=1):
    session = requests.Session()
    retry = Retry(total=total, backoff_factor=backoff_factor,
                  status_forcelist=[429,500,502,503,504], allowed_methods=["GET","POST"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; lab-scraper/1.0)"})
    return session

def respectful_delay(min_delay=0.3, max_delay=1.0):
    time.sleep(random.uniform(min_delay, max_delay))

def normalize_date(raw):
    if not raw:
        return ""
    try:
        dt = dateparser.parse(raw, dayfirst=False)
        return dt.date().isoformat()
    except Exception:
        return raw.strip()

def is_python_job(text_fields):
    # text_fields: list of strings to scan
    combined = " ".join([t or "" for t in text_fields]).lower()
    return "python" in combined

def scrape(min_date=None):
    session = create_session_with_retries()
    resp = session.get(BASE, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")
    jobs = soup.select(".card-content")
    results = []
    seen = set()
    for job in jobs:
        title = job.select_one("h2.title").get_text(strip=True) if job.select_one("h2.title") else ""
        company = job.select_one("h3.company").get_text(strip=True) if job.select_one("h3.company") else ""
        location = job.select_one("p.location").get_text(strip=True) if job.select_one("p.location") else ""
        # find apply link
        apply_elem = job.find("a", string="Apply")
        apply_url = urljoin(BASE, apply_elem["href"]) if apply_elem and apply_elem.get("href") else ""
        # there may be meta such as contract and date inside <p> with class "is-small"
        extras = job.select("p.is-small")
        contract = ""
        date_raw = ""
        for ex in extras:
            text = ex.get_text(" ", strip=True)
            # heuristics
            if "Contract" in text or "Full" in text or "Part" in text or "Intern" in text:
                contract = text
            if any(c.isdigit() for c in text):
                # likely date
                date_raw = text
        date_norm = normalize_date(date_raw)
        # filter by Python
        if not is_python_job([title, company, location, contract]):
            continue
        # deduplicate by title+company+location
        key = (title.strip().lower(), company.strip().lower(), location.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        # optional date filtering
        if min_date:
            try:
                if date_norm:
                    if dateparser.parse(date_norm).date() < min_date:
                        continue
            except:
                pass
        results.append({
            "title": title,
            "company": company,
            "location": location,
            "contract": contract,
            "date": date_norm,
            "apply_url": apply_url
        })
    # stats
    by_city = defaultdict(int)
    by_contract = defaultdict(int)
    for r in results:
        by_city[r["location"]] += 1
        by_contract[r["contract"]] += 1

    outdir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(outdir, exist_ok=True)
    fname = os.path.join(outdir, "fakejobs_python.csv")
    with open(fname, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["title","company","location","contract","date","apply_url"])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print(f"Found {len(jobs)} total job cards, filtered: {len(results)} Python jobs")
    print(f"Saved CSV to {fname}")
    print("Stats by city (sample):")
    for k,v in sorted(by_city.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f" - {k}: {v}")
    print("Stats by contract (sample):")
    for k,v in sorted(by_contract.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f" - {k}: {v}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape fake-jobs and filter Python offers")
    parser.add_argument("--min-date", help="ISO date YYYY-MM-DD to filter older jobs", default=None)
    args = parser.parse_args()
    min_date = None
    if args.min_date:
        try:
            min_date = dateparser.parse(args.min_date).date()
        except:
            print("Invalid date for --min-date; ignoring.")
    scrape(min_date=min_date)
