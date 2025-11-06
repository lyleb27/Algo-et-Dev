#!/usr/bin/env python3
"""
Exercice 4 - Analyse de marché livresque
Scraper + analyse statistique + visualisations matplotlib.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os, json, re, time, random
import pandas as pd
import matplotlib.pyplot as plt

BASE = "https://books.toscrape.com/"
RATING_MAP = {"One":1,"Two":2,"Three":3,"Four":4,"Five":5}


# --- Utilities ------------------------------------------------------

def delay():
    time.sleep(random.uniform(0.3,1.0))

def parse_price(p):
    return float(re.sub(r"[^\d.]", "", p))

def parse_rating(tag):
    if not tag: return None
    classes = tag.get("class", [])
    for c in classes:
        if c in RATING_MAP:
            return RATING_MAP[c]
    return None


# --- Scraping -------------------------------------------------------

def scrape_books():
    url = BASE
    books = []

    while True:
        delay()
        res = requests.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        for p in soup.select(".product_pod"):
            title = p.h3.a["title"]
            detail_url = urljoin(url, p.h3.a["href"])
            price = parse_price(p.select_one(".price_color").text)
            rating = parse_rating(p.select_one(".star-rating"))

            # detail page
            delay()
            d = requests.get(detail_url)
            d.raise_for_status()
            s2 = BeautifulSoup(d.text, "lxml")

            stock_tag = s2.select_one(".availability")
            stock = int(re.search(r"\d+", stock_tag.text).group(0)) if stock_tag else 0

            # category
            crumbs = s2.select(".breadcrumb li a")
            category = crumbs[2].text.strip() if len(crumbs)>=3 else "Unknown"

            books.append({
                "title": title,
                "price": price,
                "rating": rating,
                "stock": stock,
                "category": category
            })

        nxt = soup.select_one(".next a")
        if not nxt:
            break
        url = urljoin(url, nxt["href"])

    return books


# --- Analysis -------------------------------------------------------

def analyze(books, outdir):
    df = pd.DataFrame(books)

    # prix moyen par note
    by_rating = df.groupby("rating")["price"].agg(["mean","min","max","count"])
    by_rating.to_csv(os.path.join(outdir,"stats_by_rating.csv"))

    # prix moyen par catégorie
    by_cat = df.groupby("category")["price"].agg(["mean","min","max","count"])
    by_cat.to_csv(os.path.join(outdir,"stats_by_category.csv"))

    # rupture de stock
    out_of_stock = df[df["stock"]==0]

    # Graph 1 : distribution des ratings
    plt.figure(figsize=(6,4))
    df["rating"].value_counts().sort_index().plot(kind="bar")
    plt.title("Distribution des ratings")
    plt.savefig(os.path.join(outdir,"../figures/rating_distribution.png"))
    plt.close()

    # Graph 2 : prix moyens par catégorie (top 10)
    plt.figure(figsize=(10,5))
    by_cat["mean"].sort_values(ascending=False).head(10).plot(kind="bar")
    plt.title("Prix moyen par catégorie (top 10)")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir,"../figures/category_avg_price.png"))
    plt.close()

    return by_rating, by_cat, out_of_stock


# --- Main -----------------------------------------------------------

def main():
    root = os.path.dirname(__file__)
    data_dir = os.path.join(root,"data")
    fig_dir = os.path.join(root,"figures")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(fig_dir, exist_ok=True)

    print("Scraping books...")
    books = scrape_books()

    with open(os.path.join(data_dir,"clean_books.json"),"w",encoding="utf-8") as f:
        json.dump(books,f,indent=2,ensure_ascii=False)

    print("Analyzing...")
    analyze(books, data_dir)

    print("✅ Analyse terminée. Fichiers générés dans ex4_market_analysis/data et figures/")


if __name__ == "__main__":
    main()
