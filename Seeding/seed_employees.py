import asyncio
import uuid
from sqlalchemy.future import select

from core.database import AsyncSessionLocal
from models.user import User, Role
from services.user_service import UserService
from utils.schemas.user_schemas import UserCreate

EMPLOYEES_DATA = [
    {"email": "mona.s@shopeasy.com", "name": "Mona El-Shenawy", "role": "Support User"},
    {"email": "hassan.s@shopeasy.com", "name": "Hassan El-Sawy", "role": "Support User"},
    {"email": "amira.k@shopeasy.com", "name": "Amira Khalil", "role": "Support User"},
    {"email": "tarek.n@shopeasy.com", "name": "Tarek Nour", "role": "Support User"},
    {"email": "zainab.g@shopeasy.com", "name": "Zainab Gad", "role": "Support User"},
    
    {"email": "omar.t@shopeasy.com", "name": "Omar El-Masry", "role": "Tech User"},
    {"email": "sherif.a@shopeasy.com", "name": "Sherif Anwar", "role": "Tech User"},
    {"email": "nour.d@shopeasy.com", "name": "Nour El-Din", "role": "Tech User"},
    {"email": "youssef.k@shopeasy.com", "name": "Youssef Kamel", "role": "Tech User"},
    {"email": "mai.m@shopeasy.com", "name": "Mai Mansour", "role": "Tech User"}
]

async def seed_employees():
    async with AsyncSessionLocal() as session:
        print("Checking and seeding roles...")

        role_support_q = await session.execute(select(Role).filter_by(name="Support User"))
        role_support = role_support_q.scalar_one_or_none()
        if not role_support:
            role_support = Role(id=uuid.uuid4(), name="Support User", description="Support agent role")
            session.add(role_support)

        role_tech_q = await session.execute(select(Role).filter_by(name="Tech User"))
        role_tech = role_tech_q.scalar_one_or_none()
        if not role_tech:
            role_tech = Role(id=uuid.uuid4(), name="Tech User", description="Technical support role")
            session.add(role_tech)

        await session.flush()

        roles_map = {
            "Support User": role_support,
            "Tech User": role_tech
        }

        user_service = UserService(session)
        system_creator_id = uuid.uuid4()

        print("\nSeeding 10 employees via UserService...")

        for emp in EMPLOYEES_DATA:
            user_q = await session.execute(select(User).filter_by(email=emp["email"]))
            user_obj = user_q.scalar_one_or_none()
            
            if not user_obj:
                user_data = UserCreate(
                    email=emp["email"],
                    password="Password123",
                    full_name=emp["name"],
                    roles_id=[roles_map[emp["role"]].id]
                )
                
                new_user = await user_service.create_user(user_data, created_by_user_id=system_creator_id)
                
                new_user.email_confirmed = True
                session.add(new_user)
                await session.commit()
                
                print(f"Employee created: {emp['name']} ({emp['role']}) - Email Confirmed")
            else:
                print(f"Employee {emp['name']} already exists.")

        print("\n=== Seeding completed successfully. All records & audit logs saved ===")

if __name__ == "__main__":
    asyncio.run(seed_employees())