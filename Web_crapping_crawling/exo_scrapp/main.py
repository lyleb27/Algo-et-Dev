"""
google_play_collector.py
But: collecter apps Google Play via SerpAPI, nettoyer, sauvegarder CSV + SQLite, produire dataset prêt pour LLM.
"""

import os
import re
import time
import csv
from typing import List, Dict, Any
from serpapi import GoogleSearch
import pandas as pd
from tqdm import tqdm
from sqlalchemy import create_engine

# -------- CONFIG --------
API_KEY = "CLE API ICI"
PER_PAGE = 10     # dépend de l'API : on récupère ce que renvoie SerpAPI par search call
SLEEP_BETWEEN_CALLS = 1.0
# ------------------------

def fetch_apps_for_query(query: str, api_key: str, max_pages: int = 5) -> List[Dict[str, Any]]:
    """
    Requête l'API SerpAPI (engine=google_play) pour 'query'.
    Retourne la liste d'apps extraites (brutes).
    """
    all_apps = []
    for page in range(max_pages):
        params = {
            "engine": "google_play",
            "q": query,
            "api_key": api_key,
            # "start": page * PER_PAGE  # si l'API supporte start/offset
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        apps = results.get("apps", [])
        if not apps:
            break
        all_apps.extend(apps)
        time.sleep(SLEEP_BETWEEN_CALLS)
    return all_apps

# ---------- Nettoyage / Normalisation ----------
def parse_installs(installs_raw: str) -> int:
    """
    Convertit "1,000,000+", "1M+", "10k", "500" en entier approximatif.
    """
    if installs_raw is None:
        return None
    s = str(installs_raw).strip()
    s = s.replace(",", "").replace(" ", "")
    # ex: "1,000,000+", "1M+", "10k+"
    s = s.rstrip("+")
    # pattern for M / k / B
    match = re.match(r"^([\d\.]+)([KkMmBb]?)$", s)
    if match:
        num = float(match.group(1))
        unit = match.group(2).upper()
        if unit == "K":
            return int(num * 1_000)
        elif unit == "M":
            return int(num * 1_000_000)
        elif unit == "B":
            return int(num * 1_000_000_000)
        else:
            return int(num)
    # fallback: try digits inside string
    nums = re.findall(r"\d+", s)
    if nums:
        return int(nums[0])
    return None

def parse_score(score_raw) -> float:
    try:
        return float(score_raw)
    except Exception:
        return None

def normalize_text(t: str) -> str:
    if t is None:
        return ""
    # remove weird control chars, multiple spaces, trim
    t = re.sub(r"[\r\n\t]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def extract_fields(app_raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mappe le dictionnaire brut renvoyé par SerpAPI vers notre schéma requis.
    Champs demandés :
    - title, developer, score (note moyenne), installs (nombre), category, short_description
    """
    return {
        "title": normalize_text(app_raw.get("title") or app_raw.get("name")),
        "developer": normalize_text(app_raw.get("developer")),
        "score": parse_score(app_raw.get("score") or app_raw.get("rating")),
        "installs_raw": normalize_text(app_raw.get("installs") or app_raw.get("installs_raw") or ""),
        "installs": parse_installs(app_raw.get("installs") or app_raw.get("installs_raw") or ""),
        "category": normalize_text(app_raw.get("category") or app_raw.get("genre")),
        "short_description": normalize_text(app_raw.get("short_description") or app_raw.get("description") or "")
    }

def deduplicate_apps(apps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Supprime doublons basés sur (title, developer) après normalisation (lowercase).
    Garde la première apparition.
    """
    seen = set()
    deduped = []
    for app in apps:
        key = (app.get("title","").lower(), app.get("developer","").lower())
        if key not in seen:
            seen.add(key)
            deduped.append(app)
    return deduped

# ---------- Sauvegarde ----------
def save_to_csv(apps: List[Dict[str, Any]], path: str):
    df = pd.DataFrame(apps)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved CSV: {path} ({len(df)} rows)")

def save_to_sqlite(apps: List[Dict[str, Any]], sqlite_path: str, table_name: str = "apps"):
    engine = create_engine(f"sqlite:///{sqlite_path}")
    df = pd.DataFrame(apps)
    df.to_sql(table_name, engine, if_exists="replace", index=False)
    print(f"Saved SQLite: {sqlite_path} table={table_name} ({len(df)} rows)")

# ---------- Analyse / Résumé (prépare dataset pour LLM) ----------
def build_prompt_from_dataframe(df: pd.DataFrame, top_n:int=10) -> str:
    """
    Construit un prompt pour un LLM à partir du dataframe nettoyé.
    On fournit un échantillon et on demande une analyse synthétique.
    """
    # sélection de colonnes pertinentes
    sample = df[["title","developer","category","score","installs"]].fillna("").head(100)
    # convertir en CSV (string)
    csv_sample = sample.to_csv(index=False)
    prompt = f"""
Voici un dataset (CSV) contenant des applications Google Play (colonnes: title, developer, category, score, installs).
Dataset (extrait):
{csv_sample}

Analyse et génère un rapport synthétique comprenant:
- Top catégories les plus populaires (par nombre d'applications et par total d'installations)
- Top applications par note (score) (indique title, developer, score, installs)
- Top applications par nombre d'installations
- Corrélations intéressantes (ex: note vs installs)
- Recommandations pour un Product Manager ou un développeur (3 actions concrètes)
Donne le rapport en français, structure-lui un sommaire et ajoute une conclusion courte.
"""
    return prompt

# ---------- Main pipeline ----------
def run_pipeline(queries: List[str], api_key: str, max_pages_per_query: int = 3):
    raw_collected = []
    for q in queries:
        print(f"Fetching query: {q}")
        apps = fetch_apps_for_query(q, api_key, max_pages=max_pages_per_query)
        print(f"  -> {len(apps)} raw apps fetched")
        for a in apps:
            raw_collected.append(a)
    print(f"Total raw records: {len(raw_collected)}")

    # extract fields
    extracted = [extract_fields(r) for r in raw_collected]
    print(f"Extracted fields for {len(extracted)} records")

    # deduplicate
    deduped = deduplicate_apps(extracted)
    print(f"Deduplicated: {len(deduped)} records after removing duplicates")

    # Save
    os.makedirs("output", exist_ok=True)
    save_to_csv(deduped, "output/google_play_apps.csv")
    save_to_sqlite(deduped, "output/google_play_apps.db")

    # create DataFrame for further analysis / LLM prompt
    df = pd.DataFrame(deduped)
    prompt = build_prompt_from_dataframe(df)
    # write prompt to file for copy/paste into ton LLM préféré
    with open("output/llm_prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)
    print("LLM prompt saved to output/llm_prompt.txt")

    return df, prompt

# ---------- Example usage ----------
if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit("Erreur: définis SERPAPI_API_KEY en variable d'environnement.")
    # exemples de queries : catégories ou mots-clés
    queries = ["productivity apps", "photo editor", "to-do list", "finance"]
    df, prompt = run_pipeline(queries, API_KEY, max_pages_per_query=2)
    print("Pipeline terminé. Extrait du dataset:")
    print(df.head(5).to_string(index=False))

