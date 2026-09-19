import sqlite3
import hashlib
import secrets
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

app = FastAPI(title="Nexora Enterprise API", version="2.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "backend/nexora.db"

def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Inquiries table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            service_interested TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Users table for client/admin login
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            role TEXT DEFAULT 'client',
            session_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Pydantic Schemas ---
class UserRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    service_interested: str
    message: str

class EstimateRequest(BaseModel):
    project_type: str
    pages_count: int
    needs_auth: bool
    needs_payment_gateway: bool

# --- Helpers ---
def get_user_by_token(token: Optional[str] = Header(None, alias="X-Auth-Token")):
    if not token:
        return None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, email, role FROM users WHERE session_token = ?", (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "full_name": row[1], "email": row[2], "role": row[3]}
    return None

# --- Routes ---

@app.get("/")
def root():
    return {"status": "online", "system": "Nexora Production Engine v2.0"}

# Authentication Endpoints
@app.post("/api/auth/register")
def register(user: UserRegister):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    salt = secrets.token_hex(16)
    hashed_pwd = hash_password(user.password, salt)
    token = secrets.token_hex(24)
    try:
        cursor.execute(
            "INSERT INTO users (full_name, email, salt, hashed_password, session_token) VALUES (?, ?, ?, ?, ?)",
            (user.full_name, user.email.lower(), salt, hashed_pwd, token)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return {
            "token": token,
            "user": {"id": user_id, "full_name": user.full_name, "email": user.email, "role": "client"}
        }
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Account with this email already exists.")

@app.post("/api/auth/login")
def login(creds: UserLogin):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, email, salt, hashed_password, role FROM users WHERE email = ?", (creds.email.lower(),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    
    user_id, name, email, salt, stored_hash, role = row
    if hash_password(creds.password, salt) != stored_hash:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    
    token = secrets.token_hex(24)
    cursor.execute("UPDATE users SET session_token = ? WHERE id = ?", (token, user_id))
    conn.commit()
    conn.close()
    return {
        "token": token,
        "user": {"id": user_id, "full_name": name, "email": email, "role": role}
    }

@app.get("/api/auth/me")
def get_current_session(user: dict = Depends(get_user_by_token)):
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    
    # Also fetch client's submitted inquiries
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, service_interested, status, created_at FROM inquiries WHERE email = ? ORDER BY id DESC", (user["email"],))
    inquiries = [{"id": r[0], "service": r[1], "status": r[2], "date": r[3]} for r in cursor.fetchall()]
    conn.close()
    
    return {"user": user, "my_inquiries": inquiries}

# Services Catalog
@app.get("/api/services")
def get_services():
    return [
        {"title": "Custom Web Applications", "desc": "Production-grade microservices and single-page apps engineered with Python/FastAPI, modern UI paradigms, and asynchronous task workers."},
        {"title": "Bespoke ERP & CRM Engines", "desc": "Centralized workflow orchestration, relational database optimization, inventory pipelines, and permission matrices."},
        {"title": "SaaS Engineering & API Ecosystems", "desc": "Multi-tenant platforms with isolated data pipelines, secure Stripe billing integration, and sub-100ms REST/GraphQL endpoints."},
        {"title": "Cloud Infrastructure & DevOps", "desc": "Dockerized CI/CD pipelines, container orchestration, SSL/TLS zero-trust configuration, and real-time APM telemetry."}
    ]

# Dynamic Portfolio Case Studies
@app.get("/api/portfolio")
def get_portfolio():
    return [
        {
            "id": 1,
            "title": "OmniFlow Real Estate CRM",
            "category": "erp",
            "tag": "ERP / CRM",
            "image": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=800&q=80",
            "desc": "Automated inventory management and lead conversion platform with multi-tiered agent commission matrices.",
            "stat": "+40% Conversion Velocity",
            "tech": "FastAPI • PostgreSQL • Vue"
        },
        {
            "id": 2,
            "title": "Vanguard Cloud Analytics",
            "category": "saas",
            "tag": "SaaS Platform",
            "image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=80",
            "desc": "High-throughput telemetry ingestion platform processing over 10,000 telemetry events per second.",
            "stat": "< 80ms P95 Latency",
            "tech": "Python • TimescaleDB • Redis"
        },
        {
            "id": 3,
            "title": "PrimeSupply B2B Commerce",
            "category": "web",
            "tag": "Web Architecture",
            "image": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=800&q=80",
            "desc": "Enterprise wholesale ordering system with real-time tax calculation, custom invoicing, and multi-currency checkout.",
            "stat": "99.99% Checkout Uptime",
            "tech": "FastAPI • React • Docker"
        }
    ]

# Estimator Endpoint
@app.post("/api/estimate")
def calculate_estimate(data: EstimateRequest):
    base_cost = {"Web App": 25000, "Mobile App": 35000, "Enterprise Architecture": 60000}.get(data.project_type, 30000)
    pages_cost = data.pages_count * 2500
    auth_cost = 8000 if data.needs_auth else 0
    payment_cost = 10000 if data.needs_payment_gateway else 0
    total = base_cost + pages_cost + auth_cost + payment_cost
    weeks = max(2, round(data.pages_count * 0.4 + (2 if data.needs_auth else 0) + (1.5 if data.needs_payment_gateway else 0)))
    return {"estimated_price_inr": total, "delivery_timeline_weeks": weeks}

# Contact / Inquiry Endpoint
@app.post("/api/contact")
def create_contact(inquiry: ContactRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO inquiries (name, email, service_interested, message) VALUES (?, ?, ?, ?)",
        (inquiry.name, inquiry.email, inquiry.service_interested, inquiry.message)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Inquiry recorded successfully. Our solutions team will review and contact you."}