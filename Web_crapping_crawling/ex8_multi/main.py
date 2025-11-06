"""
ex8_multi/multi_scraper.py

Scraper multi-sources modulaire pour:
 - books.toscrape.com
 - quotes.toscrape.com
 - realpython.github.io/fake-jobs

Chaque plugin renvoie une liste d'items (dict) dans un format libre mais on ajoute metadata 'source'.
Exécuter: python main.py
"""
import requests, os, json, time, random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

def create_session():
    s = requests.Session()
    s.headers.update({"User-Agent":"multi-scraper/1.0"})
    return s

# --- Plugin: books ---
def scrape_books(session, limit_pages=2):
    base = "https://books.toscrape.com/"
    results = []
    url = base
    pages = 0
    while url and pages < limit_pages:
        resp = session.get(url, timeout=10); resp.raise_for_status()
        soup = BeautifulSoup(resp.text,"lxml")
        for p in soup.select(".product_pod"):
            title = p.h3.a["title"]
            price = p.select_one(".price_color").text if p.select_one(".price_color") else ""
            rel = p.h3.a["href"]
            item = {"title": title, "price": price, "detail_url": urljoin(url, rel)}
            results.append(item)
        nxt = soup.select_one(".next a")
        url = urljoin(url, nxt["href"]) if nxt else None
        pages += 1
        time.sleep(random.uniform(0.2,0.7))
    return results

# --- Plugin: quotes (toutes les pages) ---
def scrape_quotes(session):
    base = "http://quotes.toscrape.com/"
    url = base
    results = []
    while url:
        resp = session.get(url, timeout=10); resp.raise_for_status()
        soup = BeautifulSoup(resp.text,"lxml")
        for q in soup.select(".quote"):
            text = q.select_one(".text").get_text(strip=True)
            author = q.select_one(".author").get_text(strip=True)
            tags = [t.get_text(strip=True) for t in q.select(".tag")]
            results.append({"text":text, "author":author, "tags":tags})
        nxt = soup.select_one(".next a")
        url = urljoin(base, nxt["href"]) if nxt else None
        time.sleep(random.uniform(0.1,0.5))
    return results

# --- Plugin: fake-jobs ---
def scrape_fakejobs(session):
    base = "https://realpython.github.io/fake-jobs/"
    resp = session.get(base, timeout=10); resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    for card in soup.select(".card-content"):
        title = card.select_one("h2.title").get_text(strip=True) if card.select_one("h2.title") else ""
        company = card.select_one("h3.company").get_text(strip=True) if card.select_one("h3.company") else ""
        loc = card.select_one("p.location").get_text(strip=True) if card.select_one("p.location") else ""
        results.append({"title":title,"company":company,"location":loc})
    return results

# --- Orchestrator ---
PLUGINS = {
    "books": scrape_books,
    "quotes": scrape_quotes,
    "fakejobs": scrape_fakejobs
}

def main(outdir="ex8_multi/data"):
    os.makedirs(outdir, exist_ok=True)
    session = create_session()
    unified = {"timestamp": datetime.utcnow().isoformat(), "sources": {}}

    for name, fn in PLUGINS.items():
        try:
            print(f"Scraping {name} ...")
            items = fn(session)
            unified["sources"][name] = {"count": len(items), "items": items}
            time.sleep(random.uniform(0.2,0.8))
        except Exception as e:
            print(f"Error scraping {name}: {e}")
            unified["sources"][name] = {"error": str(e)}

    outpath = os.path.join(outdir, "unified_data.json")
    with open(outpath,"w",encoding="utf-8") as f:
        json.dump(unified, f, indent=2, ensure_ascii=False)
    print(f"Saved unified data to {outpath}")

if __name__=="__main__":
    main()
