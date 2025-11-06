#!/usr/bin/env python3
"""
ex1_books/scraper_books.py
Scraper complet pour https://books.toscrape.com/
Sauvegarde: ex1_books/data/books_<timestamp>.json
"""
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time, random, json, os
from datetime import datetime
from tqdm import tqdm
import re

BASE = "https://books.toscrape.com/"

def create_session_with_retries(total=3, backoff_factor=1):
    session = requests.Session()
    retry = Retry(total=total, backoff_factor=backoff_factor,
                  status_forcelist=[429,500,502,503,504], allowed_methods=["GET","POST"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; lab-scraper/1.0)"})
    return session

def respectful_delay(min_delay=0.8, max_delay=2.0):
    time.sleep(random.uniform(min_delay, max_delay))

RATING_MAP = {
    "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5
}

def parse_price(text):
    # Ex: '£51.77'
    try:
        return float(re.sub(r"[^\d.,]", "", text).replace(",", "."))
    except:
        return None

def parse_stock(text):
    # Ex: "In stock (22 available)"
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else 0

def parse_rating(tag):
    # class contains "star-rating Three"
    classes = tag.get("class", [])
    for cls in classes:
        if cls in RATING_MAP:
            return RATING_MAP[cls]
    return None

def scrape_book_detail(session, detail_url):
    resp = session.get(detail_url, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")
    desc_tag = soup.select_one("#content_inner .product_page > p")
    description = desc_tag.get_text(strip=True) if desc_tag else ""
    # category breadcrumb: home > Books > category > ...
    category = ""
    crumbs = soup.select(".breadcrumb li a")
    if len(crumbs) >= 3:
        category = crumbs[2].get_text(strip=True)
    # stock
    stock_tag = soup.select_one(".product_main .availability")
    stock = parse_stock(stock_tag.get_text(strip=True)) if stock_tag else 0
    image_tag = soup.select_one(".carousel img")
    image_url = urljoin(detail_url, image_tag["src"]) if image_tag and image_tag.get("src") else ""
    return {"description": description, "category": category, "stock": stock, "image_url": image_url}

def scrape():
    session = create_session_with_retries()
    page_url = urljoin(BASE, "catalogue/page-1.html")
    books = []
    page_index = 1
    # There is also index.html for first page; handle both
    # We'll iterate until no "next" found
    current = BASE
    # Start at catalogue index (site uses index.html) -> we'll use BASE and follow pagination
    current = BASE
    print("Starting scraping books.toscrape.com ...")
    while True:
        respectful_delay()
        resp = session.get(current, timeout=10)
        if resp.status_code == 404:
            print(f"Page not found: {current}, stopping.")
            break
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        # each book in .product_pod
        pods = soup.select(".product_pod")
        if not pods:
            # maybe we're on catalogue page under /catalogue/
            pods = soup.select(".product_pod")
        for pod in pods:
            title_tag = pod.select_one("h3 a")
            title = title_tag["title"].strip()
            relative = title_tag["href"]
            book_url = urljoin(current, relative)
            price_tag = pod.select_one(".price_color")
            price = parse_price(price_tag.get_text()) if price_tag else None
            rating = parse_rating(pod.select_one(".star-rating") or pod)
            # Visit detail page
            respectful_delay(0.5, 1.5)
            try:
                detail = scrape_book_detail(session, book_url)
            except Exception as e:
                print(f"Error fetching detail {book_url}: {e}")
                detail = None
            if detail is None:
                # graceful fallback
                detail = {"description": "", "category": "", "stock": 0, "image_url": ""}
            book = {
                "title": title,
                "url": book_url,
                "price": price,
                "rating": rating,
                "category": detail["category"],
                "description": detail["description"],
                "stock": detail["stock"],
                "image_url": detail["image_url"]
            }
            books.append(book)
        # next page?
        next_btn = soup.select_one(".next a")
        if next_btn and next_btn.get("href"):
            current = urljoin(current, next_btn["href"])
            page_index += 1
            print(f"Scraping page {page_index} ...")
            continue
        # else finished
        break

    # Save JSON with timestamp
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")
    outdir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(outdir, exist_ok=True)
    fname = os.path.join(outdir, f"books_{timestamp}.json")
    payload = {"timestamp": timestamp, "count": len(books), "books": books}
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(books)} books to {fname}")

if __name__ == "__main__":
    scrape()
