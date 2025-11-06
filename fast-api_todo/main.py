from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import Base, engine, SessionLocal
from models import Todo

app = FastAPI(title="FastAPI Todo Challenge")

# Création automatique de la base
Base.metadata.create_all(bind=engine)

# Dépendance de session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def home():
    return {"message": "Bienvenue dans le TP FastAPI - Todo API"}

# 1 Lire toutes les tâches
@app.get("/todos")
def read_todos(db: Session = Depends(get_db)):
    return db.query(Todo).all()

# 2 Créer une nouvelle tâche
@app.post("/todos")
def create_todo(title: str, description: str = "", db: Session = Depends(get_db)):
    todo = Todo(title=title, description=description)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo

# 3 Mettre à jour une tâche
@app.put("/todos/{todo_id}")
def update_todo(todo_id: int, completed: bool, db: Session = Depends(get_db)):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    todo.completed = completed
    db.commit()
    db.refresh(todo)
    return todo

# 4 Supprimer une tâche
@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    db.delete(todo)
    db.commit()
    return {"message": "Tâche supprimée"}

@app.get("/todos/completed")
def read_completed_todos(db: Session = Depends(get_db)):
    return db.query(Todo).filter(Todo.completed == True).all()

