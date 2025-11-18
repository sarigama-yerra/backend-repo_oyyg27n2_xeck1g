import os
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import hashlib

from database import db, create_document, get_documents
from schemas import User as UserSchema, Booking as BookingSchema, Offering as OfferingSchema

app = FastAPI(title="Pliva Retreat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------- Helpers -------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def daterange(start_date: date, end_date: date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


# ------- Seed offerings in DB if missing -------

def ensure_offerings():
    if db is None:
        return
    existing = list(db["offering"].find({}))
    if existing:
        return
    offerings: List[OfferingSchema] = [
        OfferingSchema(
            id="van",
            title="Fully Equipped Camper Van",
            description="Cozy van with kitchenette, comfy bed, and everything you need to chase sunsets by the Pliva river.",
            price_per_night=55.0,
            max_guests=2,
            amenities=["Kitchenette", "Bed linens", "Portable shower", "Heater", "Solar power"],
            photos=[
                "/images/van-1.jpg",
                "/images/van-2.jpg",
            ],
        ),
        OfferingSchema(
            id="cabin",
            title="Renovated Container Cabin",
            description="Minimalist, warm cabin tucked in nature near the river and mountains.",
            price_per_night=65.0,
            max_guests=3,
            amenities=["Queen bed", "Fire pit", "River access", "Mountain view", "Wi‑Fi"],
            photos=[
                "/images/cabin-1.jpg",
                "/images/cabin-2.jpg",
            ],
        ),
    ]
    for off in offerings:
        create_document("offering", off.model_dump())


ensure_offerings()

# ------- Models for auth requests -------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AvailabilityRequest(BaseModel):
    offering_id: str
    start_date: date
    end_date: date


# ------- Routes -------
@app.get("/")
def root():
    return {"message": "Pliva Retreat API running"}


@app.get("/offerings")
def list_offerings():
    docs = get_documents("offering")
    # Convert ObjectId to string-safe
    for d in docs:
        d["_id"] = str(d.get("_id"))
    return {"items": docs}


@app.post("/register")
def register(payload: RegisterRequest):
    existing = db["user"].find_one({"email": payload.email}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = UserSchema(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        avatar_url=None,
    )
    uid = create_document("user", user)
    return {"ok": True, "user_id": uid}


@app.post("/login")
def login(payload: LoginRequest):
    u = db["user"].find_one({"email": payload.email}) if db else None
    if not u or u.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = hash_password(payload.email + "|" + str(datetime.utcnow()))
    return {"ok": True, "token": token, "name": u.get("name"), "email": u.get("email")}


@app.post("/availability")
def check_availability(req: AvailabilityRequest):
    # Gather bookings overlapping the range for this offering
    query = {
        "offering_id": req.offering_id,
        "$or": [
            {"start_date": {"$lt": req.end_date.isoformat()}, "end_date": {"$gt": req.start_date.isoformat()}},
        ],
    }
    bookings = list(db["booking"].find(query)) if db else []

    unavailable = set()
    for b in bookings:
        b_start = date.fromisoformat(b["start_date"]) if isinstance(b["start_date"], str) else b["start_date"].date()
        b_end = date.fromisoformat(b["end_date"]) if isinstance(b["end_date"], str) else b["end_date"].date()
        for d in daterange(b_start, b_end):
            unavailable.add(d.isoformat())

    days = []
    for d in daterange(req.start_date, req.end_date):
        days.append({
            "date": d.isoformat(),
            "available": d.isoformat() not in unavailable
        })
    return {"days": days}


class CreateBookingRequest(BaseModel):
    user_email: EmailStr
    offering_id: str
    start_date: date
    end_date: date
    guests: int


@app.post("/book")
def create_booking(req: CreateBookingRequest):
    # Validate offering exists
    off = db["offering"].find_one({"id": req.offering_id}) if db else None
    if not off:
        raise HTTPException(status_code=404, detail="Offering not found")

    # Conflict check
    conflict = db["booking"].find_one({
        "offering_id": req.offering_id,
        "$or": [
            {"start_date": {"$lt": req.end_date.isoformat()}, "end_date": {"$gt": req.start_date.isoformat()}},
        ],
        "status": {"$ne": "cancelled"}
    }) if db else None

    if conflict:
        raise HTTPException(status_code=400, detail="Selected dates are no longer available")

    nights = (req.end_date - req.start_date).days
    if nights <= 0:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    total = float(off.get("price_per_night", 0)) * nights

    booking = BookingSchema(
        user_email=req.user_email,
        offering_id=req.offering_id,
        start_date=req.start_date,
        end_date=req.end_date,
        guests=req.guests,
        total_price=total,
        status="confirmed",
        note=None,
    )
    bid = create_document("booking", booking)
    return {"ok": True, "booking_id": bid, "total_price": total}


@app.get("/bookings")
def my_bookings(email: EmailStr):
    items = list(db["booking"].find({"user_email": email}).sort("created_at", -1)) if db else []
    for it in items:
        it["_id"] = str(it.get("_id"))
    return {"items": items}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
