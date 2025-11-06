#!/usr/bin/env python3
"""
ex7_pipeline/data_cleaning.py

Pipeline simple de data cleaning pour datasets de scraping (ex: books).
Exécuter: python data_cleaning.py --input path/to/raw.json --outdir ex7_pipeline/data
"""
import os, json, argparse, re
import pandas as pd
import numpy as np
from dateutil import parser as dateparser
from collections import defaultdict

def parse_price(x):
    if pd.isna(x): return np.nan
    if isinstance(x,(int,float)): return float(x)
    s = str(x)
    s = re.sub(r"[^\d\.,-]", "", s).replace(",", ".")
    try:
        return float(s)
    except:
        return np.nan

def parse_rating(x):
    if pd.isna(x): return np.nan
    try:
        return int(x)
    except:
        # try words
        mapping = {"one":1,"two":2,"three":3,"four":4,"five":5}
        s=str(x).strip().lower()
        return mapping.get(s, np.nan)

def safe_str(x):
    if pd.isna(x): return ""
    return str(x).strip()

def detect_outliers(series):
    # simple IQR method
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return series[(series < lower) | (series > upper)]

def load_input(path):
    if path.lower().endswith(".json"):
        with open(path,"r",encoding="utf-8") as f:
            payload = json.load(f)
        # try to extract list of books
        if isinstance(payload, dict) and "books" in payload:
            return pd.DataFrame(payload["books"])
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        return pd.DataFrame(payload)
    else:
        return pd.read_csv(path)

def clean_df(df):
    # normalize columns: title, price, rating, category, stock, date (if present)
    df = df.copy()
    # common columns may or may not exist
    if "title" in df.columns:
        df["title"] = df["title"].apply(safe_str)
    if "price" in df.columns:
        df["price_raw"] = df["price"]
        df["price"] = df["price"].apply(parse_price)
    if "rating" in df.columns:
        df["rating_raw"] = df["rating"]
        df["rating"] = df["rating"].apply(parse_rating)
    if "stock" in df.columns:
        def parse_stock(x):
            if pd.isna(x): return np.nan
            s = str(x)
            m = re.search(r"(\d+)", s)
            return int(m.group(1)) if m else np.nan
        df["stock_raw"] = df["stock"]
        df["stock"] = df["stock"].apply(parse_stock)
    if "category" in df.columns:
        df["category"] = df["category"].apply(safe_str)
    # trim strings columns
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].apply(lambda s: s.strip() if isinstance(s,str) else s)

    # Impute simple: price -> median, rating -> mode, stock -> 0 if missing
    report = {}
    if "price" in df.columns:
        median_price = df["price"].median(skipna=True)
        df["price"].fillna(median_price, inplace=True)
        report["median_price_imputed"] = float(median_price) if not np.isnan(median_price) else None
    if "rating" in df.columns:
        mode = df["rating"].mode(dropna=True)
        df["rating"].fillna(mode.iloc[0] if not mode.empty else 0, inplace=True)
    if "stock" in df.columns:
        df["stock"].fillna(0, inplace=True)

    # Detect outliers on price
    price_outliers = detect_outliers(df["price"]) if "price" in df.columns else pd.Series([])
    report["price_outliers_count"] = int(price_outliers.shape[0])

    # Basic quality metrics
    quality = {
        "n_rows": int(df.shape[0]),
        "missing_per_column": df.isna().sum().to_dict()
    }
    report["quality"] = quality
    return df, report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Fichier brut (json/csv)")
    parser.add_argument("--outdir", default="ex7_pipeline/data", help="Dossier de sortie")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    df = load_input(args.input)
    cleaned, report = clean_df(df)
    cleaned.to_csv(os.path.join(args.outdir,"cleaned_books.csv"), index=False, encoding="utf-8")
    with open(os.path.join(args.outdir,"cleaning_report.json"),"w",encoding="utf-8") as f:
        json.dump(report,f,indent=2,ensure_ascii=False)
    print(f"Saved cleaned CSV and report to {args.outdir}")

if __name__ == "__main__":
    main()
