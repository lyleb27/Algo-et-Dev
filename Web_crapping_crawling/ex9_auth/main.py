#!/usr/bin/env python3
"""
ex9_auth/auth_session.py

Gère login + session persistence pour http://quotes.toscrape.com/login
Exemple d'utilisation:
 python auth_session.py --username foo --password bar
"""
import requests, os, argparse, pickle, time
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "http://quotes.toscrape.com"
LOGIN_URL = urljoin(BASE, "/login")
SESSION_FILE = "ex9_auth/session.pkl"

def create_session():
    s = requests.Session()
    s.headers.update({"User-Agent":"auth-scraper/1.0"})
    return s

def load_session(path=SESSION_FILE):
    if os.path.exists(path):
        try:
            with open(path,"rb") as f:
                return pickle.load(f)
        except:
            return None
    return None

def save_session(session, path=SESSION_FILE):
    with open(path,"wb") as f:
        pickle.dump(session, f)

def login(session, username, password, save=False):
    # get login page to fetch csrf token
    r = session.get(LOGIN_URL, timeout=10); r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    token_tag = soup.select_one("input[name='csrf_token']")
    token = token_tag["value"] if token_tag else ""
    payload = {"username": username, "password": password, "csrf_token": token}
    # submit
    post = session.post(LOGIN_URL, data=payload, timeout=10)
    post.raise_for_status()
    # check if login successful: on this site they redirect to / after login and show "Logout" link
    if "Logout" in post.text or "logout" in post.text.lower():
        print("Login seems successful.")
        if save:
            save_session(session)
            print(f"Session saved to {SESSION_FILE}")
        return True
    else:
        # sometimes the site returns same page with error; try GET profile or other protected page
        print("Login may have failed (no 'Logout' found).")
        return False

def access_protected(session, path="/"):
    url = urljoin(BASE, path)
    r = session.get(url, timeout=10)
    r.raise_for_status()
    return r.text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--save", action="store_true", help="sauvegarder session dans un fichier")
    args = parser.parse_args()

    # try load
    sess = load_session()
    if sess:
        print("Session chargée depuis le disque.")
    else:
        sess = create_session()

    success = login(sess, args.username, args.password, save=args.save)
    if not success:
        print("Tentative de continuer malgré l'échec de login...")

    # Exemple: accéder à la page d'accueil (peut contenir éléments réservés)
    html = access_protected(sess, "/")
    print("Longueur du contenu de la page d'accueil:", len(html))
    # Extraire une info protégée exemple : vérifier presence d'un élément
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html,"lxml")
    if soup.select_one("a[href='/logout']"):
        print("Logout link present -> authentifié")
    else:
        print("Logout link absent -> probablement non authentifié")

if __name__=="__main__":
    main()
