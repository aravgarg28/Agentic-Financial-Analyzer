from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import hashlib
import uuid
from sqlalchemy import text
from app.database import async_session
from app.models import User, Budget

router = APIRouter(prefix="/auth", tags=["Authentication"])

class AuthInput(BaseModel):
    username: str
    password: str

@router.post("/register")
async def register(data: AuthInput):
    if not data.username or not data.password:
        raise HTTPException(status_code=400, detail="Username and password required")
        
    async with async_session() as session:
        # Check if user exists
        result = await session.execute(text("SELECT id FROM users WHERE username = :u"), {"u": data.username})
        if result.scalar():
            raise HTTPException(status_code=400, detail="Username already exists")
            
        # Create user
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        hashed_pw = hashlib.sha256(data.password.encode()).hexdigest()
        
        new_user = User(id=user_id, username=data.username, password_hash=hashed_pw)
        session.add(new_user)
        
        # Create default budgets
        default_budgets = {
            "food": 1500.0, "transport": 2200.0, "shopping": 2500.0,
            "utilities": 750.0, "entertainment": 550.0, "health": 1300.0, "travel": 3000.0,
        }
        for cat, amt in default_budgets.items():
            session.add(Budget(user_id=user_id, category=cat, amount=amt))
            
        await session.commit()
        return {"status": "success", "user_id": user_id, "username": data.username}


@router.post("/login")
async def login(data: AuthInput):
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, password_hash FROM users WHERE username = :u"),
            {"u": data.username}
        )
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=401, detail="Invalid username or password")
            
        hashed_pw = hashlib.sha256(data.password.encode()).hexdigest()
        if hashed_pw != row[1]:
            raise HTTPException(status_code=401, detail="Invalid username or password")
            
        return {"status": "success", "user_id": row[0], "username": data.username}
