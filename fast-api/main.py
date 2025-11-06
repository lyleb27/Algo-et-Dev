from fastapi import FastAPI


app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur votre première API FastAPI !"}

@app.get("/hello/{name}")
def say_hello(name: str):
    return {"message": f"Bonjour {name}, ravi de te voir ici !"}

# Démarrage du serveur :
# uvicorn main:app --reload

from pydantic import BaseModel
class Utilisateur(BaseModel):
    nom: str
    age: int
    email: str

@app.post("/utilisateur/")
def creer_utilisateur(user: Utilisateur):
    return {"message": f"Utilisateur {user.nom} ajouté avec succès."}

@app.get("/produit/")
def lire_produit(nom: str = "Inconnu", prix: float = 0.0):
    return {"produit": nom, "prix": prix}

fake_db = []
@app.post("/items/")
def create_item(item: dict):
    fake_db.append(item)
    return {"db_size": len(fake_db)}

@app.get("/items/")
def list_items():
    return {"items": fake_db}

from fastapi import Depends, HTTPException

def get_token_header(token: str = "12345"):
    if token != "12345":
        raise HTTPException(status_code=400, detail="Token invalide")
    return token

@app.get("/secure-data/", dependencies=[Depends(get_token_header)])
def secure_data():
    return {"message": "Accès autorisé"}