import asyncio
import uuid
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from core.database import AsyncSessionLocal
from models.user import User, Role
from models.ticket import Ticket, TicketMessage, TicketStatus, TicketPriority, TicketType, SenderType

COMPLEX_TICKETS_DATA = [
    # --- TECH TICKETS (8 Tickets) ---
    {
        "ticket_type": TicketType.TECH,
        "title": "Infinite Promo Code Stack Loop on Checkout",
        "priority": TicketPriority.URGENT,
        "status": TicketStatus.IN_PROGRESS,
        "customer_name": "Fahad Al-Qahtani",
        "customer_email": "fahad.q@example.com",
        "desc": "System allowed stacking multiple promo codes recursively, leading to a negative order total.",
        "assigned_to": "omar.t@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Fahad Al-Qahtani", "email": "fahad.q@example.com", "text": "أهلاً، جيت اشتري جافا كودر كارد وضفت كودين خصم ورا بعض، السيستم خصم مرتين وطلع المجموع بالسالب (-150 ريال) والطلب معلق مو راضي يكتمل الآن! تكفون حلوا المشكلة."},
            {"sender": SenderType.AGENT, "name": "Omar El-Masry", "email": "omar.t@shopeasy.com", "text": "Hi Fahad, this is Omar from the Tech Team. We've detected a validation bug in our discount application microservice that fails to check recursive rules. I am blocking further checkout attempts on your cart temporarily to patch this loop."}
        ]
    },
    {
        "ticket_type": TicketType.TECH,
        "title": "Double Tokenization Failure on Checkout (Apple Pay)",
        "priority": TicketPriority.HIGH,
        "status": TicketStatus.OPEN,
        "customer_name": "Layan Al-Harbi",
        "customer_email": "layan.h@example.com",
        "desc": "Payment gateway processed dual tokens for a single checkout session, bank debited twice.",
        "assigned_to": "sherif.a@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Layan Al-Harbi", "email": "layan.h@example.com", "text": "I tried paying with Apple Pay. The first attempt said 'Failed' but my bank deducted 1200 SAR. I tried again, it succeeded, and now I have been charged twice! Bank reference: TXN-998871."},
            {"sender": SenderType.AGENT, "name": "Sherif Anwar", "email": "sherif.a@shopeasy.com", "text": "Hello Layan, we received your logs. It seems the gateway generated double session tokens. We have initiated a callback request to the bank to release the first blocked charge. Please allow 3-5 business days."}
        ]
    },
    {
        "ticket_type": TicketType.TECH,
        "title": "Redis Session Timeout Cart Desync during Flash Sale",
        "priority": TicketPriority.HIGH,
        "status": TicketStatus.RESOLVED,
        "customer_name": "Bandar Al-Otaibi",
        "customer_email": "bandar.o@example.com",
        "desc": "User session expired during high concurrency, cart item reserved but not shown in order database.",
        "assigned_to": "nour.d@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Bandar Al-Otaibi", "email": "bandar.o@example.com", "text": "كنت أحاول أشتري البلايستيشن وقت العرض، خصموا من الفيزا والمنتج طار من السلة لكن ما نزل لي أي طلب في صفحتي الشخصية! وش السالفة؟"},
            {"sender": SenderType.AGENT, "name": "Nour El-Din", "email": "nour.d@shopeasy.com", "text": "Hi Bandar, due to extreme traffic, your Redis session expired right as the webhook returned. I've manually reconciled the transaction and forced order #88902 into our SQL database. You should see it in your panel now."},
            {"sender": SenderType.CUSTOMER, "name": "Bandar Al-Otaibi", "email": "bandar.o@example.com", "text": "تمام الله يعطيكم العافية الحين ظهر عندي بالسيستم."}
        ]
    },
    {
        "ticket_type": TicketType.TECH,
        "title": "MFA Lockout after SIM Swapping",
        "priority": TicketPriority.MEDIUM,
        "status": TicketStatus.IN_PROGRESS,
        "customer_name": "Youssef Al-Dosari",
        "customer_email": "youssef.d@example.com",
        "desc": "Customer lost access to their phone number and cannot bypass MFA, recovery email is also unverified.",
        "assigned_to": "youssef.k@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Youssef Al-Dosari", "email": "youssef.d@example.com", "text": "I changed my SIM card and lost my old number. Now I can't log in because the OTP goes to the old SIM. Please disable MFA on my account."},
            {"sender": SenderType.AGENT, "name": "Youssef Kamel", "email": "youssef.k@shopeasy.com", "text": "Hi Youssef, since your recovery email is unverified, we cannot disable MFA immediately due to security policies. Please provide a government-issued ID matching your account billing name so we can proceed manually."}
        ]
    },
    {
        "ticket_type": TicketType.TECH,
        "title": "GraphQL Query Complexity Limit on Giant Cart",
        "priority": TicketPriority.LOW,
        "status": TicketStatus.CLOSED,
        "customer_name": "Hana Al-Saddoun",
        "customer_email": "hana.s@example.com",
        "desc": "Users with over 200 saved items in the cart trigger a GraphQL query complexity block (Error 400).",
        "assigned_to": "mai.m@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Hana Al-Saddoun", "email": "hana.s@example.com", "text": "Every time I open my shopping cart page, the app gives me an error 'Bad Request 400'. I can't checkout or view my cart at all!"},
            {"sender": SenderType.AGENT, "name": "Mai Mansour", "email": "mai.m@shopeasy.com", "text": "Hi Hana, we investigated your account. You have 240 items in your active cart, which exceeded our default GraphQL query nesting and complexity threshold. I've temporarily whitelisted your account and optimized our query schema."},
            {"sender": SenderType.CUSTOMER, "name": "Hana Al-Saddoun", "email": "hana.s@example.com", "text": "Perfect! It works now. Thank you so much."}
        ]
    },
    {
        "ticket_type": TicketType.TECH,
        "title": "Region CDN Cloudflare DDoS False Positive Block",
        "priority": TicketPriority.HIGH,
        "status": TicketStatus.IN_PROGRESS,
        "customer_name": "Tareq Al-Jamil",
        "customer_email": "tareq.j@example.com",
        "desc": "CDN flagged corporate VPN IPs as a DDoS threat, blocking checkout endpoint.",
        "assigned_to": "omar.t@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Tareq Al-Jamil", "email": "tareq.j@example.com", "text": "كل ما أضغط 'تأكيد الدفع' تظهر لي صفحة حجب من كلوود فلير! جربت من كذا جهاز ونفس المشكلة بالرغم من إن بطاقتي سليمة."},
            {"sender": SenderType.AGENT, "name": "Omar El-Masry", "email": "omar.t@shopeasy.com", "text": "Hello Tareq, it seems the VPN you are using belongs to a shared corporate IP range that was flagged globally. I am talking to our network engineers to adjust Cloudflare's WAF sensitivity on our checkout paths."}
        ]
    },
    {
        "ticket_type": TicketType.TECH,
        "title": "Tamara Callback Database Lock Condition",
        "priority": TicketPriority.URGENT,
        "status": TicketStatus.OPEN,
        "customer_name": "Sarah Al-Ghamdi",
        "customer_email": "sarah.g@example.com",
        "desc": "Tamara sent simultaneous approval webhooks, locking the row and generating duplicate payments.",
        "assigned_to": "sherif.a@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Sarah Al-Ghamdi", "email": "sarah.g@example.com", "text": "تمت الموافقة على طلبي من تمارا وخصموا الدفعة الأولى، لكن فجأة دخلت على المتجر ولقيت مكتوب 'الدفع فشل' والطلب تكنسل بالرغم من الخصم!"},
            {"sender": SenderType.AGENT, "name": "Sherif Anwar", "email": "sherif.a@shopeasy.com", "text": "Hi Sarah, we apologize for the confusion. Our system suffered a race condition during Tamara's callback, locking the SQL row temporarily. I'm reviewing the payload logs and will override the status manually to 'Paid'."}
        ]
    },
    {
        "ticket_type": TicketType.TECH,
        "title": "Fulfillment Partner Webhook Shipping Sync Failure",
        "priority": TicketPriority.MEDIUM,
        "status": TicketStatus.RESOLVED,
        "customer_name": "Sultan Al-Shammari",
        "customer_email": "sultan.sh@example.com",
        "desc": "API mismatch with third-party logistics tracking, causing infinite loop on tracking status requests.",
        "assigned_to": "nour.d@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Sultan Al-Shammari", "email": "sultan.sh@example.com", "text": "I want to track my order. The tracking link just keeps loading forever and the AI assistant tells me it's having trouble connecting to the catalog."},
            {"sender": SenderType.AGENT, "name": "Nour El-Din", "email": "nour.d@shopeasy.com", "text": "Hi Sultan, our logistics partner recently modified their JSON payload structure, which broke our webhook parser. I've manually updated your tracking details and deployed a hotfix for the API parser."},
            {"sender": SenderType.CUSTOMER, "name": "Sultan Al-Shammari", "email": "sultan.sh@example.com", "text": "Got it, I can see the tracking steps now. Thank you."}
        ]
    },

    # --- SUPPORT TICKETS (7 Tickets) ---
    {
        "ticket_type": TicketType.SUPPORT,
        "title": "Stolen Credit Card Dispute & Account Freeze",
        "priority": TicketPriority.URGENT,
        "status": TicketStatus.IN_PROGRESS,
        "customer_name": "Saad Al-Dossari",
        "customer_email": "saad.d@example.com",
        "desc": "Legal dispute: Bank issued a chargeback claim stating the card used was stolen.",
        "assigned_to": "mona.s@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Saad Al-Dossari", "email": "saad.d@example.com", "text": "حسابي تقفل فجأة وبدون أي سابق إنذار! وعندي رصيد محفظة بقيمة 800 ريال ماني قادر أستخدمه، وش سبب الحجب؟"},
            {"sender": SenderType.AGENT, "name": "Mona El-Shenawy", "email": "mona.s@shopeasy.com", "text": "Dear Saad, our legal department has locked this account due to an official bank dispute regarding transaction #TXN-70498. The card issuer reported it stolen. We must hold all funds until the official investigation is settled."}
        ]
    },
    {
        "ticket_type": TicketType.SUPPORT,
        "title": "Empty Sealed iPhone Box Discrepancy",
        "priority": TicketPriority.URGENT,
        "status": TicketStatus.OPEN,
        "customer_name": "Jawahir Al-Sudairi",
        "customer_email": "jawahir.s@example.com",
        "desc": "High priority: Customer claims they received a sealed box with no phone inside.",
        "assigned_to": "hassan.s@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Jawahir Al-Sudairi", "email": "jawahir.s@example.com", "text": "استلمت كرتون الآيفون مغلف حرارياً ومقفول بالكامل، فتحته ولقيت العلبة فاضية بدون الجهاز والشاحن! كيف كذا؟ أطالب بتعويض فوري!"},
            {"sender": SenderType.AGENT, "name": "Hassan El-Sawy", "email": "hassan.s@shopeasy.com", "text": "Hello Jawahir, we take these reports extremely seriously. I am currently requesting the dispatch weight logs from our warehouse and cross-referencing with SMSA's transit weight to pinpoint where the discrepancy occurred."}
        ]
    },
    {
        "ticket_type": TicketType.SUPPORT,
        "title": "Fragile Item Carrier Liability Dispute",
        "priority": TicketPriority.HIGH,
        "status": TicketStatus.IN_PROGRESS,
        "customer_name": "Sultan Al-Otaibi",
        "customer_email": "sultan.o@example.com",
        "desc": "Shipment arrived shattered; carrier blames packaging, warehouse blames carrier.",
        "assigned_to": "amira.k@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Sultan Al-Otaibi", "email": "sultan.o@example.com", "text": "النجف الكريستال وصلني مكسر ومفتت بالكامل داخل الصندوق! ومبين الكرتون معفوس من شاحنة التوصيل. أرجو حل الموضوع بأسرع وقت."},
            {"sender": SenderType.AGENT, "name": "Amira Khalil", "email": "amira.k@shopeasy.com", "text": "Hi Sultan, I am opening an official claim with Aramex because the box had our fragile tape on it. We are preparing a replacement unit to ship to you immediately while we handle the liability dispute with them."}
        ]
    },
    {
        "ticket_type": TicketType.SUPPORT,
        "title": "Cross-Border Customs Bundle Clearance Issue",
        "priority": TicketPriority.MEDIUM,
        "status": TicketStatus.IN_PROGRESS,
        "customer_name": "Rakan Al-Zafiri",
        "customer_email": "rakan.z@example.com",
        "desc": "Customs withheld a multi-vendor bundle because one item lacks regional compliance certificate.",
        "assigned_to": "tarek.n@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Rakan Al-Zafiri", "email": "rakan.z@example.com", "text": "My package has been stuck at Riyadh Customs for 8 days. They contacted me and said they need a compliance certificate for the wireless charger in my order."},
            {"sender": SenderType.AGENT, "name": "Tarek Nour", "email": "tarek.n@shopeasy.com", "text": "Hello Rakan, yes, the wireless charger in your bundle is from a vendor located in China and is missing the SASO certificate. We are going to split your shipment, release the rest of your items, and refund you for the charger."}
        ]
    },
    {
        "ticket_type": TicketType.SUPPORT,
        "title": "Deceased Account Holder Store Credit Retrieval",
        "priority": TicketPriority.LOW,
        "status": TicketStatus.RESOLVED,
        "customer_name": "Alia Al-Fayez",
        "customer_email": "alia.f@example.com",
        "desc": "Family requested transfer of deceased member's credits and order history to another account.",
        "assigned_to": "zainab.g@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Alia Al-Fayez", "email": "alia.f@example.com", "text": "والدي توفي الله يرحمه وعنده رصيد محفظة في متجركم وطلبات لم تستلم، كيف نقدر ننقل الرصيد والطلبات لحسابي الشخصي؟"},
            {"sender": SenderType.AGENT, "name": "Zainab Gad", "email": "zainab.g@shopeasy.com", "text": "Dear Alia, we offer our deepest condolences. To assist you with this sensitive request, please provide a copy of the death certificate and proof of family relations. Once received, our administrative team will manually migrate all credits to your account."},
            {"sender": SenderType.CUSTOMER, "name": "Alia Al-Fayez", "email": "alia.f@example.com", "text": "أرسلت المستندات المطلوبة على بريدكم الآن."}
        ]
    },
    {
        "ticket_type": TicketType.SUPPORT,
        "title": "Tamara Approval with Failed Internal Wallet Deduction",
        "priority": TicketPriority.HIGH,
        "status": TicketStatus.CLOSED,
        "customer_name": "Saleh Al-Rashid",
        "customer_email": "saleh.r@example.com",
        "desc": "Mixed payment system failure: store credit was not deducted, but Tamara processed the remainder.",
        "assigned_to": "mona.s@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Saleh Al-Rashid", "email": "saleh.r@example.com", "text": "I used 100 SAR of my store credit and paid the remaining 200 SAR with Tamara. The order is showing 'failed' but Tamara already authorized the installment plan!"},
            {"sender": SenderType.AGENT, "name": "Mona El-Shenawy", "email": "mona.s@shopeasy.com", "text": "Hi Saleh, our ledger showed a timeout when communicating with the wallet service, causing a rollback. I have manually deducted the 100 SAR store credit and approved your order #30491 to match your Tamara authorization."},
            {"sender": SenderType.CUSTOMER, "name": "Saleh Al-Rashid", "email": "saleh.r@example.com", "text": "Thank you, Mona. Order status has changed to preparing."}
        ]
    },
    {
        "ticket_type": TicketType.SUPPORT,
        "title": "Gift Card Purchased via Disputed Compromised Account",
        "priority": TicketPriority.HIGH,
        "status": TicketStatus.IN_PROGRESS,
        "customer_name": "Ghada Al-Saud",
        "customer_email": "ghada.a@example.com",
        "desc": "Chargeback request on a gift card that was already redeemed by a third party.",
        "assigned_to": "hassan.s@shopeasy.com",
        "messages": [
            {"sender": SenderType.CUSTOMER, "name": "Ghada Al-Saud", "email": "ghada.a@example.com", "text": "حسابي تعرض للاختراق وتم شراء بطاقة إهداء بقيمة 1000 ريال وإرسالها لحساب غريب وتم استخدامها! البنك طلب مني رفع تذكرة معكم لإيقاف الرصيد."},
            {"sender": SenderType.AGENT, "name": "Hassan El-Sawy", "email": "hassan.s@shopeasy.com", "text": "Hello Ghada, we have located the gift card. Unfortunately, it has already been redeemed and spent on a shipped order. We are locking the recipient's account immediately and collaborating with the payment gateway to handle the fraud investigation."}
        ]
    }
]

async def seed_complex_tickets():
    async with AsyncSessionLocal() as session:
        print("Fetching seeded employees from database...")
        
        # Get all users with roles loaded
        result = await session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.is_active == True)
        )
        users = result.scalars().all()
        
        # Map users by their email for easy lookup
        users_map = {u.email: u for u in users}
        
        if not users_map:
            print("ERROR: No employees found! Please run 'seed_employees.py' first.")
            return

        print(f"Found {len(users_map)} employees in database. Starting ticket seeding...")
        
        now = datetime.now(timezone.utc)
        tickets_seeded = 0

        for t_data in COMPLEX_TICKETS_DATA:
            # Generate random SLA based on priority
            sla_hours = 4 if t_data["priority"] == TicketPriority.URGENT else (12 if t_data["priority"] == TicketPriority.HIGH else 24)
            
            # Retrieve the correct assignee user object
            assignee = users_map.get(t_data["assigned_to"])
            if not assignee:
                print(f"Skipping ticket '{t_data['title']}' because employee {t_data['assigned_to']} was not found.")
                continue

            # Check if ticket already exists (to avoid duplicate seed runs)
            t_check = await session.execute(
                select(Ticket).where(Ticket.title == t_data["title"])
            )
            if t_check.scalar_one_or_none():
                print(f"Ticket '{t_data['title']}' already exists. Skipping.")
                continue

            # Create ticket object
            ticket = Ticket(
                id=uuid.uuid4(),
                ticket_type=t_data["ticket_type"],
                title=t_data["title"],
                description=t_data["desc"],
                customer_name=t_data["customer_name"],
                customer_email=t_data["customer_email"],
                external_customer_id=f"CUST-{random.randint(1000, 9999)}",
                status=t_data["status"],
                priority=t_data["priority"],
                assignee_id=assignee.id,
                assigned_at=now - timedelta(hours=2),
                sla_due_date=now + timedelta(hours=sla_hours),
                is_closed=True if t_data["status"] in [TicketStatus.CLOSED, TicketStatus.RESOLVED] else False,
                is_active=True,
                created_at=now - timedelta(hours=3),
                updated_at=now
            )
            session.add(ticket)
            await session.flush()

            # Seed conversation messages for this ticket
            message_time = now - timedelta(hours=2.5)
            for m_data in t_data["messages"]:
                msg = TicketMessage(
                    id=uuid.uuid4(),
                    ticket_id=ticket.id,
                    sender_type=m_data["sender"],
                    sender_name=m_data["name"],
                    sender_email=m_data["email"],
                    message_text=m_data["text"],
                    is_internal_note=False,
                    created_at=message_time
                )
                session.add(msg)
                message_time += timedelta(minutes=30) # Space messages by 30 mins

            tickets_seeded += 1
            print(f"Seeded Ticket: '{ticket.title}' assigned to {assignee.full_name}")

        await session.commit()
        print(f"\n=== Seeding completed! {tickets_seeded} complex tickets & dialogues successfully seeded. ===")

if __name__ == "__main__":
    asyncio.run(seed_complex_tickets())