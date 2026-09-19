import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# --- Configuration & Security ---
ADMIN_SECRET_KEY = "nexora_admin_secret_2026"
api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "your-email@gmail.com"
SENDER_PASSWORD = "your-app-password"  # Google App Password
ADMIN_NOTIFICATION_RECEIVER = "your-email@gmail.com"

# --- Database Setup (SQLite) ---
DATABASE_URL = "sqlite:///./nexora.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ContactLead(Base):
    __tablename__ = "contact_leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    service_interested = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="New")  # New, Contacted, In Progress, Closed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas ---
class ContactMessage(BaseModel):
    name: str
    email: EmailStr
    service_interested: str
    message: str

class LeadStatusUpdate(BaseModel):
    status: str

class QuoteRequest(BaseModel):
    project_type: str
    pages_count: int
    needs_auth: bool
    needs_payment_gateway: bool

# --- FastAPI Initialization ---
app = FastAPI(
    title="Nexora API",
    version="1.2.0",
    description="Full-featured API backend for Nexora IT platform"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_admin(api_key: str = Security(api_key_header)):
    if api_key != ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing Admin Key"
        )
    return api_key

# --- Helper Functions ---
def send_lead_notification_email(lead_name: str, lead_email: str, service: str, message: str):
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = ADMIN_NOTIFICATION_RECEIVER
        msg["Subject"] = f"New Lead Captured: {lead_name} ({service})"

        body = f"""New inquiry captured:

Name: {lead_name}
Email: {lead_email}
Service: {service}
Message:
{message}
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Background email notification failed: {e}")

# --- Public Endpoints ---

@app.get("/")
def read_root():
    return {"status": "success", "message": "Nexora backend is live"}

@app.get("/api/services")
def get_services():
    return [
        {
            "id": 1,
            "title": "Full-Stack Web Development",
            "desc": "Scalable modern web apps built with Python FastAPI and reactive frontends."
        },
        {
            "id": 2,
            "title": "Cloud & DevOps Architecture",
            "desc": "Containerized deployments, automated CI/CD pipelines, and cloud infrastructure management."
        },
        {
            "id": 3,
            "title": "Corporate IT Training",
            "desc": "Hands-on, industry-grade training covering modern Python stacks and microservices."
        }
    ]

@app.post("/api/estimate")
def estimate_cost(quote: QuoteRequest):
    base_price = 15000  # Base cost in INR
    price = base_price + (quote.pages_count * 2000)

    if quote.needs_auth:
        price += 8000
    if quote.needs_payment_gateway:
        price += 10000

    timeline = 2 + (quote.pages_count // 3)

    return {
        "estimated_price_inr": price,
        "delivery_timeline_weeks": timeline
    }

@app.post("/api/contact")
def submit_contact(
    data: ContactMessage,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    new_lead = ContactLead(
        name=data.name,
        email=data.email,
        service_interested=data.service_interested,
        message=data.message,
        status="New"
    )
    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)

    # Queue email task without blocking the response
    background_tasks.add_task(
        send_lead_notification_email,
        data.name,
        data.email,
        data.service_interested,
        data.message
    )

    return {
        "status": "success",
        "message": "Query saved successfully. Our team will contact you shortly!",
        "lead_id": new_lead.id
    }

# --- Protected Admin Endpoints ---

@app.get("/api/admin/leads", dependencies=[Depends(verify_admin)])
def get_leads(
    status: Optional[str] = Query(None, description="Filter leads by status: New, Contacted, Closed"),
    db: Session = Depends(get_db)
):
    query = db.query(ContactLead)
    if status:
        query = query.filter(ContactLead.status == status)
    return query.order_by(ContactLead.id.desc()).all()

@app.patch("/api/admin/leads/{lead_id}", dependencies=[Depends(verify_admin)])
def update_lead_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db)
):
    lead = db.query(ContactLead).filter(ContactLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = payload.status
    db.commit()
    db.refresh(lead)
    return {"status": "success", "message": f"Lead #{lead_id} updated to {payload.status}"}

@app.delete("/api/admin/leads/{lead_id}", dependencies=[Depends(verify_admin)])
def delete_lead(
    lead_id: int,
    db: Session = Depends(get_db)
):
    lead = db.query(ContactLead).filter(ContactLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    db.delete(lead)
    db.commit()
    return {"status": "success", "message": f"Lead #{lead_id} removed permanently"}