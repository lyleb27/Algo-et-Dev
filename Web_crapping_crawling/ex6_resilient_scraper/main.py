"""
Exercice 6 - Scraper résilient
Reprise sur interruption + log + retry + throttling + IP freeze detection.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time, random, json, os, logging, re
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

BASE = "https://books.toscrape.com/"
PROGRESS_FILE = "data/progress.json"
OUTPUT_FILE = "data/books_resilient.json"

# --- Logging --------------------------------------------------------

def configure_logging(logdir):
    os.makedirs(logdir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(logdir,"scraper.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )


# --- Session avec retry --------------------------------------------

def session_retry():
    s = requests.Session()
    r = Retry(total=5, backoff_factor=1,
              status_forcelist=[429,500,502,503,504],
              allowed_methods=["GET"])
    a = HTTPAdapter(max_retries=r)
    s.mount("http://", a)
    s.mount("https://", a)
    return s


def throttle(min_s=0.5,max_s=1.5):
    time.sleep(random.uniform(min_s,max_s))


# --- Progress -------------------------------------------------------

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        return json.load(open(PROGRESS_FILE))
    return {"done_pages":[],"books":[]}

def save_progress(p):
    json.dump(p, open(PROGRESS_FILE,"w"), indent=2)


# --- IP freeze detection --------------------------------------------

def is_ip_blocked(response):
    if response.status_code == 429:
        return True
    if "captcha" in response.text.lower():
        return True
    return False


# --- Scraper --------------------------------------------------------

def scrape_page(session, url):
    throttle()
    r = session.get(url, timeout=10)
    if is_ip_blocked(r):
        logging.error("IP semble bloquée !")
        raise Exception("IP blocked")
    r.raise_for_status()

    soup = BeautifulSoup(r.text,"lxml")
    books=[]
    for p in soup.select(".product_pod"):
        title = p.h3.a["title"]
        price = float(re.sub(r"[^\d.]", "", p.select_one(".price_color").text))
        books.append({"title":title,"price":price})
    next_link = soup.select_one(".next a")
    return books, next_link["href"] if next_link else None


def main():
    root = os.path.dirname(__file__)
    os.makedirs(os.path.join(root,"data"), exist_ok=True)
    os.makedirs(os.path.join(root,"logs"), exist_ok=True)
    configure_logging(os.path.join(root,"logs"))

    session = session_retry()
    progress = load_progress()

    current = BASE
    page_index = 1

    if progress["done_pages"]:
        page_index = max(progress["done_pages"]) + 1
        current = urljoin(BASE, f"catalogue/page-{page_index}.html")

    while True:
        try:
            logging.info(f"Scraping page {page_index}: {current}")
            books, next_rel = scrape_page(session, current)

            progress["books"].extend(books)
            progress["done_pages"].append(page_index)
            save_progress(progress)

            if not next_rel:
                break

            current = urljoin(current, next_rel)
            page_index += 1

        except Exception as e:
            logging.error(f"Erreur : {e}, tentative reprise dans 10s")
            time.sleep(10)
            continue

    json.dump(progress["books"], open(os.path.join(root,"data","books_resilient.json"),"w"), indent=2)
    print("✅ Scraper résilient terminé.")


if __name__=="__main__":
    main()
