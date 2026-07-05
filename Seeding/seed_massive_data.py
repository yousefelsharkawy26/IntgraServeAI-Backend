import asyncio
import uuid
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy.future import select
from sqlalchemy import insert
from passlib.context import CryptContext

from core.database import AsyncSessionLocal
from models.user import User, Role, user_roles
from models.ticket import Ticket, TicketMessage, TicketStatus, TicketPriority, TicketType, SenderType

# Password hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Name generator matrices
FIRST_NAMES = ["Ahmed", "Mohamed", "Sara", "Khaled", "Mona", "Youssef", "Abdallah", "Hassan", "Fatma", "Layan", 
               "Faisal", "Amira", "Omar", "Nour", "Ibrahim", "Ali", "Maryam", "Maha", "Fahad", "Saad", 
               "Hana", "Deena", "Reem", "Sultan", "Jawahir", "Naif", "Saleh", "Hind", "Tareq", "Zainab"]

LAST_NAMES = ["Al-Harbi", "Al-Otaibi", "El-Masry", "Al-Qahtani", "Al-Sudairi", "Al-Ghamdi", "Al-Shammari", 
              "Al-Dossari", "Al-Rashid", "Al-Fayez", "El-Sawy", "Anwar", "Nour", "Gad", "Kamel", 
              "Al-Jamil", "Al-Saddoun", "Al-Hassan", "Al-Saleh", "Al-Bakr"]

# Ticket templates matrices
TECH_SUBJECTS = [
    "Payment Gateway Error {}", "Database Sync Failure {}", "MFA Login Lockout {}", 
    "GraphQL Complexity Block on Cart {}", "Apple Pay Tokenization Failure {}", 
    "Tamara Installment Callback Lock {}", "Redis Session Expiry on Flash Sale {}", 
    "CDN DDoS False Positive on Checkout {}", "API Webhook Shipping Loop {}"
]
TECH_DESCRIPTIONS = [
    "User reported error code {} during checkout process. DB transactions rolled back.",
    "Session sync timed out. Cart is empty but payment cleared. Transaction Reference: TXN-{}.",
    "Multi-factor authentication blocked. Customer swapped SIM card and lost access to number {}.",
    "GraphQL query exceeded default nesting depth of 15. Active cart contains {} items."
]

SUPPORT_SUBJECTS = [
    "Damaged Delivery Claim {}", "Request for Refund on Cancelled Order {}", 
    "Stolen Card Fraud Dispute {}", "Cross-Border Customs Clearance Delay {}", 
    "Empty Sealed Box Discrepancy {}", "Gift Card Redemption Lock {}", 
    "SLA Delay with SMSA Delivery {}", "Request for Address Modification {}"
]
SUPPORT_DESCRIPTIONS = [
    "Customer received fragile item broken during transit. Aramex tracking ID: SH-{}.",
    "Order #{} was cancelled prior to shipment but bank has not released the pre-authorization hold.",
    "Bank filed a legal dispute for order #{} stating credit card was used without authorization."
]

CUSTOMER_MESSAGES = [
    "Hello, I am facing an urgent issue with my order. Please check this as soon as possible.",
    "أهلاً، أواجه مشكلة حرجة جداً في عملية الشحن ولم يتواصل معي المندوب بعد.",
    "I tried reaching out via live chat but the AI assistant referred me to human support.",
    "الرجاء معالجة الطلب بسرعة، العطل تسبب في إيقاف حسابي بشكل كامل."
]

AGENT_MESSAGES = [
    "Hello, I have reviewed your logs. I am forwarding this case to our engineering team for immediate patch.",
    "مرحباً بك، اطلعت على المشكلة وجاري العمل على حل العطل وتحديث تذكرتك فوراً.",
    "We have contacted our logistics partner to resolve this delay. Thank you for your patience.",
    "I have manually overridden the system lock on your account. Please try logging in now."
]

def generate_random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

async def seed_massive_data():
    async with AsyncSessionLocal() as session:
        print("=== Step 1: Pre-hashing Password ===")
        # Hash password once to save massive processing time (reused for 10k users)
        prehashed_password = pwd_context.hash("Password123")
        print("Password pre-hashed successfully.")

        print("\n=== Step 2: Fetching / Creating Roles ===")
        role_support_q = await session.execute(select(Role).filter_by(name="Support User"))
        role_support = role_support_q.scalar_one_or_none()
        if not role_support:
            role_support = Role(id=uuid.uuid4(), name="Support User", description="Support Agent")
            session.add(role_support)

        role_tech_q = await session.execute(select(Role).filter_by(name="Tech User"))
        role_tech = role_tech_q.scalar_one_or_none()
        if not role_tech:
            role_tech = Role(id=uuid.uuid4(), name="Tech User", description="Tech Agent")
            session.add(role_tech)
        
        await session.flush()
        role_support_id = role_support.id
        role_tech_id = role_tech.id

        # --------------------------------------------------------------------
        # Generating 10,000 Employees
        # --------------------------------------------------------------------
        print("\n=== Step 3: Preparing 10,000 Employees ===")
        employees_list = []
        user_roles_list = []
        now = datetime.now(timezone.utc)

        # Distribute: 5,000 Tech, 5,000 Support
        for i in range(1, 10001):
            user_id = uuid.uuid4()
            role_id = role_tech_id if i <= 5000 else role_support_id
            role_name = "tech" if i <= 5000 else "support"
            email = f"agent.{role_name}.{i}@shopeasy.com"
            name = generate_random_name()

            employees_list.append({
                "id": user_id,
                "email": email,
                "email_confirmed": True,
                "password_hash": prehashed_password,
                "full_name": name,
                "is_active": True,
                "created_at": now - timedelta(days=30),
                "updated_at": now
            })

            user_roles_list.append({
                "user_id": user_id,
                "role_id": role_id,
                "assigned_at": now - timedelta(days=30)
            })

        print("Bulk inserting 10,000 employees into database...")
        # Insert in batches of 2,500
        for i in range(0, len(employees_list), 2500):
            batch_users = employees_list[i:i+2500]
            batch_roles = user_roles_list[i:i+2500]
            await session.execute(insert(User), batch_users)
            await session.execute(insert(user_roles), batch_roles)
            print(f"-> Inserted employees batch {i+2500}/10000")
        
        await session.commit()
        print("All 10,000 employees saved successfully.")

        # Split employee lists for ticket assignment
        tech_agent_ids = [emp["id"] for emp in employees_list if emp["id"] in [ur["user_id"] for ur in user_roles_list if ur["role_id"] == role_tech_id]]
        support_agent_ids = [emp["id"] for emp in employees_list if emp["id"] in [ur["user_id"] for ur in user_roles_list if ur["role_id"] == role_support_id]]

        # --------------------------------------------------------------------
        # Generating 100,000 Tickets
        # --------------------------------------------------------------------
        print("\n=== Step 4: Preparing 100,000 Tickets & Messages ===")
        tickets_batch = []
        messages_batch = []
        
        ticket_statuses = [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED]
        ticket_priorities = [TicketPriority.LOW, TicketPriority.MEDIUM, TicketPriority.HIGH, TicketPriority.URGENT]

        total_tickets = 100000
        batch_size = 5000

        print(f"Generating and bulk inserting {total_tickets} tickets in batches of {batch_size}...")

        for i in range(1, total_tickets + 1):
            ticket_id = uuid.uuid4()
            ticket_type = random.choice([TicketType.TECH, TicketType.SUPPORT])
            status = random.choice(ticket_statuses)
            priority = random.choice(ticket_priorities)
            
            # Select random assignee based on type
            assignee_id = random.choice(tech_agent_ids) if ticket_type == TicketType.TECH else random.choice(support_agent_ids)
            
            # Generate random customer info
            cust_name = generate_random_name()
            cust_email = f"customer.{i}@example.com"
            ext_cust_id = f"CUST-{random.randint(100000, 999999)}"

            # Pick matching text templates
            random_id = random.randint(10000, 99999)
            if ticket_type == TicketType.TECH:
                title = random.choice(TECH_SUBJECTS).format(random_id)
                desc = random.choice(TECH_DESCRIPTIONS).format(random_id)
            else:
                title = random.choice(SUPPORT_SUBJECTS).format(random_id)
                desc = random.choice(SUPPORT_DESCRIPTIONS).format(random_id)

            ticket_created_at = now - timedelta(days=random.randint(1, 29), hours=random.randint(1, 23))

            tickets_batch.append({
                "id": ticket_id,
                "ticket_type": ticket_type,
                "title": title,
                "description": desc,
                "customer_name": cust_name,
                "customer_email": cust_email,
                "external_customer_id": ext_cust_id,
                "status": status,
                "priority": priority,
                "ai_auto_created": random.choice([True, False]),
                "is_closed": True if status in [TicketStatus.CLOSED, TicketStatus.RESOLVED] else False,
                "is_active": True,
                "assignee_id": assignee_id,
                "assigned_at": ticket_created_at + timedelta(minutes=15),
                "sla_due_date": ticket_created_at + timedelta(hours=12),
                "created_at": ticket_created_at,
                "updated_at": now
            })

            # Create 2 messages for each ticket
            msg_1_id = uuid.uuid4()
            msg_2_id = uuid.uuid4()

            messages_batch.append({
                "id": msg_1_id,
                "ticket_id": ticket_id,
                "sender_type": SenderType.CUSTOMER,
                "sender_name": cust_name,
                "sender_email": cust_email,
                "message_text": random.choice(CUSTOMER_MESSAGES),
                "is_internal_note": False,
                "created_at": ticket_created_at + timedelta(minutes=5)
            })

            messages_batch.append({
                "id": msg_2_id,
                "ticket_id": ticket_id,
                "sender_type": SenderType.AGENT,
                "sender_name": "Support Agent",
                "sender_email": "agent@shopeasy.com",
                "message_text": random.choice(AGENT_MESSAGES),
                "is_internal_note": False,
                "created_at": ticket_created_at + timedelta(minutes=20)
            })

            # Bulk flush when batch limit is reached to save RAM
            if i % batch_size == 0:
                await session.execute(insert(Ticket), tickets_batch)
                await session.execute(insert(TicketMessage), messages_batch)
                await session.commit() # Save progress instantly
                
                tickets_batch.clear()
                messages_batch.clear()
                print(f"-> Progress: Inserted {i}/{total_tickets} tickets and {i*2} messages.")

        print("\n=== Database Seeding Complete! ===")
        print(f"Total Employees Added: 10,000")
        print(f"Total Tickets Added: 100,000")
        print(f"Total Messages Added: 200,000")

if __name__ == "__main__":
    asyncio.run(seed_massive_data())