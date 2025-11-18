"""
Database Schemas for Pliva Retreat

Each Pydantic model represents a MongoDB collection.
Collection name is the lowercase of the class name.
"""
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr
from datetime import date

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    avatar_url: Optional[str] = Field(None, description="Profile image URL")

class Offering(BaseModel):
    id: str = Field(..., description="Unique ID e.g. 'van' or 'cabin'")
    title: str
    description: str
    price_per_night: float = Field(..., ge=0)
    max_guests: int = Field(..., ge=1)
    amenities: List[str] = []
    photos: List[str] = []

class Booking(BaseModel):
    user_email: EmailStr
    offering_id: str = Field(..., description="'van' or 'cabin'")
    start_date: date
    end_date: date
    guests: int = Field(..., ge=1)
    total_price: float = Field(..., ge=0)
    status: str = Field("pending", description="pending | confirmed | cancelled")
    note: Optional[str] = None
