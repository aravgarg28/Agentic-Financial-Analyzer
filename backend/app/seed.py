"""
Seed script — generates 500 realistic financial transactions.
Run: python -m app.seed
"""
import asyncio
import random
from datetime import datetime, timedelta
from app.database import engine, async_session, Base
from app.models import Transaction, User, Budget
import hashlib

# Realistic merchant names per category
MERCHANTS = {
    "food": [
        "Whole Foods Market", "Trader Joe's", "Chipotle", "Starbucks",
        "Domino's Pizza", "McDonald's", "Panera Bread", "Sweetgreen",
        "Shake Shack", "Chick-fil-A", "Subway", "Panda Express",
    ],
    "transport": [
        "Uber", "Lyft", "Shell Gas Station", "BP Fuel", "MTA Metro",
        "Delta Airlines", "United Airlines", "Amtrak", "Chevron",
        "Hertz Car Rental",
    ],
    "shopping": [
        "Amazon", "Target", "Walmart", "Best Buy", "Nike Store",
        "Apple Store", "Nordstrom", "IKEA", "Costco", "Home Depot",
        "Etsy", "Zara",
    ],
    "utilities": [
        "Con Edison Electric", "National Grid Gas", "Verizon Wireless",
        "AT&T Internet", "Spectrum Cable", "Water Authority",
        "T-Mobile", "Xfinity",
    ],
    "entertainment": [
        "Netflix", "Spotify", "AMC Theatres", "Disney+", "Hulu",
        "Steam Games", "Ticketmaster", "HBO Max", "YouTube Premium",
        "PlayStation Store",
    ],
    "health": [
        "CVS Pharmacy", "Walgreens", "Planet Fitness", "Equinox Gym",
        "Dr. Smith Medical", "Quest Diagnostics", "Cigna Insurance",
        "Peloton", "MinuteClinic",
    ],
    "travel": [
        "Marriott Hotels", "Airbnb", "Booking.com", "Hilton Hotels",
        "Expedia", "Southwest Airlines", "Kayak Travel",
    ],
    "income": [
        "Employer Direct Deposit", "Freelance Payment", "Stock Dividend",
        "Interest Income", "Tax Refund", "Side Project Revenue",
    ],
}

# Spending ranges per category (min, max)
AMOUNT_RANGES = {
    "food": (5.0, 85.0),
    "transport": (8.0, 250.0),
    "shopping": (15.0, 400.0),
    "utilities": (30.0, 200.0),
    "entertainment": (5.0, 60.0),
    "health": (10.0, 300.0),
    "travel": (50.0, 1500.0),
    "income": (1500.0, 6000.0),
}

DESCRIPTIONS = {
    "food": "Meal / groceries purchase",
    "transport": "Transportation expense",
    "shopping": "Retail purchase",
    "utilities": "Monthly utility bill",
    "entertainment": "Entertainment subscription or event",
    "health": "Healthcare or fitness expense",
    "travel": "Travel booking or accommodation",
    "income": "Income deposit",
}


def generate_transactions(n: int = 500, user_id: str = "user_1") -> list[dict]:
    """Generate n realistic transactions spread over the last 6 months."""
    transactions = []
    now = datetime.utcnow()
    categories = list(MERCHANTS.keys())
    # Weight categories so income is less frequent
    weights = [15, 10, 15, 8, 12, 8, 7, 5]

    for _ in range(n):
        category = random.choices(categories, weights=weights, k=1)[0]
        merchant = random.choice(MERCHANTS[category])
        lo, hi = AMOUNT_RANGES[category]
        amount = round(random.uniform(lo, hi), 2)
        # Income is positive, expenses are negative in display but stored positive
        days_ago = random.randint(0, 180)
        hours_offset = random.randint(0, 23)
        ts = now - timedelta(days=days_ago, hours=hours_offset)

        transactions.append(
            {
                "user_id": user_id,
                "merchant": merchant,
                "amount": amount if category == "income" else -amount,
                "category": category,
                "timestamp": ts,
                "description": f"{DESCRIPTIONS[category]} at {merchant}",
            }
        )
    return transactions


async def seed():
    """Drop and recreate tables, then insert seed data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created")

    rows = generate_transactions(500)
    async with async_session() as session:
        # Create default user
        user = User(
            id="user_1",
            username="player1",
            password_hash=hashlib.sha256("password".encode()).hexdigest()
        )
        session.add(user)
        
        # Create default budgets
        default_budgets = {
            "food": 1500.0, "transport": 2200.0, "shopping": 4500.0,
            "utilities": 1500.0, "entertainment": 600.0, "health": 1800.0, "travel": 7000.0,
        }
        for cat, amt in default_budgets.items():
            session.add(Budget(user_id="user_1", category=cat, amount=amt))

        for row in rows:
            session.add(Transaction(**row))
        await session.commit()
    print(f"✅ Seeded users, budgets, and {len(rows)} transactions")


if __name__ == "__main__":
    asyncio.run(seed())
