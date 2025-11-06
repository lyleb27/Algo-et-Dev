"""
Exercice 5 - Navigation catégorielle avancée
Cartographie arborescente + statistiques par catégorie.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os, json, time, random, re
import pandas as pd

BASE = "https://books.toscrape.com/"

def delay(): time.sleep(random.uniform(0.3,1.0))

def parse_price(p):
    return float(re.sub(r"[^\d.]", "", p))

def parse_rating(tag):
    RMAP = {"One":1,"Two":2,"Three":3,"Four":4,"Five":5}
    if not tag: return None
    for c in tag.get("class", []):
        if c in RMAP: return RMAP[c]
    return None

def scrape_category(url):
    """Scrape une seule catégorie (pagination incluse)."""
    books = []
    current = url
    while True:
        delay()
        r = requests.get(current)
        r.raise_for_status()
        s = BeautifulSoup(r.text,"lxml")

        for p in s.select(".product_pod"):
            title = p.h3.a["title"]
            price = parse_price(p.select_one(".price_color").text)
            rating = parse_rating(p.select_one(".star-rating"))

            # detail
            d = requests.get(urljoin(current, p.h3.a["href"]))
            d.raise_for_status()
            s2 = BeautifulSoup(d.text,"lxml")
            stock = int(re.search(r"\d+", s2.select_one(".availability").text).group(0))
            books.append({"title":title,"price":price,"rating":rating,"stock":stock})

        nxt = s.select_one(".next a")
        if not nxt: break
        current = urljoin(current, nxt["href"])

    return books


def main():
    root = os.path.dirname(__file__)
    outdir = os.path.join(root,"data")
    os.makedirs(outdir, exist_ok=True)

    # Page d'accueil – liste de catégories
    r = requests.get(BASE)
    r.raise_for_status()
    soup = BeautifulSoup(r.text,"lxml")

    cats = soup.select(".side_categories ul li ul li a")

    tree = {}

    for c in cats:
        name = c.text.strip()
        url = urljoin(BASE, c["href"])
        print(f"Scraping category: {name}")
        books = scrape_category(url)

        df = pd.DataFrame(books)
        if len(df)==0:
            stats = {"count":0,"mean_price":0,"min_price":0,"max_price":0}
        else:
            stats = {
                "count": int(df.shape[0]),
                "mean_price": float(df["price"].mean()),
                "min_price": float(df["price"].min()),
                "max_price": float(df["price"].max()),
            }

        tree[name] = {
            "url": url,
            "stats": stats,
            "books": books
        }

    # détection catégories sous-représentées (moins de 10 livres)
    under = [k for k,v in tree.items() if v["stats"]["count"] < 10]
    tree["_small_categories"] = under

    with open(os.path.join(outdir,"categories_tree.json"),"w",encoding="utf-8") as f:
        json.dump(tree,f,indent=2,ensure_ascii=False)

    print("✅ Catégories analysées. Résultat : data/categories_tree.json")

if __name__=="__main__":
    main()
