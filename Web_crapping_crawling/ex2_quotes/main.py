"""
ex2_quotes/main.py
Scraper pour http://quotes.toscrape.com/
Sorties:
 - ex2_quotes/data/authors_cache.json
 - ex2_quotes/data/quotes_graph.gexf
"""
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import urljoin
import os, json, time, random
from datetime import datetime
import networkx as nx
from tqdm import tqdm

BASE = "http://quotes.toscrape.com/"

def create_session_with_retries(total=3, backoff_factor=1):
    session = requests.Session()
    retry = Retry(total=total, backoff_factor=backoff_factor,
                  status_forcelist=[429,500,502,503,504], allowed_methods=["GET","POST"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; lab-scraper/1.0)"})
    return session

def respectful_delay(min_delay=0.5, max_delay=1.5):
    time.sleep(random.uniform(min_delay, max_delay))

def load_cache(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def scrape_author(session, author_relative, cache):
    name = author_relative
    url = urljoin(BASE, author_relative)
    if url in cache:
        return cache[url]
    respectful_delay()
    resp = session.get(url, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")
    title = soup.select_one(".author-title")
    name = title.get_text(strip=True) if title else ""
    born_date = soup.select_one(".author-born-date")
    born_loc = soup.select_one(".author-born-location")
    bio = soup.select_one(".author-description")
    data = {
        "name": name,
        "born_date": born_date.get_text(strip=True) if born_date else "",
        "born_location": born_loc.get_text(strip=True) if born_loc else "",
        "bio": bio.get_text(strip=True) if bio else ""
    }
    cache[url] = data
    return data

def scrape():
    session = create_session_with_retries()
    outdir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(outdir, exist_ok=True)
    cache_path = os.path.join(outdir, "authors_cache.json")
    cache = load_cache(cache_path)
    G = nx.Graph()
    quotes_count = 0

    current = BASE
    print("Scraping quotes.toscrape.com ...")
    while True:
        respectful_delay()
        resp = session.get(current, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        quote_blocks = soup.select(".quote")
        for qb in quote_blocks:
            text = qb.select_one(".text").get_text(strip=True)
            author = qb.select_one(".author").get_text(strip=True)
            tag_elems = qb.select(".tags .tag")
            tags = [t.get_text(strip=True) for t in tag_elems]
            author_link = qb.select_one("a[href*='/author/']")
            author_rel = author_link["href"] if author_link else ""
            author_data = scrape_author(session, author_rel, cache) if author_rel else {"name": author, "born_date":"", "born_location":"", "bio":""}
            quote_id = f"quote_{quotes_count}"
            G.add_node(quote_id, type="quote", text=text)
            G.add_node(author, type="author", born_date=author_data.get("born_date",""), born_location=author_data.get("born_location",""), bio=author_data.get("bio",""))
            G.add_edge(quote_id, author, relation="written_by")
            for tag in tags:
                G.add_node(tag, type="tag")
                G.add_edge(quote_id, tag, relation="has_tag")
            quotes_count += 1
        next_btn = soup.select_one(".next a")
        if next_btn and next_btn.get("href"):
            current = urljoin(current, next_btn["href"])
            print(f"Scraping next page ...")
            continue
        break

    # save cache
    save_cache(cache_path, cache)
    # save graph
    gexf_path = os.path.join(outdir, "quotes_graph.gexf")
    nx.write_gexf(G, gexf_path)
    print(f"Saved authors cache to {cache_path}")
    print(f"Saved graph to {gexf_path}")
    authors = [(n, d) for n,d in G.nodes(data=True) if d.get("type")=="author"]
    counts = []
    for name, attrs in authors:
        deg = sum(1 for nb in G.neighbors(name) if G.nodes[nb].get("type")=="quote")
        counts.append((name, deg))
    counts.sort(key=lambda x: x[1], reverse=True)
    print("Top authors by number of quotes (sample):")
    for name, cnt in counts[:10]:
        print(f" - {name}: {cnt} quote(s)")

if __name__ == "__main__":
    scrape()
