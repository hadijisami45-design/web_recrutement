from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, DECIMAL, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.sql import func
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import os
import time
import hashlib
from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles
import shutil

# Configuration de la base de données
DATABASE_URL = "mysql+pymysql://app_user:app_password@mysql:3306/recruitment_db"

# Fonction pour créer le engine avec reconnexion
def get_engine():
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            engine = create_engine(DATABASE_URL)
            # Test de connexion
            with engine.connect() as conn:
                print("✅ Connexion à MySQL réussie!")
            return engine
        except Exception as e:
            print(f"❌ Tentative {attempt + 1}/{max_retries} - Échec de connexion: {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Attente de {retry_delay} secondes avant réessai...")
                time.sleep(retry_delay)
            else:
                print("❌ Échec de connexion à la base de données après plusieurs tentatives")
                return None

# Créer le moteur
engine = get_engine()

if engine is None:
    print("⚠️ Mode sans base de données - certaines fonctionnalités seront limitées")
    engine = create_engine("sqlite:///./temp.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configuration pour les fichiers uploadés
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Modèles SQLAlchemy
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(Enum('admin', 'client'), default='client')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jobs = relationship("Job", back_populates="owner")
    applications = relationship("Application", back_populates="applicant")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    company = Column(String(100), nullable=False)
    location = Column(String(100), nullable=False)
    salary = Column(DECIMAL(10, 2))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="jobs")
    applications = relationship("Application", back_populates="job")

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    cv_filename = Column(String(255))  # Nom du fichier CV
    cover_letter = Column(Text)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="applications")
    applicant = relationship("User", back_populates="applications")

# Création des tables
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tables créées avec succès!")
except Exception as e:
    print(f"⚠️ Erreur lors de la création des tables: {e}")

# Configuration de l'authentification
SECRET_KEY = "your-secret-key-here-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Fonctions de hashage simplifiées (sans bcrypt)
def get_password_hash(password: str) -> str:
    """Hash un mot de passe avec SHA256 (pour simplifier, en production utiliser bcrypt)"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe hashé"""
    return get_password_hash(plain_password) == hashed_password

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Dépendance de base de données
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        print(f"❌ Erreur de base de données: {e}")
        raise HTTPException(status_code=500, detail="Erreur de base de données")
    finally:
        db.close()

# Schémas Pydantic
class UserBase(BaseModel):
    id: int
    username: str
    email: str
    role: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class JobBase(BaseModel):
    title: str
    description: str
    company: str
    location: str
    salary: Optional[float] = None

class JobCreate(JobBase):
    pass

class ApplicationCreate(BaseModel):
    cover_letter: str
    user_id: int

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserBase

# Initialisation de FastAPI
app = FastAPI(title="Recruitment API")

# Montez le dossier static pour servir les fichiers
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://frontend:5000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route de santé
@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "Recruitment API is running"}

@app.get("/")
def read_root():
    return {"message": "Recruitment API - Backend is working!"}

# Routes d'authentification
@app.post("/register", response_model=UserBase)
def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        # Vérifier si l'utilisateur existe déjà
        db_user = db.query(User).filter(User.username == user.username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Nom d'utilisateur déjà utilisé")
        
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email déjà utilisé")
        
        # Créer le nouvel utilisateur
        hashed_password = get_password_hash(user.password)
        db_user = User(
            username=user.username,
            email=user.email,
            password=hashed_password,
            role='client'
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        return UserBase(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            role=db_user.role
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'inscription: {str(e)}")

@app.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    try:
        db_user = db.query(User).filter(User.username == user.username).first()
        if not db_user:
            raise HTTPException(status_code=400, detail="Utilisateur non trouvé")
        
        if not verify_password(user.password, db_user.password):
            raise HTTPException(status_code=400, detail="Mot de passe incorrect")
        
        access_token = create_access_token(
            data={"sub": db_user.username}, 
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": db_user.id,
                "username": db_user.username,
                "email": db_user.email,
                "role": db_user.role
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la connexion: {str(e)}")

# Routes pour les annonces
@app.get("/jobs", response_model=List[dict])
def get_jobs(db: Session = Depends(get_db)):
    try:
        jobs = db.query(Job).all()
        return [
            {
                "id": job.id,
                "title": job.title,
                "description": job.description,
                "company": job.company,
                "location": job.location,
                "salary": float(job.salary) if job.salary else None,
                "created_by": job.created_by
            }
            for job in jobs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des annonces: {str(e)}")

@app.post("/jobs")
def create_job(job: JobCreate, db: Session = Depends(get_db)):
    try:
        db_job = Job(
            title=job.title,
            description=job.description,
            company=job.company,
            location=job.location,
            salary=job.salary
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        
        return {
            "id": db_job.id,
            "title": db_job.title,
            "description": db_job.description,
            "company": db_job.company,
            "location": db_job.location,
            "salary": float(db_job.salary) if db_job.salary else None,
            "created_by": db_job.created_by
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création de l'annonce: {str(e)}")

@app.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Annonce non trouvée")
        
        db.delete(job)
        db.commit()
        return {"message": "Annonce supprimée avec succès"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")

# Route pour uploader un CV
@app.post("/upload-cv/")
async def upload_cv(file: UploadFile = File(...)):
    try:
        # Vérifier que c'est un PDF
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés")
        
        # Générer un nom de fichier unique
        unique_filename = f"cv_{int(time.time())}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        # Sauvegarder le fichier
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {"filename": unique_filename, "message": "CV uploadé avec succès"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload: {str(e)}")

# Route pour postuler avec fichier
@app.post("/jobs/{job_id}/apply")
async def apply_to_job(
    job_id: int, 
    cover_letter: str,
    user_id: int,
    cv_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        # Upload du CV
        if not cv_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés")
        
        unique_filename = f"cv_{int(time.time())}_{cv_file.filename}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(cv_file.file, buffer)
        
        # Vérifier si l'annonce existe
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Annonce non trouvée")
        
        # Vérifier si l'utilisateur existe
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        db_application = Application(
            job_id=job_id,
            user_id=user_id,
            cv_filename=unique_filename,
            cover_letter=cover_letter
        )
        db.add(db_application)
        db.commit()
        db.refresh(db_application)
        
        return {
            "id": db_application.id,
            "job_id": db_application.job_id,
            "user_id": db_application.user_id,
            "cv_filename": db_application.cv_filename,
            "message": "Candidature envoyée avec succès"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la candidature: {str(e)}")

# Route pour récupérer les candidatures d'un job
@app.get("/jobs/{job_id}/applications")
def get_job_applications(job_id: int, db: Session = Depends(get_db)):
    try:
        applications = db.query(Application).filter(Application.job_id == job_id).all()
        return [
            {
                "id": app.id,
                "user_id": app.user_id,
                "username": app.applicant.username,
                "email": app.applicant.email,
                "cv_filename": app.cv_filename,
                "cover_letter": app.cover_letter,
                "applied_at": app.applied_at.isoformat(),
                "job_title": app.job.title
            }
            for app in applications
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")


@app.get("/applications")
def get_all_applications(db: Session = Depends(get_db)):
    try:
        applications = db.query(Application).all()
        return [
            {
                "id": app.id,
                "job_id": app.job_id,
                "job_title": app.job.title,
                "user_id": app.user_id,
                "username": app.applicant.username,
                "email": app.applicant.email,
                "cv_filename": app.cv_filename,
                "cover_letter": app.cover_letter,
                "applied_at": app.applied_at.isoformat()
            }
            for app in applications
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")

# Routes admin
@app.get("/users", response_model=List[UserBase])
def get_users(db: Session = Depends(get_db)):
    try:
        users = db.query(User).all()
        return [
            UserBase(
                id=user.id,
                username=user.username,
                email=user.email,
                role=user.role
            )
            for user in users
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des utilisateurs: {str(e)}")

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        if user.role == 'admin':
            raise HTTPException(status_code=400, detail="Impossible de supprimer un administrateur")
        
        db.delete(user)
        db.commit()
        return {"message": "Utilisateur supprimé avec succès"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")

print("🚀 Backend FastAPI prêt à démarrer!")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)