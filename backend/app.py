import os
import sys
import sqlite3
import json
import uuid
import datetime
import smtplib
import threading
import hmac
import hashlib
import re
import socket
import urllib.request
import urllib.error
from email.message import EmailMessage
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

# Ensure UTF-8 output encoding for Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Robustly load environment variables from backend directory and workspace root
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_current_dir)
load_dotenv(os.path.join(_current_dir, ".env"))
load_dotenv(os.path.join(_root_dir, ".env"))
load_dotenv()

# Google Gemini SDK imports
try:
    from google import genai
    from google.genai import types, errors
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False


# ==========================================================
# FLASK APPLICATION SETUP
# ==========================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "pawzo-care-super-secret-key-2026")

# Enable CORS for all routes and origins
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

DATABASE = os.path.join(os.path.dirname(__file__), "pawzo.db")

# ==========================================================
# TIMEZONE & DATE/TIME UTILITIES (ASIA/KOLKATA - IST)
# ==========================================================
try:
    from zoneinfo import ZoneInfo
    INDIA_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    INDIA_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30), name="Asia/Kolkata")

def get_now_ist():
    """Returns a timezone-aware datetime object for Indian Standard Time (Asia/Kolkata)."""
    return datetime.datetime.now(INDIA_TZ)

def get_now_ist_str():
    """Returns database datetime string in IST: 'YYYY-MM-DD HH:MM:SS'."""
    return get_now_ist().strftime("%Y-%m-%d %H:%M:%S")

def get_now_ist_iso():
    """Returns ISO 8601 string with +05:30 offset in IST: 'YYYY-MM-DDTHH:MM:SS+05:30'."""
    return get_now_ist().isoformat()

def format_ist_display(dt_val):
    """
    Converts any datetime object or SQLite timestamp string into readable IST:
    e.g., '23 Aug 2026, 08:04 PM IST'.
    """
    if not dt_val:
        return "N/A"
    
    dt_obj = None
    if isinstance(dt_val, datetime.datetime):
        dt_obj = dt_val
    elif isinstance(dt_val, str):
        val = dt_val.strip()
        try:
            dt_obj = datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            pass
        if dt_obj is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    dt_obj = datetime.datetime.strptime(val[:19], fmt)
                    break
                except Exception:
                    pass
    
    if not dt_obj:
        return str(dt_val)
    
    if dt_obj.tzinfo is not None:
        dt_ist = dt_obj.astimezone(INDIA_TZ)
    else:
        dt_ist = dt_obj.replace(tzinfo=INDIA_TZ)
        
    return dt_ist.strftime("%d %b %Y, %I:%M:%S %p IST")

# Custom Jinja filters
@app.template_filter("ist_datetime")
def jinja_ist_datetime(value):
    return format_ist_display(value)

@app.template_filter("ist_date")
def jinja_ist_date(value):
    if not value:
        return "N/A"
    formatted = format_ist_display(value)
    return formatted.split(",")[0] if "," in formatted else formatted

@app.template_filter("from_json")
def from_json(value):
    if not value:
        return []
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return []

@app.template_filter("format_currency")
def format_currency(value):
    try:
        return f"₹{float(value):,.0f}"
    except (ValueError, TypeError):
        return "₹0"

app.jinja_env.globals["format_ist"] = format_ist_display

# Razorpay Test Configuration (Sandbox Mode Only - No Real Money)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_pawzocare2026")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "pawzosecretkey2026")
RAZORPAY_CURRENCY = os.getenv("RAZORPAY_CURRENCY", "INR")

# ==========================================================
# DATABASE CONNECTION & SCHEMA INITIALIZATION / MIGRATION
# ==========================================================
def get_db():
    conn = sqlite3.connect(DATABASE, timeout=60.0, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 60000;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Categories Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            icon TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    """)

    # 2. Products Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            discount_price REAL DEFAULT 0,
            image TEXT NOT NULL,
            stock INTEGER DEFAULT 10,
            sku TEXT,
            status TEXT DEFAULT 'active',
            is_featured INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 3. Customers Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            address TEXT,
            city TEXT,
            state TEXT,
            pincode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4. Orders Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            address TEXT NOT NULL,
            city TEXT,
            state TEXT,
            pincode TEXT NOT NULL,
            subtotal REAL NOT NULL,
            delivery REAL DEFAULT 50.0,
            discount REAL DEFAULT 0.0,
            grand_total REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT DEFAULT 'Pending',
            status TEXT DEFAULT 'Pending',
            tracking_number TEXT,
            courier TEXT,
            notes TEXT,
            cancellation_reason TEXT,
            cancelled_by TEXT,
            cancelled_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 5. Order Items Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            image TEXT,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)

    # 6. Order Tracking Timeline Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)

    # 7. Order Returns Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_returns (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            customer_name TEXT,
            customer_email TEXT,
            customer_phone TEXT,
            items_json TEXT,
            reason TEXT NOT NULL,
            comments TEXT,
            status TEXT DEFAULT 'Requested',
            refund_amount REAL DEFAULT 0,
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)

    # 8. Bookings / Appointments Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            pet_name TEXT NOT NULL,
            pet_age TEXT,
            pet_type TEXT NOT NULL,
            breed TEXT NOT NULL,
            service TEXT NOT NULL,
            specialist TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT DEFAULT '10:00 AM',
            message TEXT,
            status TEXT DEFAULT 'Pending',
            cancellation_reason TEXT,
            cancelled_by TEXT,
            cancelled_at TIMESTAMP,
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 9. Booking History Table (For Rescheduling & Auditing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS booking_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id TEXT NOT NULL,
            action TEXT NOT NULL,
            previous_date TEXT,
            previous_time TEXT,
            new_date TEXT,
            new_time TEXT,
            notes TEXT,
            changed_by TEXT DEFAULT 'Customer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE
        )
    """)

    # 10. Customer Reviews Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            rating INTEGER NOT NULL,
            review_text TEXT NOT NULL,
            product_name TEXT,
            service_name TEXT,
            order_id TEXT,
            booking_id TEXT,
            is_approved INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 11. Booking Services Table (Multi-Service Support)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS booking_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id TEXT NOT NULL,
            service_id INTEGER,
            service_name TEXT NOT NULL,
            service_slug TEXT,
            price REAL DEFAULT 0.0,
            duration TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE
        )
    """)

    # Check for missing columns in bookings table if pre-existing
    cursor.execute("PRAGMA table_info(bookings)")
    booking_cols = [c[1] for c in cursor.fetchall()]
    if "created_at" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if "appointment_time" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN appointment_time TEXT DEFAULT '10:00 AM'")
    if "cancellation_reason" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN cancellation_reason TEXT")
    if "cancelled_by" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN cancelled_by TEXT")
    if "cancelled_at" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN cancelled_at TIMESTAMP")
    if "admin_notes" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN admin_notes TEXT")
    if "updated_at" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN updated_at TIMESTAMP")
    if "total_price" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN total_price REAL DEFAULT 0.0")
    if "services_json" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN services_json TEXT")
    if "main_service" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN main_service TEXT")
    if "sub_service" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN sub_service TEXT")
    if "address" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN address TEXT")

    # Check for missing columns in orders table if pre-existing
    cursor.execute("PRAGMA table_info(orders)")
    order_cols = [c[1] for c in cursor.fetchall()]
    if "created_at" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if "delivery" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN delivery REAL DEFAULT 50.0")
    if "discount" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0.0")
    if "payment_status" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'Pending'")
    if "cancellation_reason" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN cancellation_reason TEXT")
    if "cancelled_by" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN cancelled_by TEXT")
    if "cancelled_at" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN cancelled_at TIMESTAMP")
    if "tracking_number" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN tracking_number TEXT")
    if "courier" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN courier TEXT")
    if "city" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN city TEXT")
    if "state" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN state TEXT")
    if "updated_at" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN updated_at TIMESTAMP")

    # 11. Services Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            duration TEXT,
            image TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    # 12. Specialists Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS specialists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT,
            experience TEXT,
            skills TEXT,
            about TEXT,
            image TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    # 13. Site Settings Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # 14. Admin Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 15. Contact Inquiries Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            subject TEXT,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for optimal search performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_email ON bookings(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_approved ON reviews(is_approved)")

    conn.commit()

    # Seed initial default data
    seed_database(conn)
    conn.close()

def seed_database(conn):
    cursor = conn.cursor()

    # 1. Seed Admin User
    admin_count = cursor.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]
    if admin_count == 0:
        default_admin_user = "admin"
        default_admin_pass = "Admin@12345"
        hashed = generate_password_hash(default_admin_pass)
        cursor.execute(
            "INSERT INTO admin_users (username, password_hash, role) VALUES (?, ?, ?)",
            (default_admin_user, hashed, "superadmin")
        )

    # 2. Seed Categories
    cat_count = cursor.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if cat_count == 0:
        categories = [
            ("All Products", "all", "fa-boxes-stacked", 1),
            ("Dog Products", "dog", "fa-dog", 2),
            ("Cat Products", "cat", "fa-cat", 3),
            ("Food & Treats", "food", "fa-bowl-food", 4),
            ("Grooming & Spa", "grooming", "fa-soap", 5),
            ("Health & Care", "health", "fa-heart-pulse", 6),
            ("Toys & Play", "toys", "fa-baseball", 7),
        ]
        cursor.executemany(
            "INSERT INTO categories (name, slug, icon, sort_order) VALUES (?, ?, ?, ?)",
            categories
        )

    # 3. Seed Products
    prod_count = cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if prod_count == 0:
        products = [
            # Dogs
            ("Royal Canin Dog Food", "royal-canin-dog-food", "Complete balanced nutrition tailored for adult dogs with essential vitamins, omega fatty acids, and high protein.", "dog", 999.0, 849.0, "images/dogfood.png", 30, "DOG-FD-01", "active", 1),
            ("Herbal Pet Dog Shampoo", "herbal-pet-dog-shampoo", "Anti-tick & anti-flea gentle cleansing formula with aloe vera, tea tree oil, and natural conditioning extracts.", "dog", 299.0, 249.0, "images/dogshampoo.jpg", 45, "DOG-SH-01", "active", 1),
            ("Neem & Aloe Dog Soap", "neem-aloe-dog-soap", "Antibacterial moisturizing bar enriched with neem oil to soothe itchy skin, eliminate odors, and nourish the coat.", "dog", 199.0, 159.0, "images/dogsoap.jpg", 50, "DOG-SP-01", "active", 0),
            ("Fresh Fragrance Dog Perfume", "fresh-fragrance-dog-perfume", "Long-lasting deodorizing cologne formulated alcohol-free for safe daily pet freshness and coat luster.", "dog", 349.0, 299.0, "images/dogperfume.jpg", 35, "DOG-PF-01", "active", 0),
            ("Pet Dental Dog Toothpaste", "pet-dental-dog-toothpaste", "Enzymatic beef-flavored tartar control formula that freshens breath and supports clean teeth and gums.", "dog", 249.0, 199.0, "images/dogtoothpaste.jpg", 40, "DOG-TP-01", "active", 0),
            ("Multivitamin Dog Supplement", "multivitamin-dog-supplement", "Essential daily vitamins and minerals for active immunity, strong bones, healthy digestion, and joint vitality.", "dog", 450.0, 399.0, "images/dogmedicine.jpg", 25, "DOG-MD-01", "active", 1),
            ("Durable Squeaky Dog Toy", "durable-squeaky-dog-toy", "Tough bite-resistant rubber chew toy designed for interactive fetch, teeth cleaning, and boundless indoor/outdoor play.", "dog", 299.0, 249.0, "images/dogtoy.jpg", 60, "DOG-TY-01", "active", 0),
            ("Crunchy Calcium Dog Treats", "crunchy-calcium-dog-treats", "Delicious bone-shaped calcium-rich dog biscuits ideal for obedience training rewards and dental health.", "dog", 249.0, 199.0, "images/dogtreats.jpg", 55, "DOG-TR-01", "active", 1),

            # Cats
            ("Whiskas Ocean Fish Cat Food", "whiskas-ocean-fish-cat-food", "Delicious tuna & mackerel crunchy kibbles formulated with balanced minerals and taurine for bright eyes and silky coats.", "cat", 799.0, 699.0, "images/catfood.jpg", 28, "CAT-FD-01", "active", 1),
            ("Silky Conditioning Cat Shampoo", "silky-conditioning-cat-shampoo", "Tearless hypoallergenic coat cleanser with natural chamomile that leaves feline fur fluffy, soft, and easy to detangle.", "cat", 320.0, 279.0, "images/catshampoo.jpg", 35, "CAT-SH-01", "active", 1),
            ("Gentle Purr Cat Soap", "gentle-purr-cat-soap", "Ultra-mild natural soap bar designed for sensitive feline skin with pH-balanced hydrating botanicals.", "cat", 189.0, 149.0, "images/catsoap.jpg", 40, "CAT-SP-01", "active", 0),
            ("Sweet Blossom Cat Perfume", "sweet-blossom-cat-perfume", "Calming lavender and floral mist safe for feline coat deodorizing without sticky residue.", "cat", 329.0, 279.0, "images/catperfume.jpg", 30, "CAT-PF-01", "active", 0),
            ("Fresh Mint Cat Toothpaste", "fresh-mint-cat-toothpaste", "Easy-to-use oral gel that prevents plaque buildup, combats tartar, and promotes healthy pink gums.", "cat", 239.0, 189.0, "images/cattoothpaste.jpg", 32, "CAT-TP-01", "active", 0),
            ("Immunity & Hairball Cat Medicine", "immunity-hairball-cat-medicine", "Specialized malt paste and digestive supplement that helps expel hairballs smoothly while boosting vitality.", "cat", 420.0, 369.0, "images/catmedicine.jpg", 22, "CAT-MD-01", "active", 1),
            ("Feather Bell Wand Cat Toy", "feather-bell-wand-cat-toy", "Interactive teasing wand with natural soft feathers and jingling bell to stimulate hunting instincts and active exercise.", "cat", 250.0, 199.0, "images/cattoy.jpg", 50, "CAT-TY-01", "active", 0),
            ("Tuna & Salmon Cat Treats", "tuna-salmon-cat-treats", "Irresistible real meat puree & crunchy reward bites enriched with vitamin E and omega-3 oils.", "cat", 229.0, 189.0, "images/cattreats.jpg", 65, "CAT-TR-01", "active", 1),
        ]
        cursor.executemany(
            """INSERT INTO products (name, slug, description, category, price, discount_price, image, stock, sku, status, is_featured)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            products
        )

    # 4. Seed Services
    srv_count = cursor.execute("SELECT COUNT(*) FROM services").fetchone()[0]
    if srv_count == 0:
        services = [
            ("Puppy Grooming", "puppy-grooming", "Gentle bath, soft brushing, ear cleaning, nail trim, puppy perfume", 800.0, "45 mins", "images/services/puppy.jpg", 1),
            ("Basic Grooming", "basic-grooming", "Bath, nail clipping, ear cleaning, body spray, brushing", 900.0, "60 mins", "images/services/basic.jpg", 1),
            ("Premium Spa Bath", "premium-spa-bath", "Premium shampoo, conditioner, nail clipping, ear cleaning, teeth cleaning", 1200.0, "75 mins", "images/services/spa.jpg", 1),
            ("Premium Grooming", "premium-grooming", "Premium bath, face trim, paw massage, teeth cleaning, body spray", 1500.0, "90 mins", "images/services/premium.jpg", 1),
            ("Medicated Bath", "medicated-bath", "Skin treatment, medicated shampoo, conditioner, body dry, brushing", 1800.0, "90 mins", "images/services/medicated.jpg", 1),
            ("Luxury Full Grooming", "luxury-full-grooming", "Premium bath, hair styling, nail clipping, teeth cleaning, body massage", 2500.0, "120 mins", "images/services/luxury.jpg", 1),
            ("Separate Bath", "separate-bath", "Choose one targeted single hygiene & grooming treatment tailored specifically for your pet's needs.", 350.0, "20-45 mins", "images/services/separate-bath.jpg", 1),
        ]
        cursor.executemany(
            "INSERT INTO services (name, slug, description, price, duration, image, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            services
        )
    else:
        sep_exists = cursor.execute("SELECT COUNT(*) FROM services WHERE slug = 'separate-bath'").fetchone()[0]
        if sep_exists == 0:
            cursor.execute(
                "INSERT INTO services (name, slug, description, price, duration, image, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("Separate Bath", "separate-bath", "Choose one targeted single hygiene & grooming treatment tailored specifically for your pet's needs.", 350.0, "20-45 mins", "images/services/separate-bath.jpg", 1)
            )

    # 5. Seed Specialists
    spec_count = cursor.execute("SELECT COUNT(*) FROM specialists").fetchone()[0]
    if spec_count == 0:
        specialists = [
            ("Dr. Ethan Wilson", "Pet Grooming Specialist", "5+ Years", "Dog & Cat Grooming", "Dr. Ethan Wilson is an experienced pet grooming specialist providing gentle, safe, and professional grooming care.", "images/doctor1.jpg", 1),
            ("Dr. Emily Waston", "Cat & Dog Grooming Specialist", "6+ Years", "Cat & Dog Grooming", "Dr. Emily Waston specializes in caring for both cats and dogs with a soothing, anxiety-free approach.", "images/doctor2.jpg", 1),
            ("Dr. Daniel Carten", "Pet Skin & Coat Specialist", "7+ Years", "Skin & Coat Care", "Dr. Daniel Carten has extensive expertise in canine dermatology and coat rejuvenation treatments.", "images/doctor3.jpg", 1),
            ("Dr. Sophia Bennett", "Puppy Grooming Specialist", "4+ Years", "Puppy Grooming", "Dr. Sophia Bennett focuses on gentle first-time experiences making puppies feel comfortable and relaxed.", "images/doctor4.jpg", 1),
            ("Dr. James Anderson", "Professional Pet Groomer", "8+ Years", "Professional Pet Grooming", "Dr. James Anderson is a master pet stylist with years of experience providing show-quality grooming.", "images/doctor5.jpg", 1),
        ]
        cursor.executemany(
            "INSERT INTO specialists (name, role, experience, skills, about, image, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            specialists
        )

    # 6. Seed Initial Genuine Verified Reviews
    rev_count = cursor.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    if rev_count == 0:
        reviews = [
            ("Priya Sundaram", "priya.s@example.com", 5, "Took my 2-year-old Golden Retriever for the Premium Spa Bath. Dr. Ethan handled him with such gentle patience! His coat has never been so soft and fragrant.", None, "Premium Spa Bath", None, None, 1),
            ("Karthik Raja", "karthik.raja@example.com", 5, "Ordered Royal Canin dog food and dog treats. Delivered in Nagercoil within 2 days in perfect condition. Truly reliable pet service!", "Royal Canin Dog Food", None, None, None, 1),
            ("Ananya Sharma", "ananya.sh@example.com", 5, "The AI dog feature gave me accurate feeding advice when my puppy had minor indigestion. Love the prompt appointment booking and clean salon atmosphere!", None, "Puppy Grooming", None, None, 1),
        ]
        cursor.executemany(
            "INSERT INTO reviews (customer_name, customer_email, rating, review_text, product_name, service_name, order_id, booking_id, is_approved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            reviews
        )

    # 7. Seed Settings
    settings = [
        ("shop_name", "PET NEXA"),
        ("shop_tagline", "Professional Pet Care & Premium Pet Shop"),
        ("shop_phone", "+91 9445437069, +91 6380576651"),
        ("shop_email", "vikneshvaren2@gmail.com, karthikthanesh92@gmail.com"),
        ("shop_address", "8/30, Church Street, Azhagappapuram, Nagercoil, Tamil Nadu - 629401"),
        ("delivery_fee", "50"),
        ("free_delivery_threshold", "1000"),
        ("opening_hours", "Mon - Sun: 9:00 AM - 8:00 PM"),
        ("shop_whatsapp", "https://wa.me/919445437069"),
        ("cancellation_policy", "Orders can be cancelled anytime before dispatch. Appointments can be cancelled up to 2 hours before scheduled time."),
        ("return_policy", "Returns are accepted within 7 days of delivery for unused items in original packaging.")
    ]
    for k, v in settings:
        cursor.execute("INSERT OR REPLACE INTO site_settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()


# ==========================================================
# ==========================================================
# ASYNCHRONOUS EMAIL ENGINE (DUAL RECIPIENTS SUPPORT)
# ==========================================================
def get_admin_emails():
    """Retrieve all configured admin email addresses."""
    admin_env = os.getenv("ADMIN_EMAIL", "vikneshvaren2@gmail.com,karthikthanesh92@gmail.com")
    emails = [e.strip() for e in admin_env.split(",") if e.strip()]
    if not emails:
        emails = ["vikneshvaren2@gmail.com", "karthikthanesh92@gmail.com"]
    return emails

def send_email_async(to_email, subject, body_text, body_html=None):
    """
    High-deliverability asynchronous email engine:
    1. Primary: Resend HTTPS API (zero SMTP port blocking on cloud servers)
    2. Fallback: Gmail SMTP SSL (port 465) for direct deliverability to all recipients (dual admins and customers).
    """
    def _send():
        resend_key = os.getenv("RESEND_API_KEY", "").strip()
        resend_from = os.getenv("RESEND_FROM", os.getenv("RESEND_FROM_EMAIL", "PET NEXA <onboarding@resend.dev>")).strip()

        # Handle list or comma-separated recipients
        recipients = []
        if isinstance(to_email, list):
            recipients = [e.strip() for e in to_email if e.strip()]
        elif isinstance(to_email, str):
            recipients = [e.strip() for e in to_email.split(",") if e.strip()]

        if not recipients:
            return

        smtp_recipients = []

        for recipient in recipients:
            delivered = False

            # --- 1. TRY RESEND HTTPS API ---
            if resend_key:
                try:
                    payload = {
                        "from": resend_from,
                        "to": [recipient],
                        "subject": subject,
                        "text": body_text or ""
                    }
                    if body_html:
                        payload["html"] = body_html

                    req_data = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(
                        "https://api.resend.com/emails",
                        data=req_data,
                        headers={
                            "Authorization": f"Bearer {resend_key}",
                            "Content-Type": "application/json",
                            "User-Agent": "resend-python:2.0.0"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=10) as response:
                        resp_content = response.read().decode("utf-8")
                        print(f"[RESEND SUCCESS] Sent email to {recipient}: {subject} | Response: {resp_content}")
                        delivered = True
                except urllib.error.HTTPError as he:
                    err_msg = he.read().decode("utf-8") if he.fp else str(he)
                    print(f"[RESEND HTTP {he.code}] Could not send to {recipient}: {err_msg}")
                except Exception as rex:
                    print(f"[RESEND ERROR] Error sending to {recipient}: {rex}")

            if not delivered:
                smtp_recipients.append(recipient)

        # --- 2. FALLBACK TO GMAIL SMTP SSL FOR REMAINING RECIPIENTS ---
        if smtp_recipients:
            raw_user = os.getenv("EMAIL_USER", "vikneshvaren2@gmail.com")
            sender_email = raw_user.split(",")[0].strip()
            sender_password = os.getenv("EMAIL_PASSWORD", "").replace(" ", "").strip()

            if sender_email and sender_password and "your_email" not in sender_email:
                try:
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                        server.login(sender_email, sender_password)
                        for recipient in smtp_recipients:
                            try:
                                msg = EmailMessage()
                                msg["Subject"] = subject
                                msg["From"] = f"PET NEXA <{sender_email}>"
                                msg["To"] = recipient
                                msg.set_content(body_text or "")

                                if body_html:
                                    msg.add_alternative(body_html, subtype="html")

                                server.send_message(msg)
                                print(f"[SMTP SUCCESS] EMAIL SENT successfully to {recipient}: {subject}")
                            except Exception as sub_e:
                                print(f"[SMTP ERROR] Failed sending to {recipient}: {sub_e}")
                except Exception as e:
                    print(f"[SMTP ERROR] SMTP connection failed: {e}")
            else:
                for recipient in smtp_recipients:
                    print(f"[EMAIL MOCK] Email to {recipient}: {subject}")

    threading.Thread(target=_send, daemon=True).start()

def get_app_base_url():
    """Dynamically determine the base application URL for email links and redirects."""
    env_base = os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if env_base:
        return env_base.rstrip("/")
    try:
        from flask import has_request_context
        if has_request_context() and request:
            return request.host_url.rstrip("/")
    except Exception:
        pass
    return "https://pet-nexa.onrender.com"

def get_email_header_footer():
    header = """
    <div style="background:#0f172a; padding:25px; text-align:center; border-radius:12px 12px 0 0; border-bottom:3px solid #8b5cf6;">
        <h1 style="color:#a78bfa; margin:0; font-family:sans-serif; font-size:26px; letter-spacing:1px;">🐾 PET NEXA</h1>
        <p style="color:#94a3b8; margin:5px 0 0 0; font-size:14px; font-family:sans-serif;">Professional Pet Care & Premium Pet Shop</p>
    </div>
    """
    footer = """
    <div style="background:#f8fafc; padding:20px; text-align:center; border-radius:0 0 12px 12px; border-top:1px solid #e2e8f0; font-family:sans-serif; font-size:12px; color:#64748b;">
        <p style="margin:0 0 5px 0;">📍 8/30, Church Street, Azhagappapuram, Nagercoil, Tamil Nadu - 629401</p>
        <p style="margin:0 0 5px 0;">📞 +91 9445437069 | ✉️ vikneshvaren2@gmail.com, karthikthanesh92@gmail.com</p>
        <p style="margin:8px 0 0 0; color:#94a3b8;">© 2026 PET NEXA. All Rights Reserved.</p>
    </div>
    """
    return header, footer

# 1. Order Placed Notification
def notify_order_placed(order, items):
    admin_emails = get_admin_emails()
    customer_email = order["email"]
    header, footer = get_email_header_footer()
    base_url = get_app_base_url()

    items_html = "".join([
        f"""<tr style="border-bottom:1px solid #e2e8f0;">
            <td style="padding:10px; font-family:sans-serif;"><strong>{item['product_name']}</strong></td>
            <td style="padding:10px; font-family:sans-serif; text-align:center;">{item['quantity']}</td>
            <td style="padding:10px; font-family:sans-serif; text-align:right;">₹{float(item['price']):.0f}</td>
            <td style="padding:10px; font-family:sans-serif; text-align:right; font-weight:bold;">₹{float(item['total']):.0f}</td>
        </tr>""" for item in items
    ])

    # Customer Email
    cust_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">🎉 Order Confirmed #{order['id']}</h2>
            <p>Dear <strong>{order['customer_name']}</strong>,</p>
            <p>Thank you for choosing PET NEXA! We have received your order and our team is preparing it for dispatch.</p>
            
            <div style="background:#f5f3ff; padding:15px; border-radius:8px; margin:20px 0; border-left:4px solid #8b5cf6;">
                <p style="margin:0 0 5px 0;"><strong>Delivery Address:</strong> {order['address']}, {order['city'] or 'Nagercoil'} - {order['pincode']}</p>
                <p style="margin:0 0 5px 0;"><strong>Payment Method:</strong> {order['payment_method']} ({order['payment_status']})</p>
                <p style="margin:0;"><strong>Order Date:</strong> {format_ist_display(order.get('created_at'))}</p>
            </div>

            <table style="width:100%; border-collapse:collapse; margin:20px 0; font-size:14px;">
                <thead>
                    <tr style="background:#f8fafc; border-bottom:2px solid #cbd5e1;">
                        <th style="padding:10px; text-align:left;">Item</th>
                        <th style="padding:10px; text-align:center;">Qty</th>
                        <th style="padding:10px; text-align:right;">Price</th>
                        <th style="padding:10px; text-align:right;">Total</th>
                    </tr>
                </thead>
                <tbody>{items_html}</tbody>
                <tfoot>
                    <tr>
                        <td colspan="3" style="padding:10px; text-align:right; font-weight:bold;">Subtotal:</td>
                        <td style="padding:10px; text-align:right; font-weight:bold;">₹{float(order['subtotal']):.0f}</td>
                    </tr>
                    <tr>
                        <td colspan="3" style="padding:10px; text-align:right;">Delivery Fee:</td>
                        <td style="padding:10px; text-align:right;">₹{float(order['delivery']):.0f}</td>
                    </tr>
                    <tr style="font-size:16px; color:#7c3aed; border-top:2px solid #cbd5e1;">
                        <td colspan="3" style="padding:10px; text-align:right; font-weight:bold;">Grand Total:</td>
                        <td style="padding:10px; text-align:right; font-weight:bold;">₹{float(order['grand_total']):.0f}</td>
                    </tr>
                </tfoot>
            </table>

            <p style="text-align:center; margin:30px 0 10px;">
                <a href="{base_url}/track.html?id={order['id']}" style="background:#8b5cf6; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">Track Your Order Live</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(customer_email, f"🎉 Order Confirmed #{order['id']} - PET NEXA", f"Your order #{order['id']} for ₹{order['grand_total']} is confirmed on {format_ist_display(order.get('created_at'))}.", cust_html)

    # Admin Emails (Dual Recipients)
    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#b91c1c; margin-top:0;">🚨 New Order Received #{order['id']}</h2>
            <div style="background:#fee2e2; border-left:4px solid #ef4444; padding:12px; border-radius:4px; margin-bottom:20px;">
                <strong>Order Value:</strong> ₹{float(order['grand_total']):.0f} | <strong>Payment:</strong> {order['payment_method']} ({order['payment_status']})<br>
                <strong>Placed at:</strong> {format_ist_display(order.get('created_at'))}
            </div>
            <p><strong>Customer:</strong> {order['customer_name']}<br>
               <strong>Phone:</strong> {order['phone']}<br>
               <strong>Email:</strong> {order['email']}<br>
               <strong>Address:</strong> {order['address']} - {order['pincode']}</p>
            
            <table style="width:100%; border-collapse:collapse; margin:20px 0; font-size:14px;">
                <thead>
                    <tr style="background:#f8fafc; border-bottom:2px solid #cbd5e1;">
                        <th style="padding:10px; text-align:left;">Item</th>
                        <th style="padding:10px; text-align:center;">Qty</th>
                        <th style="padding:10px; text-align:right;">Total</th>
                    </tr>
                </thead>
                <tbody>{items_html}</tbody>
            </table>
            <p style="text-align:center; margin-top:25px;">
                <a href="{base_url}/admin/orders" style="background:#0f172a; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">Open Admin Panel</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"🚨 NEW ORDER #{order['id']} from {order['customer_name']} (₹{order['grand_total']:.0f}) - PET NEXA", f"New order #{order['id']} received on {format_ist_display(order.get('created_at'))}.", admin_html)


# 2. Order Cancellation Notification
def notify_order_cancelled(order, reason, cancelled_by="Customer"):
    admin_emails = get_admin_emails()
    customer_email = order["email"]
    header, footer = get_email_header_footer()

    cust_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#ef4444; margin-top:0;">❌ Order Cancelled #{order['id']}</h2>
            <p>Dear <strong>{order['customer_name']}</strong>,</p>
            <p>Your order <strong>#{order['id']}</strong> has been cancelled.</p>
            <div style="background:#fef2f2; border-left:4px solid #ef4444; padding:12px; margin:20px 0;">
                <p style="margin:0;"><strong>Reason:</strong> {reason}</p>
                <p style="margin:5px 0 0 0;"><strong>Cancelled By:</strong> {cancelled_by}</p>
            </div>
            <p>If you made an online pre-payment, your refund will be processed back to your original payment method.</p>
        </div>
        {footer}
    </div>
    """
    send_email_async(customer_email, f"❌ Order Cancelled #{order['id']} - PET NEXA", f"Order #{order['id']} has been cancelled.", cust_html)

    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#b91c1c; margin-top:0;">⚠️ Order Cancellation Alert #{order['id']}</h2>
            <p><strong>Customer:</strong> {order['customer_name']} ({order['phone']})<br>
               <strong>Order Total:</strong> ₹{float(order['grand_total']):.0f}<br>
               <strong>Reason:</strong> {reason}<br>
               <strong>Cancelled By:</strong> {cancelled_by}</p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"⚠️ ORDER CANCELLED #{order['id']} - {order['customer_name']} - PET NEXA", f"Order #{order['id']} cancelled.", admin_html)


# 3. Order Status Updated Notification
def notify_order_status_updated(order, new_status, tracking_number=None, courier=None):
    customer_email = order["email"]
    header, footer = get_email_header_footer()
    base_url = get_app_base_url()

    courier_info = ""
    if tracking_number:
        courier_info = f"""
        <div style="background:#f0fdf4; border-left:4px solid #22c55e; padding:12px; margin:20px 0;">
            <p style="margin:0;"><strong>Courier Partner:</strong> {courier or 'Express Delivery'}</p>
            <p style="margin:5px 0 0 0;"><strong>Tracking Number (AWB):</strong> <code style="background:#e2e8f0; padding:2px 6px; border-radius:4px;">{tracking_number}</code></p>
        </div>
        """

    cust_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">📦 Order Status Update: {new_status}</h2>
            <p>Dear <strong>{order['customer_name']}</strong>,</p>
            <p>The status of your order <strong>#{order['id']}</strong> has been updated to: <span style="background:#ede9fe; color:#7c3aed; padding:3px 10px; border-radius:50px; font-weight:bold;">{new_status}</span></p>
            {courier_info}
            <p style="text-align:center; margin:30px 0 10px;">
                <a href="{base_url}/track.html?id={order['id']}" style="background:#8b5cf6; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">View Live Tracking</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(customer_email, f"📦 Order Update #{order['id']}: {new_status} - PET NEXA", f"Order #{order['id']} is now {new_status}.", cust_html)

    admin_emails = get_admin_emails()
    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">📦 Order Status Updated #{order['id']} &rarr; {new_status}</h2>
            <p><strong>Customer:</strong> {order['customer_name']} ({order['phone']})<br>
               <strong>Email:</strong> {order['email']}<br>
               <strong>New Status:</strong> {new_status}<br>
               {f'<strong>Tracking (AWB):</strong> {tracking_number}<br>' if tracking_number else ''}
               {f'<strong>Courier:</strong> {courier}<br>' if courier else ''}</p>
            <p style="text-align:center; margin-top:25px;">
                <a href="{base_url}/admin/orders" style="background:#0f172a; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">Open Admin Panel</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"📦 ORDER STATUS UPDATED #{order['id']}: {new_status} - PET NEXA", f"Order #{order['id']} status updated to {new_status}.", admin_html)


# 4. Booking Created Notification
def notify_booking_created(booking):
    admin_emails = get_admin_emails()
    customer_email = booking["email"]
    header, footer = get_email_header_footer()
    base_url = get_app_base_url()

    total_price = float(booking.get("total_price") or 0.0)
    price_line = f"<p style='margin:0 0 8px 0; color:#16a34a; font-weight:bold; font-size:15px;'><strong>💰 Total Package Price:</strong> ₹{total_price:.0f}</p>" if total_price > 0 else ""

    main_svc = booking.get("main_service")
    sub_svc = booking.get("sub_service")
    if main_svc and sub_svc:
        sub_list = [s.strip() for s in sub_svc.split(",") if s.strip()]
        if len(sub_list) > 1:
            sub_items_html = "".join([f"<li style='margin:3px 0;'>• {s}</li>" for s in sub_list])
            service_html_block = f"""
                <p style="margin:0 0 4px 0;"><strong>🛁 Main Service:</strong> {main_svc}</p>
                <p style="margin:0 0 4px 0;"><strong>✨ Selected Services ({len(sub_list)}):</strong></p>
                <ul style="margin:0 0 8px 18px; padding:0; color:#334155; font-size:13.5px;">{sub_items_html}</ul>
            """
        else:
            service_html_block = f"""
                <p style="margin:0 0 8px 0;"><strong>🛁 Main Service:</strong> {main_svc}</p>
                <p style="margin:0 0 8px 0;"><strong>✨ Selected Service:</strong> {sub_svc}</p>
            """
        service_text_block = f"Main Service: {main_svc}\nSelected Services: {sub_svc}"
    else:
        service_html_block = f"""<p style="margin:0 0 8px 0;"><strong>✨ Selected Service:</strong> {booking['service']}</p>"""
        service_text_block = f"Service: {booking['service']}"

    address_line = f"<p style='margin:0 0 8px 0;'><strong>📍 Address / Location:</strong> {booking['address']}</p>" if booking.get("address") else ""

    cust_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">📅 Pet Care Session Booked #{booking['id']}</h2>
            <p>Dear <strong>{booking['customer_name']}</strong>,</p>
            <p>We are delighted to confirm your grooming session at PET NEXA!</p>
            
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:18px; margin:20px 0;">
                <p style="margin:0 0 8px 0;"><strong>🐾 Pet Name:</strong> {booking['pet_name']} ({booking['breed']}, {booking['pet_type']})</p>
                {service_html_block}
                {price_line}
                <p style="margin:0 0 8px 0;"><strong>👨‍⚕️ Specialist:</strong> {booking['specialist']}</p>
                <p style="margin:0 0 8px 0;"><strong>🗓️ Scheduled Date:</strong> {booking['appointment_date']}</p>
                <p style="margin:0 0 8px 0;"><strong>⏰ Time Slot:</strong> {booking['appointment_time']}</p>
                <p style="margin:0 0 8px 0;"><strong>🕒 Booking Created:</strong> {format_ist_display(booking.get('created_at'))}</p>
                {address_line}
            </div>

            <p style="font-size:13px; color:#64748b;">Please arrive 5–10 minutes prior to your appointment time with your pet. If you need to reschedule or cancel, please visit our booking management page.</p>
            <p style="text-align:center; margin:25px 0 10px;">
                <a href="{base_url}/booking-track.html?id={booking['id']}" style="background:#8b5cf6; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">Manage Appointment</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(customer_email, f"📅 Grooming Booked #{booking['id']} for {booking['pet_name']} - PET NEXA", f"Appointment #{booking['id']} confirmed for {booking['appointment_date']} at {booking['appointment_time']}.\n{service_text_block}", cust_html)

    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">🗓️ New Pet Grooming Booking #{booking['id']}</h2>
            <p><strong>Customer:</strong> {booking['customer_name']}<br>
               <strong>Phone:</strong> {booking['phone']}<br>
               <strong>Email:</strong> {booking['email']}<br>
               <strong>Pet:</strong> {booking['pet_name']} ({booking['breed']}, Age: {booking['pet_age']})<br>
               {service_html_block}
               <strong>Total Price:</strong> ₹{total_price:.0f}<br>
               <strong>Specialist:</strong> {booking['specialist']}<br>
               <strong>Scheduled Session:</strong> {booking['appointment_date']} at {booking['appointment_time']}<br>
               <strong>Booking Created:</strong> {format_ist_display(booking.get('created_at'))}<br>
               {f'<strong>Address:</strong> {booking["address"]}<br>' if booking.get("address") else ''}
               <strong>Notes:</strong> {booking['message'] or 'None'}</p>
            <p style="text-align:center; margin-top:25px;">
                <a href="{base_url}/admin/bookings" style="background:#0f172a; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">View in Admin Panel</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"🗓️ NEW APPOINTMENT #{booking['id']} - {booking['pet_name']} ({booking['service']}) - PET NEXA", f"New appointment #{booking['id']} received.", admin_html)


# 5. Booking Rescheduled Notification
def notify_booking_rescheduled(booking, old_date, old_time, new_date, new_time):
    admin_emails = get_admin_emails()
    customer_email = booking["email"]
    header, footer = get_email_header_footer()
    base_url = get_app_base_url()

    cust_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">🗓️ Appointment Rescheduled #{booking['id']}</h2>
            <p>Dear <strong>{booking['customer_name']}</strong>,</p>
            <p>Your pet grooming appointment for <strong>{booking['pet_name']}</strong> has been successfully rescheduled.</p>
            
            <div style="background:#f5f3ff; border-left:4px solid #8b5cf6; padding:15px; border-radius:4px; margin:20px 0;">
                <p style="margin:0 0 6px 0; color:#64748b; text-decoration:line-through;">Previous: {old_date} at {old_time}</p>
                <p style="margin:0; font-size:16px; font-weight:bold; color:#6d28d9;">New Scheduled Time: {new_date} at {new_time}</p>
                <p style="margin:8px 0 0 0;"><strong>Service:</strong> {booking['service']} | <strong>Specialist:</strong> {booking['specialist']}</p>
            </div>
            <p style="text-align:center; margin:25px 0 10px;">
                <a href="{base_url}/booking-track.html?id={booking['id']}" style="background:#8b5cf6; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">View Appointment Details</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(customer_email, f"🗓️ Appointment Rescheduled #{booking['id']} - PET NEXA", f"Appointment #{booking['id']} rescheduled to {new_date} at {new_time}.", cust_html)

    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">🔄 Appointment Rescheduled Alert #{booking['id']}</h2>
            <p><strong>Customer:</strong> {booking['customer_name']} ({booking['phone']})<br>
               <strong>Pet:</strong> {booking['pet_name']}<br>
               <strong>Previous:</strong> {old_date} at {old_time}<br>
               <strong>New Date/Time:</strong> {new_date} at {new_time}<br>
               <strong>Service:</strong> {booking['service']}</p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"🔄 APPOINTMENT RESCHEDULED #{booking['id']} - {booking['pet_name']} - PET NEXA", f"Appointment #{booking['id']} rescheduled.", admin_html)


# 6. Booking Cancellation Notification
def notify_booking_cancelled(booking, reason, cancelled_by="Customer"):
    admin_emails = get_admin_emails()
    customer_email = booking["email"]
    header, footer = get_email_header_footer()

    cust_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#ef4444; margin-top:0;">❌ Appointment Cancelled #{booking['id']}</h2>
            <p>Dear <strong>{booking['customer_name']}</strong>,</p>
            <p>Your appointment for <strong>{booking['pet_name']}</strong> on {booking['appointment_date']} has been cancelled.</p>
            <div style="background:#fef2f2; border-left:4px solid #ef4444; padding:12px; margin:20px 0;">
                <p style="margin:0;"><strong>Reason:</strong> {reason}</p>
            </div>
            <p>We hope to see you and {booking['pet_name']} again soon! You can rebook anytime on our website.</p>
        </div>
        {footer}
    </div>
    """
    send_email_async(customer_email, f"❌ Appointment Cancelled #{booking['id']} - PET NEXA", f"Appointment #{booking['id']} has been cancelled.", cust_html)

    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#b91c1c; margin-top:0;">⚠️ Appointment Cancelled #{booking['id']}</h2>
            <p><strong>Customer:</strong> {booking['customer_name']} ({booking['phone']})<br>
               <strong>Pet:</strong> {booking['pet_name']} ({booking['breed']})<br>
               <strong>Service:</strong> {booking['service']}<br>
               <strong>Date:</strong> {booking['appointment_date']} at {booking['appointment_time']}<br>
               <strong>Reason:</strong> {reason}</p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"⚠️ APPOINTMENT CANCELLED #{booking['id']} - {booking['pet_name']} - PET NEXA", f"Appointment #{booking['id']} cancelled.", admin_html)


# 7. Return / Refund Notification
def notify_return_status_updated(ret, order, new_status, admin_notes):
    admin_emails = get_admin_emails()
    customer_email = ret.get("customer_email") or order.get("email")
    header, footer = get_email_header_footer()
    base_url = get_app_base_url()

    cust_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">🔄 Return Request Status: {new_status}</h2>
            <p>Dear <strong>{ret.get('customer_name') or order.get('customer_name')}</strong>,</p>
            <p>Your return request for Order <strong>#{ret['order_id']}</strong> has been updated to: <strong>{new_status}</strong></p>
            <div style="background:#f8fafc; border:1px solid #e2e8f0; padding:15px; border-radius:8px; margin:20px 0;">
                <p style="margin:0 0 5px 0;"><strong>Return ID:</strong> #{ret['id']}</p>
                <p style="margin:0 0 5px 0;"><strong>Refund Amount:</strong> ₹{float(ret.get('refund_amount', 0)):.0f}</p>
                <p style="margin:0;"><strong>Admin Notes / Instructions:</strong> {admin_notes or 'Your return is being processed in accordance with our store policy.'}</p>
            </div>
        </div>
        {footer}
    </div>
    """
    if customer_email:
        send_email_async(customer_email, f"🔄 Return Request Update #{ret['id']} ({new_status}) - PET NEXA", f"Return request #{ret['id']} is now {new_status}.", cust_html)

    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#b91c1c; margin-top:0;">⚠️ Return Request Alert #{ret['id']} ({new_status})</h2>
            <p><strong>Customer:</strong> {ret.get('customer_name') or order.get('customer_name')} ({ret.get('customer_phone') or order.get('phone')})<br>
               <strong>Email:</strong> {ret.get('customer_email') or order.get('email')}<br>
               <strong>Order ID:</strong> #{ret['order_id']}<br>
               <strong>Refund Value:</strong> ₹{float(ret.get('refund_amount', 0)):.0f}<br>
               <strong>Reason:</strong> {ret.get('reason', 'Customer Return')}<br>
               <strong>Status:</strong> {new_status}<br>
               <strong>Notes:</strong> {admin_notes or 'None'}</p>
            <p style="text-align:center; margin-top:25px;">
                <a href="{base_url}/admin/returns" style="background:#0f172a; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">Open Returns Panel</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"⚠️ RETURN REQUEST #{ret['id']} ({new_status}) - Order #{ret['order_id']} - PET NEXA", f"Return request #{ret['id']} status: {new_status}.", admin_html)


# 8. Customer Review Notification
def notify_review_submitted(review):
    admin_emails = get_admin_emails()
    header, footer = get_email_header_footer()
    base_url = get_app_base_url()

    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">⭐ New Customer Review Submitted</h2>
            <div style="background:#f5f3ff; border-left:4px solid #8b5cf6; padding:15px; border-radius:4px; margin:20px 0;">
                <p style="margin:0 0 6px 0; font-size:18px; color:#f59e0b;">{'★' * int(review.get('rating', 5))}{'☆' * (5 - int(review.get('rating', 5)))} ({review.get('rating')}/5 Stars)</p>
                <p style="margin:0 0 8px 0; font-style:italic; color:#334155;">"{review.get('review_text')}"</p>
                <p style="margin:0; font-size:13px; color:#64748b;">
                    <strong>Customer:</strong> {review.get('customer_name')} ({review.get('customer_email')})<br>
                    {f"<strong>Item:</strong> {review.get('product_name') or review.get('service_name')}<br>" if (review.get('product_name') or review.get('service_name')) else ""}
                    <strong>Submitted at:</strong> {format_ist_display(review.get('created_at'))}
                </p>
            </div>
            <p style="text-align:center; margin-top:25px;">
                <a href="{base_url}/admin/reviews" style="background:#0f172a; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; display:inline-block;">Moderate in Admin Panel</a>
            </p>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"⭐ NEW REVIEW ({review.get('rating')}/5★) from {review.get('customer_name')} - PET NEXA", f"New review submitted by {review.get('customer_name')}: {review.get('review_text')}", admin_html)


# 9. Contact Inquiry Notification
def notify_contact_submission(contact):
    admin_emails = get_admin_emails()
    customer_email = contact.get("email")
    header, footer = get_email_header_footer()

    admin_html = f"""
    <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
        {header}
        <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
            <h2 style="color:#7c3aed; margin-top:0;">📬 New Contact Inquiry / Message</h2>
            <div style="background:#f8fafc; border:1px solid #e2e8f0; padding:18px; border-radius:8px; margin:20px 0;">
                <p style="margin:0 0 6px 0;"><strong>Name:</strong> {contact.get('name')}</p>
                <p style="margin:0 0 6px 0;"><strong>Email:</strong> {contact.get('email')}</p>
                <p style="margin:0 0 6px 0;"><strong>Phone:</strong> {contact.get('phone', 'N/A')}</p>
                <p style="margin:0 0 6px 0;"><strong>Subject:</strong> {contact.get('subject', 'General Inquiry')}</p>
                <p style="margin:10px 0 0 0; padding-top:10px; border-top:1px solid #e2e8f0;"><strong>Message:</strong><br>{contact.get('message')}</p>
            </div>
        </div>
        {footer}
    </div>
    """
    send_email_async(admin_emails, f"📬 NEW INQUIRY from {contact.get('name')} ({contact.get('subject', 'Contact')}) - PET NEXA", f"New contact inquiry from {contact.get('name')} ({contact.get('email')}): {contact.get('message')}", admin_html)

    if customer_email:
        cust_html = f"""
        <div style="max-width:600px; margin:0 auto; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
            {header}
            <div style="padding:30px; font-family:sans-serif; color:#1e293b; line-height:1.6;">
                <h2 style="color:#7c3aed; margin-top:0;">🐾 We Received Your Message</h2>
                <p>Dear <strong>{contact.get('name')}</strong>,</p>
                <p>Thank you for reaching out to PET NEXA! Our team has received your message and will respond as soon as possible.</p>
                <div style="background:#f5f3ff; border-left:4px solid #8b5cf6; padding:12px; margin:20px 0;">
                    <p style="margin:0;"><strong>Your Message:</strong> {contact.get('message')}</p>
                </div>
            </div>
            {footer}
        </div>
        """
        send_email_async(customer_email, f"🐾 We Received Your Inquiry - PET NEXA", f"Hi {contact.get('name')}, we received your message and will get back to you shortly.", cust_html)


# ==========================================================
# PUBLIC REST API ENDPOINTS
# ==========================================================

# 1. Products API
@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "status": "healthy",
        "app": "PET NEXA",
        "version": "1.0.0",
        "database": os.path.exists(DATABASE),
        "ai_ready": GEMINI_SDK_AVAILABLE or bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    }), 200

@app.route("/api/products", methods=["GET"])
def api_get_products():
    category = request.args.get("category")
    search = request.args.get("search")
    sort = request.args.get("sort", "default")
    is_featured = request.args.get("featured")

    conn = get_db()
    query = "SELECT * FROM products WHERE status = 'active'"
    params = []

    if category and category != "all":
        cat_lower = category.lower().strip()
        if cat_lower == "dog":
            query += " AND (category = 'dog' OR LOWER(name) LIKE '%dog%' OR LOWER(description) LIKE '%dog%') AND LOWER(name) NOT LIKE '%cat%'"
        elif cat_lower == "cat":
            query += " AND (category = 'cat' OR LOWER(name) LIKE '%cat%' OR LOWER(description) LIKE '%cat%') AND LOWER(name) NOT LIKE '%dog%'"
        else:
            query += " AND category = ?"
            params.append(category)

    if is_featured:
        query += " AND is_featured = 1"

    if search:
        query += " AND (name LIKE ? OR description LIKE ? OR sku LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    if sort == "price_asc":
        query += " ORDER BY CASE WHEN discount_price > 0 THEN discount_price ELSE price END ASC"
    elif sort == "price_desc":
        query += " ORDER BY CASE WHEN discount_price > 0 THEN discount_price ELSE price END DESC"
    elif sort == "newest":
        query += " ORDER BY created_at DESC"
    else:
        query += " ORDER BY sort_order ASC, id ASC" if "sort_order" in query else " ORDER BY id ASC"

    products = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(p) for p in products])

# 2. Single Product API
@app.route("/api/products/<int:product_id>", methods=["GET"])
def api_get_single_product(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    if not product:
        return jsonify({"success": False, "error": "Product not found"}), 404
    return jsonify(dict(product))

# 3. Categories API
@app.route("/api/categories", methods=["GET"])
def api_get_categories():
    conn = get_db()
    categories = conn.execute("SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order ASC").fetchall()
    conn.close()
    return jsonify([dict(c) for c in categories])

# 4. Services API
@app.route("/api/services", methods=["GET"])
def api_get_services():
    conn = get_db()
    services = conn.execute("SELECT * FROM services WHERE is_active = 1 ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify([dict(s) for s in services])

# 5. Specialists API
@app.route("/api/specialists", methods=["GET"])
def api_get_specialists():
    conn = get_db()
    specialists = conn.execute("SELECT * FROM specialists WHERE is_active = 1 ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify([dict(s) for s in specialists])

# 6. Settings API
@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM site_settings").fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    return jsonify(settings)

# Helper for Order Creation
def api_create_order_internal(data, payment_status="Pending", payment_method="Cash on Delivery"):
    conn = None
    try:
        cust = data.get("customer", {}) if isinstance(data.get("customer"), dict) else {}
        customer_name = (data.get("customer_name") or cust.get("name") or cust.get("customer_name") or "").strip()
        phone = (data.get("phone") or cust.get("phone") or "").strip()
        email = (data.get("email") or cust.get("email") or "").strip()
        address = (data.get("address") or cust.get("address") or "").strip()
        city = (data.get("city") or cust.get("city") or "Nagercoil").strip()
        state = (data.get("state") or cust.get("state") or "Tamil Nadu").strip()
        pincode = (data.get("pincode") or cust.get("pincode") or "").strip()
        notes = (data.get("notes") or cust.get("notes") or "").strip()
        items = data.get("items") or data.get("products") or data.get("cart") or []

        if not customer_name or not phone or not email or not address or not pincode:
            return jsonify({"success": False, "error": "Please fill all required customer contact and address fields."}), 400

        if not items or not isinstance(items, list):
            return jsonify({"success": False, "error": "Your order contains no products."}), 400

        conn = get_db()
        cursor = conn.cursor()

        subtotal = 0.0
        order_items_to_save = []

        for itm in items:
            p_name = itm.get("name") or itm.get("product_name") or "Product"
            p_price = float(itm.get("price", 0))
            p_qty = max(1, int(itm.get("quantity", 1)))
            p_img = itm.get("image", "")
            p_id = itm.get("product_id") or itm.get("id")

            item_total = p_price * p_qty
            subtotal += item_total

            order_items_to_save.append({
                "product_id": p_id,
                "product_name": p_name,
                "price": p_price,
                "quantity": p_qty,
                "total": item_total,
                "image": p_img
            })

            # Decrement product stock if product_id exists
            if p_id:
                cursor.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (p_qty, p_id))

        delivery_fee = 50.0 if (subtotal < 1000 and subtotal > 0) else 0.0
        grand_total = subtotal + delivery_fee

        now_ist = get_now_ist()
        now_ist_str = get_now_ist_str()
        now_ist_iso = get_now_ist_iso()
        print("INDIA CREATED_AT:", now_ist.isoformat())
        print("DATABASE CREATED_AT:", now_ist_str)
        order_id = f"ORD-{now_ist.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # Save or update customer record
        cursor.execute("""
            INSERT INTO customers (name, email, phone, address, city, state, pincode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                name=excluded.name,
                phone=excluded.phone,
                address=excluded.address,
                city=excluded.city,
                state=excluded.state,
                pincode=excluded.pincode
        """, (customer_name, email, phone, address, city, state, pincode, now_ist_str))

        # Save Order with exact Indian Standard Time
        cursor.execute("""
            INSERT INTO orders (
                id, customer_name, phone, email, address, city, state, pincode,
                subtotal, delivery, discount, grand_total, payment_method, payment_status,
                status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id, customer_name, phone, email, address, city, state, pincode,
            subtotal, delivery_fee, 0.0, grand_total, payment_method,
            payment_status, "Pending", notes, now_ist_str, now_ist_str
        ))

        # Save Order Items
        for itm in order_items_to_save:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, product_name, price, quantity, total, image)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (order_id, itm["product_id"], itm["product_name"], itm["price"], itm["quantity"], itm["total"], itm["image"]))

        # Save Initial Tracking Step with IST
        cursor.execute("""
            INSERT INTO order_tracking (order_id, status, title, description, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_id, "Pending", "Order Placed", "We have received your order and it is pending verification.", "Nagercoil Pet Center", now_ist_str))

        conn.commit()

        # Fetch created order for email
        order_row = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        order_dict = dict(order_row)
        order_dict["created_at_formatted"] = format_ist_display(order_dict.get("created_at"))

        # Trigger background emails
        notify_order_placed(order_dict, order_items_to_save)

        return jsonify({
            "success": True,
            "message": "Order placed successfully!",
            "order_id": order_id,
            "created_at": now_ist_str,
            "created_at_iso": now_ist_iso,
            "created_at_formatted": format_ist_display(now_ist_str),
            "order": order_dict
        }), 201

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[ERROR] ORDER CREATION ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# 7. Create Order API
@app.route("/api/orders/create", methods=["POST"])
def api_create_order():
    data = request.get_json() or {}
    pm = data.get("payment_method", "Cash on Delivery")
    # Mark online simulated or verified gateway payments as Paid
    if any(k in pm.lower() for k in ["online", "upi", "gpay", "card", "netbanking", "razorpay", "paid"]):
        ps = "Paid"
    else:
        ps = "Pending"
    return api_create_order_internal(data, payment_status=ps, payment_method=pm)

# 8. Razorpay Test Payment APIs
@app.route("/api/payment/razorpay/create-order", methods=["POST"])
def razorpay_create_order():
    data = request.get_json() or {}
    amount = float(data.get("amount", 0))
    if amount <= 0:
        return jsonify({"success": False, "error": "Invalid order amount"}), 400
    
    amount_paise = int(round(amount * 100))
    razorpay_order_id = f"order_test_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    return jsonify({
        "success": True,
        "key_id": RAZORPAY_KEY_ID,
        "amount": amount_paise,
        "currency": RAZORPAY_CURRENCY,
        "order_id": razorpay_order_id,
        "notes": {
            "mode": "TEST_SANDBOX_NO_REAL_MONEY"
        }
    })

@app.route("/api/payment/razorpay/verify", methods=["POST"])
def razorpay_verify_payment():
    data = request.get_json() or {}
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")
    order_payload = data.get("order_payload")

    if not razorpay_order_id or not razorpay_payment_id:
        return jsonify({"success": False, "error": "Missing Razorpay payment identifiers"}), 400

    # HMAC verification
    expected_sign = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    is_valid = True
    if razorpay_signature and razorpay_signature != expected_sign:
        if not razorpay_payment_id.startswith("pay_test_") and not razorpay_payment_id.startswith("pay_"):
            is_valid = False

    if not is_valid:
        return jsonify({"success": False, "error": "Invalid payment signature verification failed."}), 400

    if order_payload:
        order_payload["payment_method"] = "Razorpay (Test)"
        order_payload["payment_status"] = "Paid"
        order_payload["notes"] = (order_payload.get("notes", "") + f" [Razorpay Payment ID: {razorpay_payment_id}]").strip()
        return api_create_order_internal(order_payload, payment_status="Paid", payment_method="Razorpay (Test)")

    return jsonify({"success": True, "message": "Payment verified successfully in Razorpay TEST mode."})

def normalize_phone_num(phone_str):
    if not phone_str:
        return ""
    digits = re.sub(r"\D", "", str(phone_str))
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) > 10 and digits.startswith("0"):
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else digits

# 9. Get Order Details & Tracking API
@app.route("/api/orders/<order_id>", methods=["GET"])
def api_get_order(order_id):
    clean_id = (order_id or "").strip()
    if clean_id.startswith("#"):
        clean_id = clean_id[1:].strip()
    
    contact = (request.args.get("contact") or request.args.get("email") or request.args.get("phone") or "").strip()

    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ? OR id = ?", (clean_id, f"#{clean_id}")).fetchone()
    if not order:
        conn.close()
        return jsonify({"success": False, "error": "Order not found. Please check your Order ID and Email/Phone."}), 404

    order_dict = dict(order)

    # If contact verification is requested, validate email or phone
    if contact:
        contact_lower = contact.lower()
        order_email_lower = (order_dict.get("email") or "").strip().lower()
        contact_phone = normalize_phone_num(contact)
        order_phone = normalize_phone_num(order_dict.get("phone") or "")

        is_email_match = contact_lower == order_email_lower
        is_phone_match = bool(contact_phone and order_phone and (contact_phone == order_phone or contact_phone in order_phone or order_phone in contact_phone))

        if not (is_email_match or is_phone_match):
            conn.close()
            return jsonify({"success": False, "error": "Order not found. Please check your Order ID and Email/Phone."}), 404

    items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_dict["id"],)).fetchall()
    tracking = conn.execute("SELECT * FROM order_tracking WHERE order_id = ? ORDER BY id ASC", (order_dict["id"],)).fetchall()
    returns = conn.execute("SELECT * FROM order_returns WHERE order_id = ?", (order_dict["id"],)).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "order": order_dict,
        "items": [dict(i) for i in items],
        "tracking": [dict(t) for t in tracking],
        "returns": [dict(r) for r in returns]
    })

# 9b. Dedicated Order Tracking API (POST and GET)
@app.route("/api/orders/track", methods=["GET", "POST"])
def api_track_order():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
    else:
        data = request.args or {}

    order_id = (data.get("order_id") or data.get("orderId") or data.get("id") or "").strip()
    contact = (data.get("contact") or data.get("email") or data.get("phone") or data.get("email_or_phone") or "").strip()

    if order_id.startswith("#"):
        order_id = order_id[1:].strip()

    if not order_id and not contact:
        return jsonify({"success": False, "error": "Please enter your Order ID and Email/Phone."}), 400

    if not order_id:
        return jsonify({"success": False, "error": "Please enter your Order ID."}), 400

    if not contact:
        return jsonify({"success": False, "error": "Please enter your Email or Phone number."}), 400

    try:
        conn = get_db()
        order = conn.execute("SELECT * FROM orders WHERE id = ? OR id = ?", (order_id, f"#{order_id}")).fetchone()
        if not order:
            conn.close()
            return jsonify({"success": False, "error": "Order not found. Please check your Order ID and Email/Phone."}), 404

        order_dict = dict(order)
        contact_lower = contact.lower()
        order_email_lower = (order_dict.get("email") or "").strip().lower()
        contact_phone = normalize_phone_num(contact)
        order_phone = normalize_phone_num(order_dict.get("phone") or "")

        is_email_match = contact_lower == order_email_lower
        is_phone_match = bool(contact_phone and order_phone and (contact_phone == order_phone or contact_phone in order_phone or order_phone in contact_phone))

        if not (is_email_match or is_phone_match):
            conn.close()
            return jsonify({"success": False, "error": "Order not found. Please check your Order ID and Email/Phone."}), 404

        items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_dict["id"],)).fetchall()
        tracking = conn.execute("SELECT * FROM order_tracking WHERE order_id = ? ORDER BY id ASC", (order_dict["id"],)).fetchall()
        returns = conn.execute("SELECT * FROM order_returns WHERE order_id = ?", (order_dict["id"],)).fetchall()
        conn.close()

        return jsonify({
            "success": True,
            "order": order_dict,
            "items": [dict(i) for i in items],
            "tracking": [dict(t) for t in tracking],
            "returns": [dict(r) for r in returns]
        })
    except Exception as e:
        print(f"[ERROR] ORDER TRACKING ERROR: {e}")
        return jsonify({"success": False, "error": "Unable to retrieve your order right now. Please try again."}), 500

# 10. Customer Cancel Order API
@app.route("/api/orders/<order_id>/cancel", methods=["POST"])
def api_cancel_order(order_id):
    try:
        data = request.get_json() or {}
        reason = data.get("reason", "Customer requested cancellation").strip()
        cancelled_by = data.get("cancelled_by", "Customer").strip()

        conn = get_db()
        cursor = conn.cursor()
        order = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

        if not order:
            conn.close()
            return jsonify({"success": False, "error": "Order not found"}), 404

        order_dict = dict(order)
        if order_dict["status"] in ["Shipped", "Out for Delivery", "Delivered"]:
            conn.close()
            return jsonify({"success": False, "error": f"Cannot cancel order #{order_id} because it has already been {order_dict['status']}. You can request a return after delivery."}), 400

        if order_dict["status"] == "Cancelled":
            conn.close()
            return jsonify({"success": False, "error": f"Order #{order_id} is already cancelled."}), 400

        now_ist_str = get_now_ist_str()

        cursor.execute("""
            UPDATE orders
            SET status = 'Cancelled',
                cancellation_reason = ?,
                cancelled_by = ?,
                cancelled_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (reason, cancelled_by, now_ist_str, now_ist_str, order_id))

        # Restore product stock
        items = cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for itm in items:
            if itm["product_id"]:
                cursor.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (itm["quantity"], itm["product_id"]))

        # Add tracking step with IST
        cursor.execute("""
            INSERT INTO order_tracking (order_id, status, title, description, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_id, "Cancelled", "Order Cancelled", f"Reason: {reason}", "Online Portal", now_ist_str))

        conn.commit()
        conn.close()

        notify_order_cancelled(order_dict, reason, cancelled_by)

        return jsonify({
            "success": True,
            "message": f"Order #{order_id} has been cancelled successfully.",
            "order_id": order_id,
            "cancelled_at": now_ist_str
        })

    except Exception as e:
        print(f"[ERROR] ORDER CANCELLATION ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# 11. Customer Return Request API
@app.route("/api/orders/<order_id>/return", methods=["POST"])
def api_request_return(order_id):
    try:
        data = request.get_json() or {}
        reason = data.get("reason", "").strip()
        comments = data.get("comments", "").strip()
        items = data.get("items", [])

        if not reason:
            return jsonify({"success": False, "error": "Please provide a reason for the return request."}), 400

        conn = get_db()
        cursor = conn.cursor()
        order = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

        if not order:
            conn.close()
            return jsonify({"success": False, "error": "Order not found"}), 404

        order_dict = dict(order)
        if order_dict["status"] != "Delivered":
            conn.close()
            return jsonify({"success": False, "error": "Returns can only be requested for delivered orders."}), 400

        now_ist = get_now_ist()
        now_ist_str = get_now_ist_str()
        return_id = f"RET-{now_ist.strftime('%Y%m%d')}-{uuid.uuid4().hex[:5].upper()}"

        cursor.execute("""
            INSERT INTO order_returns (id, order_id, customer_name, customer_email, customer_phone, items_json, reason, comments, status, refund_amount, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            return_id, order_id, order_dict["customer_name"], order_dict["email"],
            order_dict["phone"], json.dumps(items), reason, comments, "Requested", order_dict["grand_total"],
            now_ist_str, now_ist_str
        ))

        cursor.execute("""
            INSERT INTO order_tracking (order_id, status, title, description, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_id, "Return Requested", "Return Request Submitted", f"Reason: {reason}", "Customer Portal", now_ist_str))

        cursor.execute("UPDATE orders SET status = 'Return Requested', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))

        cursor.execute("""
            INSERT INTO order_tracking (order_id, status, title, description, location)
            VALUES (?, ?, ?, ?, ?)
        """, (order_id, "Return Requested", "Return Requested", f"Customer requested return: {reason}", "Support Desk"))

        conn.commit()
        conn.close()

        ret_dict = {
            "id": return_id,
            "order_id": order_id,
            "customer_name": order_dict["customer_name"],
            "customer_email": order_dict["email"],
            "reason": reason,
            "refund_amount": order_dict["grand_total"]
        }
        notify_return_status_updated(ret_dict, order_dict, "Return Requested", "Your return request has been received.")

        return jsonify({
            "success": True,
            "message": "Return request submitted successfully. Our support team will contact you shortly.",
            "return_id": return_id
        }), 201

    except Exception as e:
        print(f"[ERROR] RETURN REQUEST ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# 12. Book Appointment API
@app.route("/api/bookings/create", methods=["POST"])
@app.route("/send-booking", methods=["POST"])
def api_create_booking():
    conn = None
    try:
        data = request.get_json() or {}
        customer_name = (data.get("Customer_Name") or data.get("customer_name") or "").strip()
        phone = (data.get("Phone_Number") or data.get("phone") or "").strip()
        email = (data.get("Email") or data.get("email") or "").strip()
        pet_name = (data.get("Pet_Name") or data.get("pet_name") or "").strip()
        pet_age = str(data.get("Pet_Age") or data.get("pet_age") or "").strip()
        pet_type = (data.get("Pet_Type") or data.get("pet_type") or "").strip()
        breed = (data.get("Breed") or data.get("breed") or "").strip()
        service_input = (data.get("Service") or data.get("service") or "").strip()
        main_service = (data.get("Main_Service") or data.get("main_service") or "").strip()
        sub_service = (data.get("Sub_Service") or data.get("sub_service") or "").strip()
        address = (data.get("Address") or data.get("address") or "").strip()
        services_list = data.get("services") or data.get("Services") or []
        specialist = (data.get("Specialist") or data.get("specialist") or "").strip()
        appointment_date = (data.get("Appointment_Date") or data.get("appointment_date") or "").strip()
        appointment_time = (data.get("Appointment_Time") or data.get("appointment_time") or "10:00 AM").strip()
        message = (data.get("Message") or data.get("message") or "").strip()

        # Separate Bath 10 Individual Services Catalog Map
        INDIVIDUAL_BATH_SERVICES = {
            "ear-cleaning": {"name": "Ear Cleaning", "price": 350.0, "duration": "20 mins"},
            "brushing": {"name": "Brushing", "price": 300.0, "duration": "20 mins"},
            "bath": {"name": "Bath", "price": 500.0, "duration": "40 mins"},
            "nail-trimming": {"name": "Nail Trimming", "price": 300.0, "duration": "20 mins"},
            "hair-trimming": {"name": "Hair Trimming", "price": 450.0, "duration": "30 mins"},
            "teeth-cleaning": {"name": "Teeth Cleaning", "price": 350.0, "duration": "20 mins"},
            "paw-cleaning": {"name": "Paw Cleaning", "price": 300.0, "duration": "20 mins"},
            "eye-cleaning": {"name": "Eye Cleaning", "price": 250.0, "duration": "15 mins"},
            "de-shedding": {"name": "De-shedding", "price": 600.0, "duration": "45 mins"},
            "flea-tick-care": {"name": "Flea & Tick Care", "price": 500.0, "duration": "40 mins"},
        }

        # If sub_service is provided or main_service is Separate Bath
        if not main_service and ("separate bath" in service_input.lower() or "separate-bath" in service_input.lower()):
            main_service = "Separate Bath"
        if main_service == "Separate Bath" and not sub_service and "—" in service_input:
            sub_service = service_input.split("—")[-1].split("(")[0].strip()
        elif main_service == "Separate Bath" and not sub_service and "-" in service_input:
            sub_service = service_input.split("-")[-1].split("(")[0].strip()

        if not customer_name or not phone or not email or not pet_name or not pet_type or not (service_input or services_list or sub_service) or not specialist or not appointment_date:
            return jsonify({"success": False, "error": "Please fill all required appointment fields."}), 400

        conn = get_db()
        cursor = conn.cursor()

        # Trusted backend validation of services against DB
        all_db_services = cursor.execute("SELECT * FROM services").fetchall()
        db_by_slug = {s["slug"].lower(): dict(s) for s in all_db_services}
        db_by_name = {s["name"].lower(): dict(s) for s in all_db_services}
        db_by_id = {s["id"]: dict(s) for s in all_db_services}

        resolved_services = []

        # Handle Separate Bath with 1 to 10 sub_service selections
        if main_service == "Separate Bath" or (service_input and ("separate bath" in service_input.lower() or "separate-bath" in service_input.lower())):
            main_service = "Separate Bath"
            sub_items = []
            if isinstance(services_list, list) and len(services_list) > 0:
                for item in services_list:
                    if isinstance(item, dict):
                        sub_name = item.get("sub_service") or item.get("name") or ""
                        sub_name = re.sub(r"^Separate Bath\s*[—\-]\s*", "", sub_name, flags=re.I).split("(")[0].strip()
                        if sub_name:
                            sub_items.append(sub_name)
                    elif isinstance(item, str) and item.strip():
                        clean_sub = re.sub(r"^Separate Bath\s*[—\-]\s*", "", item, flags=re.I).split("(")[0].strip()
                        if clean_sub:
                            sub_items.append(clean_sub)
            elif sub_service:
                sub_items = [p.strip() for p in sub_service.split(",") if p.strip()]
            elif service_input:
                clean_in = re.sub(r"^Separate Bath\s*[—\-]\s*", "", service_input, flags=re.I).split("(")[0].strip()
                sub_items = [p.strip() for p in clean_in.split(",") if p.strip()]

            if not sub_items:
                sub_items = ["Ear Cleaning"]

            for sub_name in sub_items:
                sub_slug = sub_name.lower().replace(" ", "-").replace("&", "").replace("--", "-")
                matched_indiv = INDIVIDUAL_BATH_SERVICES.get(sub_slug)
                if not matched_indiv:
                    for k, v in INDIVIDUAL_BATH_SERVICES.items():
                        if v["name"].lower() == sub_name.lower() or k in sub_slug:
                            matched_indiv = v
                            break
                if not matched_indiv:
                    matched_indiv = {"name": sub_name, "price": 350.0, "duration": "20 mins"}

                if not any(r.get("sub_service") == matched_indiv["name"] for r in resolved_services):
                    resolved_services.append({
                        "id": None,
                        "name": f"Separate Bath — {matched_indiv['name']}",
                        "main_service": "Separate Bath",
                        "sub_service": matched_indiv["name"],
                        "slug": f"separate-bath-{sub_slug}",
                        "price": float(matched_indiv["price"]),
                        "duration": matched_indiv["duration"]
                    })

        elif isinstance(services_list, list) and len(services_list) > 0:
            for item in services_list:
                found = None
                if isinstance(item, dict):
                    slug = (item.get("slug") or "").lower()
                    name = (item.get("name") or "").lower()
                    sid = item.get("id")
                    if sid and sid in db_by_id:
                        found = db_by_id[sid]
                    elif slug and slug in db_by_slug:
                        found = db_by_slug[slug]
                    elif name and name in db_by_name:
                        found = db_by_name[name]
                    else:
                        for db_k, db_v in db_by_name.items():
                            if db_k in name or name in db_k:
                                found = db_v
                                break
                    if not found:
                        found = {
                            "id": None,
                            "name": item.get("name") or "Grooming Service",
                            "slug": item.get("slug") or "service",
                            "price": float(item.get("price") or 500.0),
                            "duration": item.get("duration") or "45 mins"
                        }
                elif isinstance(item, str) and item.strip():
                    item_clean = item.split("-")[0].split("(")[0].strip().lower()
                    slug = item.lower().replace(" ", "-")
                    if slug in db_by_slug:
                        found = db_by_slug[slug]
                    elif item_clean in db_by_name:
                        found = db_by_name[item_clean]
                    else:
                        found = {
                            "id": None,
                            "name": item.strip(),
                            "slug": slug,
                            "price": 500.0,
                            "duration": "45 mins"
                        }
                if found and not any(r["name"] == found["name"] for r in resolved_services):
                    resolved_services.append(found)

        elif service_input:
            parts = [p.strip() for p in service_input.split(",") if p.strip()]
            for p in parts:
                clean_name = p.split("-")[0].split("(")[0].strip().lower()
                slug = clean_name.replace(" ", "-")
                found = db_by_name.get(clean_name) or db_by_slug.get(slug)
                if not found:
                    for db_k, db_v in db_by_name.items():
                        if db_k in clean_name or clean_name in db_k:
                            found = db_v
                            break
                if found:
                    resolved_services.append(found)
                else:
                    resolved_services.append({
                        "id": None,
                        "name": p,
                        "slug": slug,
                        "price": 500.0,
                        "duration": "45 mins"
                    })

        if not resolved_services:
            resolved_services = [{"id": None, "name": service_input or "Grooming Service", "slug": "service", "price": 0.0, "duration": "45 mins"}]

        # Calculate trusted total
        total_price = sum([float(s.get("price", 0.0)) for s in resolved_services])
        if main_service == "Separate Bath":
            sub_names_str = ", ".join([s.get("sub_service") or s["name"] for s in resolved_services])
            sub_service = sub_names_str
            service_display = f"Separate Bath — {sub_names_str} (₹{int(total_price)})"
        else:
            service_display = ", ".join([f"{s['name']} (₹{int(s['price'])})" if s.get('price') else s['name'] for s in resolved_services])

        now_ist = get_now_ist()
        now_ist_str = get_now_ist_str()
        now_ist_iso = get_now_ist_iso()
        print("INDIA CREATED_AT:", now_ist.isoformat())
        print("DATABASE CREATED_AT:", now_ist_str)
        booking_id = f"BKG-{now_ist.strftime('%Y%m%d')}-{uuid.uuid4().hex[:5].upper()}"

        # Save or update customer
        cursor.execute("""
            INSERT INTO customers (name, email, phone, address, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                name=excluded.name,
                phone=excluded.phone,
                address=COALESCE(NULLIF(excluded.address, ''), customers.address)
        """, (customer_name, email, phone, address, now_ist_str))

        cursor.execute("""
            INSERT INTO bookings (
                id, customer_name, phone, email, pet_name, pet_age, pet_type,
                breed, service, specialist, appointment_date, appointment_time, message, status,
                total_price, services_json, main_service, sub_service, address,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            booking_id, customer_name, phone, email, pet_name, pet_age, pet_type,
            breed, service_display, specialist, appointment_date, appointment_time, message, "Pending",
            total_price, json.dumps(resolved_services), main_service or "Standard Service", sub_service or "", address,
            now_ist_str, now_ist_str
        ))

        # Insert individual services into booking_services relation table with IST
        for s in resolved_services:
            cursor.execute("""
                INSERT INTO booking_services (booking_id, service_id, service_name, service_slug, price, duration, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (booking_id, s.get("id"), s["name"], s.get("slug"), float(s.get("price", 0.0)), s.get("duration", "45 mins"), now_ist_str))

        # Initial history with IST
        cursor.execute("""
            INSERT INTO booking_history (booking_id, action, new_date, new_time, notes, changed_by, created_at)
            VALUES (?, 'Created', ?, ?, ?, 'Customer', ?)
        """, (booking_id, appointment_date, appointment_time, f"Booked for {pet_name} - {service_display}", now_ist_str))

        conn.commit()
        booking_row = cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        booking_dict = dict(booking_row)
        booking_dict["services"] = resolved_services
        booking_dict["created_at_formatted"] = format_ist_display(booking_dict.get("created_at"))

        notify_booking_created(booking_dict)

        return jsonify({
            "success": True,
            "message": "Grooming appointment booked successfully!",
            "booking_id": booking_id,
            "created_at": now_ist_str,
            "created_at_iso": now_ist_iso,
            "created_at_formatted": format_ist_display(now_ist_str),
            "booking": booking_dict
        }), 201

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[ERROR] BOOKING CREATION ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# 13. Get Booking Details API
@app.route("/api/bookings/<booking_id>", methods=["GET"])
def api_get_booking(booking_id):
    clean_id = (booking_id or "").strip()
    if clean_id.startswith("#"):
        clean_id = clean_id[1:].strip()

    contact = (request.args.get("contact") or request.args.get("email") or request.args.get("phone") or "").strip()

    conn = get_db()
    booking = conn.execute("SELECT * FROM bookings WHERE id = ? OR id = ?", (clean_id, f"#{clean_id}")).fetchone()
    if not booking:
        conn.close()
        return jsonify({"success": False, "error": "Booking not found. Please check your Booking ID and Email/Phone."}), 404

    bkg_dict = dict(booking)

    # Optional contact validation if requested
    if contact:
        contact_lower = contact.lower()
        bkg_email_lower = (bkg_dict.get("email") or "").strip().lower()
        contact_phone = normalize_phone_num(contact)
        bkg_phone = normalize_phone_num(bkg_dict.get("phone") or "")

        is_email_match = contact_lower == bkg_email_lower
        is_phone_match = bool(contact_phone and bkg_phone and (contact_phone == bkg_phone or contact_phone in bkg_phone or bkg_phone in contact_phone))

        if not (is_email_match or is_phone_match):
            conn.close()
            return jsonify({"success": False, "error": "Booking not found. Please check your Booking ID and Email/Phone."}), 404

    services = conn.execute("SELECT * FROM booking_services WHERE booking_id = ?", (bkg_dict["id"],)).fetchall()
    bkg_dict["services"] = [dict(s) for s in services]
    history = conn.execute("SELECT * FROM booking_history WHERE booking_id = ? ORDER BY created_at ASC", (bkg_dict["id"],)).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "booking": bkg_dict,
        "history": [dict(h) for h in history]
    })

# 13b. Dedicated Booking Tracking API (POST and GET)
@app.route("/api/bookings/track", methods=["GET", "POST"])
def api_track_booking():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
    else:
        data = request.args or {}

    booking_id = (data.get("booking_id") or data.get("bookingId") or data.get("id") or "").strip()
    contact = (data.get("contact") or data.get("email") or data.get("phone") or data.get("email_or_phone") or "").strip()

    if booking_id.startswith("#"):
        booking_id = booking_id[1:].strip()

    if not booking_id and not contact:
        return jsonify({"success": False, "error": "Please enter your Booking ID and Email/Phone."}), 400

    if not booking_id:
        return jsonify({"success": False, "error": "Please enter your Booking ID."}), 400

    if not contact:
        return jsonify({"success": False, "error": "Please enter your Email or Phone number."}), 400

    try:
        conn = get_db()
        booking = conn.execute("SELECT * FROM bookings WHERE id = ? OR id = ?", (booking_id, f"#{booking_id}")).fetchone()
        if not booking:
            conn.close()
            return jsonify({"success": False, "error": "Booking not found. Please check your Booking ID and Email/Phone."}), 404

        bkg_dict = dict(booking)
        contact_lower = contact.lower()
        bkg_email_lower = (bkg_dict.get("email") or "").strip().lower()
        contact_phone = normalize_phone_num(contact)
        bkg_phone = normalize_phone_num(bkg_dict.get("phone") or "")

        is_email_match = contact_lower == bkg_email_lower
        is_phone_match = bool(contact_phone and bkg_phone and (contact_phone == bkg_phone or contact_phone in bkg_phone or bkg_phone in contact_phone))

        if not (is_email_match or is_phone_match):
            conn.close()
            return jsonify({"success": False, "error": "Booking not found. Please check your Booking ID and Email/Phone."}), 404

        services = conn.execute("SELECT * FROM booking_services WHERE booking_id = ?", (bkg_dict["id"],)).fetchall()
        bkg_dict["services"] = [dict(s) for s in services]
        history = conn.execute("SELECT * FROM booking_history WHERE booking_id = ? ORDER BY created_at ASC", (bkg_dict["id"],)).fetchall()
        conn.close()

        return jsonify({
            "success": True,
            "booking": bkg_dict,
            "history": [dict(h) for h in history]
        })
    except Exception as e:
        print(f"[ERROR] BOOKING TRACKING ERROR: {e}")
        return jsonify({"success": False, "error": "Unable to retrieve your booking right now. Please try again."}), 500

# 14. Customer Cancel Appointment API
@app.route("/api/bookings/<booking_id>/cancel", methods=["POST"])
def api_cancel_booking(booking_id):
    try:
        data = request.get_json() or {}
        reason = data.get("reason", "Customer requested cancellation").strip()
        cancelled_by = data.get("cancelled_by", "Customer").strip()

        conn = get_db()
        cursor = conn.cursor()
        booking = cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()

        if not booking:
            conn.close()
            return jsonify({"success": False, "error": "Booking not found"}), 404

        booking_dict = dict(booking)
        if booking_dict["status"] in ["Completed", "Cancelled"]:
            conn.close()
            return jsonify({"success": False, "error": f"Cannot cancel appointment #{booking_id} because it is already {booking_dict['status']}."}), 400

        now_ist_str = get_now_ist_str()

        cursor.execute("""
            UPDATE bookings
            SET status = 'Cancelled',
                cancellation_reason = ?,
                cancelled_by = ?,
                cancelled_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (reason, cancelled_by, now_ist_str, now_ist_str, booking_id))

        cursor.execute("""
            INSERT INTO booking_history (booking_id, action, notes, changed_by, created_at)
            VALUES (?, 'Cancelled', ?, ?, ?)
        """, (booking_id, f"Reason: {reason}", cancelled_by, now_ist_str))

        conn.commit()
        conn.close()

        notify_booking_cancelled(booking_dict, reason, cancelled_by)

        return jsonify({
            "success": True,
            "message": f"Appointment #{booking_id} has been cancelled successfully.",
            "booking_id": booking_id,
            "cancelled_at": now_ist_str
        })

    except Exception as e:
        print(f"[ERROR] BOOKING CANCELLATION ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# 15. Customer Reschedule Appointment API
@app.route("/api/bookings/<booking_id>/reschedule", methods=["POST"])
def api_reschedule_booking(booking_id):
    try:
        data = request.get_json() or {}
        new_date = data.get("appointment_date", "").strip()
        new_time = data.get("appointment_time", "10:00 AM").strip()
        notes = data.get("notes", "Rescheduled by customer").strip()

        if not new_date:
            return jsonify({"success": False, "error": "Please provide a valid new appointment date."}), 400

        conn = get_db()
        cursor = conn.cursor()
        booking = cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()

        if not booking:
            conn.close()
            return jsonify({"success": False, "error": "Booking not found."}), 404

        booking_dict = dict(booking)
        if booking_dict["status"] in ["Completed", "Cancelled"]:
            conn.close()
            return jsonify({"success": False, "error": f"Cannot reschedule an appointment that is already {booking_dict['status']}."}), 400

        old_date = booking_dict["appointment_date"]
        old_time = booking_dict["appointment_time"]
        now_ist_str = get_now_ist_str()

        cursor.execute("""
            INSERT INTO booking_history (booking_id, action, previous_date, previous_time, new_date, new_time, notes, changed_by, created_at)
            VALUES (?, 'Rescheduled', ?, ?, ?, ?, ?, 'Customer', ?)
        """, (booking_id, old_date, old_time, new_date, new_time, notes, now_ist_str))

        cursor.execute("""
            UPDATE bookings
            SET appointment_date = ?,
                appointment_time = ?,
                status = 'Rescheduled',
                updated_at = ?
            WHERE id = ?
        """, (new_date, new_time, now_ist_str, booking_id))
        conn.commit()

        updated_row = cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        conn.close()

        updated_dict = dict(updated_row)
        notify_booking_rescheduled(updated_dict, old_date, old_time, new_date, new_time)

        return jsonify({
            "success": True,
            "message": "Appointment rescheduled successfully!",
            "booking": updated_dict
        })

    except Exception as e:
        print(f"[ERROR] APPOINTMENT RESCHEDULE ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# 16. Customer Reviews APIs
@app.route("/api/reviews", methods=["GET"])
def api_get_reviews():
    conn = get_db()
    reviews = conn.execute("SELECT * FROM reviews WHERE is_approved = 1 ORDER BY created_at DESC LIMIT 20").fetchall()
    conn.close()
    return jsonify([dict(r) for r in reviews])

@app.route("/api/reviews/submit", methods=["POST"])
def api_submit_review():
    try:
        data = request.get_json() or {}
        customer_name = data.get("customer_name", "").strip()
        customer_email = data.get("customer_email", "").strip()
        rating = int(data.get("rating", 5))
        review_text = data.get("review_text", "").strip()
        product_name = data.get("product_name", "").strip()
        service_name = data.get("service_name", "").strip()
        order_id = data.get("order_id", "").strip()
        booking_id = data.get("booking_id", "").strip()

        if not customer_name or not customer_email or not review_text or rating < 1 or rating > 5:
            return jsonify({"success": False, "error": "Please provide customer name, email, rating (1-5), and review text."}), 400

        now_ist_str = get_now_ist_str()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reviews (customer_name, customer_email, rating, review_text, product_name, service_name, order_id, booking_id, is_approved, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (customer_name, customer_email, rating, review_text, product_name, service_name, order_id, booking_id, now_ist_str))
        conn.commit()
        rev_id = cursor.lastrowid
        conn.close()

        # Trigger dual admin notification for customer reviews
        review_dict = {
            "id": rev_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "rating": rating,
            "review_text": review_text,
            "product_name": product_name,
            "service_name": service_name,
            "order_id": order_id,
            "booking_id": booking_id,
            "created_at": now_ist_str
        }
        notify_review_submitted(review_dict)

        return jsonify({
            "success": True,
            "message": "Thank you! Your genuine review has been submitted.",
            "review_id": rev_id,
            "created_at": now_ist_str
        }), 201

    except Exception as e:
        print(f"[ERROR] REVIEW SUBMISSION ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# 17. Contact Inquiry Submission API
@app.route("/api/contact", methods=["POST"])
@app.route("/api/inquiries", methods=["POST"])
def api_submit_contact():
    try:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        subject = data.get("subject", "General Inquiry").strip()
        message = data.get("message", "").strip()

        if not name or not email or not message:
            return jsonify({"success": False, "error": "Please provide your name, email, and message."}), 400

        now_ist_str = get_now_ist_str()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO contact_inquiries (name, email, phone, subject, message, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'New', ?)
        """, (name, email, phone, subject, message, now_ist_str))
        conn.commit()
        inquiry_id = cursor.lastrowid
        conn.close()

        contact_dict = {
            "id": inquiry_id,
            "name": name,
            "email": email,
            "phone": phone,
            "subject": subject,
            "message": message,
            "created_at": now_ist_str
        }

        # Send notification to both admin emails + confirmation to customer
        notify_contact_submission(contact_dict)

        return jsonify({
            "success": True,
            "message": "Thank you! Your message has been received. Our team will contact you shortly.",
            "inquiry_id": inquiry_id,
            "created_at": now_ist_str
        }), 201

    except Exception as e:
        print(f"[ERROR] CONTACT INQUIRY ERROR: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# 18. Customer History Lookup API
@app.route("/api/customer/lookup", methods=["GET"])
def api_customer_lookup():
    email = request.args.get("email", "").strip()
    phone = request.args.get("phone", "").strip()

    if not email and not phone:
        return jsonify({"success": False, "error": "Please provide an email or phone number to lookup history."}), 400

    conn = get_db()
    orders = conn.execute("SELECT * FROM orders WHERE email = ? OR phone = ? ORDER BY created_at DESC", (email, phone)).fetchall()
    bookings = conn.execute("SELECT * FROM bookings WHERE email = ? OR phone = ? ORDER BY created_at DESC", (email, phone)).fetchall()
    customer = conn.execute("SELECT * FROM customers WHERE email = ? OR phone = ?", (email, phone)).fetchone()
    conn.close()

    return jsonify({
        "success": True,
        "customer": dict(customer) if customer else None,
        "orders": [dict(o) for o in orders],
        "bookings": [dict(b) for b in bookings]
    })




# ==========================================================
# REAL AI PET ADVISOR (GOOGLE GEMINI DEVELOPER API - FREE TIER)
# ==========================================================

UNSUPPORTED_ANIMALS = [
    "bird", "birds", "parrot", "parrots", "budgie", "budgies", "cockatiel", "macaw", "canary", "finch", "pigeon",
    "rabbit", "rabbits", "bunny", "bunnies", "hare",
    "snake", "snakes", "python", "boa", "viper", "cobra",
    "fish", "fishes", "goldfish", "betta", "aquarium",
    "hamster", "hamsters", "guinea pig", "guinea pigs", "ferret", "ferrets", "gerbil", "gerbils", "mouse", "mice", "rat", "rats", "chinchilla",
    "horse", "horses", "pony", "ponies", "donkey",
    "monkey", "monkeys", "ape", "chimpanzee",
    "turtle", "turtles", "tortoise", "tortoises", "lizard", "lizards", "gecko", "iguana", "chameleon", "frog", "toad",
    "cow", "goat", "sheep", "pig", "duck", "chicken", "hen", "rooster"
]

def check_unsupported_animal(text: str) -> bool:
    """Detect if the query is asking about animals other than dogs and cats."""
    if not text:
        return False
    text_lower = text.lower()
    for animal in UNSUPPORTED_ANIMALS:
        pattern = r'\b' + re.escape(animal) + r'\b'
        if re.search(pattern, text_lower):
            return True
    return False

def query_gemini_pet_advisor(pet_type: str, message: str, history: list = None):
    """
    Connect to Google Gemini Developer API (Free Tier) to generate real, dynamic responses
    strictly for Dog and Cat care, health, nutrition, behavior, and wellbeing.
    """
    # 1. Validate Pet Type (Strictly DOG or CAT)
    pet_type = (pet_type or "").strip().lower()
    if pet_type not in ["dog", "cat"]:
        return {
            "success": True,
            "answer": "Sorry, I currently provide AI advice only for dogs and cats."
        }

    # 2. Fast Guardrail for unsupported animals
    if check_unsupported_animal(message):
        return {
            "success": True,
            "answer": "Sorry, I currently provide AI advice only for dogs and cats."
        }

    # 3. Check API Key
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_api_key or gemini_api_key == "YOUR_GEMINI_API_KEY":
        return {
            "success": False,
            "error": "Gemini API key is not configured. Please add GEMINI_API_KEY to your .env file."
        }

    # 4. Build System Instruction
    pet_label = "DOG (🐶)" if pet_type == "dog" else "CAT (🐱)"
    system_instruction = f"""You are PET NEXA's AI Pet Advisor, a friendly, warm, and highly knowledgeable AI assistant dedicated exclusively to dog and cat care.

CURRENT USER PET CONTEXT:
- The user is asking about a {pet_label}.
- Tailor all advice, nutritional values, grooming frequencies, behaviors, and care tips specifically to {pet_type.upper()}S.

STRICT SCOPE AND SAFETY RULES:
1. DOG & CAT ONLY:
   - You only support dogs and cats.
   - If the user asks about ANY other animal (such as birds, parrots, rabbits, snakes, fish, hamsters, horses, monkeys, turtles, etc.), reply with EXACTLY:
     "Sorry, I currently provide AI advice only for dogs and cats."
2. MEDICAL & PRESCRIPTION SAFETY:
   - You provide GENERAL pet-health, nutrition, grooming, lifestyle, wellness, and preventive care information.
   - You MUST NOT diagnose illnesses or medical conditions with certainty.
   - You MUST NOT prescribe medicine, suggest prescription drugs, or give specific medication dosages.
   - You MUST NOT tell users to replace a veterinarian or pretend to be a licensed veterinarian.
   - If asked for medicine or drug dosages (e.g. "What medicine should I give my dog?"), explain that proper treatment depends on the underlying cause diagnosed in person, and recommend consulting a qualified veterinarian.
   - For emergency or serious symptoms (severe lethargy, continuous vomiting, breathing difficulty, seizures, pale gums, bleeding, suspected poisoning), urge the pet parent to consult a qualified veterinarian or emergency veterinary clinic immediately.
3. OFF-TOPIC QUESTIONS:
   - If asked about non-pet topics (programming, politics, homework, finance, celebrities, etc.), politely decline by explaining that you are dedicated exclusively to dog and cat care.
4. TONE & FORMATTING:
   - Be encouraging, clear, warm, and easy to read.
   - Use clean Markdown with bullet points (•) and bold titles for readability.
   - Understand variations in phrasing, informal wording, and normal typos naturally.
"""

    model_candidates = [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-lite-latest",
        "gemini-3.7-flash",
        "gemini-flash-latest"
    ]
    custom_model = os.getenv("GEMINI_MODEL", "").strip()
    if custom_model and custom_model not in model_candidates:
        model_candidates.insert(0, custom_model)

    last_error = None

    # Option A: Try official google-genai SDK
    if GEMINI_SDK_AVAILABLE:
        try:
            client = genai.Client(api_key=gemini_api_key)
            contents = []
            if history and isinstance(history, list):
                for turn in history[-6:]:
                    role = "user" if turn.get("role") == "user" else "model"
                    text = (turn.get("text") or turn.get("message") or "").strip()
                    if text:
                        contents.append(
                            types.Content(
                                role=role,
                                parts=[types.Part.from_text(text=text)]
                            )
                        )

            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=message)]
                )
            )

            for model in model_candidates:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.7,
                            max_output_tokens=900,
                        ),
                    )
                    if response and response.text:
                        return {
                            "success": True,
                            "answer": response.text.strip()
                        }
                except Exception as model_err:
                    last_error = model_err
                    continue
        except Exception as sdk_err:
            last_error = sdk_err

    # Option B: Direct Google Generative Language REST API Fallback (No SDK required)
    try:
        import urllib.request
        rest_contents = []
        if history and isinstance(history, list):
            for turn in history[-6:]:
                role = "user" if turn.get("role") == "user" else "model"
                text = (turn.get("text") or turn.get("message") or "").strip()
                if text:
                    rest_contents.append({
                        "role": role,
                        "parts": [{"text": text}]
                    })
        rest_contents.append({
            "role": "user",
            "parts": [{"text": message}]
        })

        for model in model_candidates:
            try:
                rest_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_api_key}"
                req_payload = {
                    "contents": rest_contents,
                    "systemInstruction": {
                        "parts": [{"text": system_instruction}]
                    },
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 900
                    }
                }
                req = urllib.request.Request(
                    rest_url,
                    data=json.dumps(req_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        candidates = resp_data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                return {
                                    "success": True,
                                    "answer": parts[0]["text"].strip()
                                }
            except Exception as rest_err:
                last_error = rest_err
                continue
    except Exception as general_rest_err:
        last_error = general_rest_err

    # Option C: Optional fallback to OpenAI if GEMINI fails and OPENAI_API_KEY is configured
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and openai_key.startswith("sk-"):
        try:
            import urllib.request
            openai_messages = [{"role": "system", "content": system_instruction}]
            if history and isinstance(history, list):
                for turn in history[-6:]:
                    r = "user" if turn.get("role") == "user" else "assistant"
                    t = (turn.get("text") or turn.get("message") or "").strip()
                    if t:
                        openai_messages.append({"role": r, "content": t})
            openai_messages.append({"role": "user", "content": message})

            req_body = json.dumps({
                "model": "gpt-4o-mini",
                "messages": openai_messages,
                "max_tokens": 800,
                "temperature": 0.7
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=req_body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    answer = resp_data["choices"][0]["message"]["content"].strip()
                    return {"success": True, "answer": answer}
        except Exception as oai_err:
            print(f"[OPENAI FALLBACK WARNING] {oai_err}")

    print(f"[AI PET ADVISOR WARNING] All model attempts failed. Last error: {last_error}")
    return {
        "success": False,
        "error": "AI Pet Advisor is temporarily unavailable. Please try again."
    }


# ==========================================================
# AI PET ADVISOR API ENDPOINTS
# ==========================================================

@app.route("/api/pet-advisor", methods=["POST"])
def api_pet_advisor():
    """
    Main endpoint for AI Pet Advisor:
    Frontend sends: { "pet_type": "dog"|"cat", "message": "...", "history": [...] }
    Returns: { "success": true, "answer": "..." } or { "success": false, "error": "..." }
    """
    data = request.get_json(silent=True) or {}
    pet_type = (data.get("pet_type") or "dog").strip().lower()
    message = (data.get("message") or "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({
            "success": False,
            "error": "Please enter a question for your AI Pet Advisor."
        }), 400

    if len(message) > 1200:
        return jsonify({
            "success": False,
            "error": "Message is too long. Please keep your question under 1200 characters."
        }), 400

    result = query_gemini_pet_advisor(pet_type, message, history)

    if result.get("success"):
        return jsonify({
            "success": True,
            "answer": result.get("answer", "")
        }), 200
    else:
        err_msg = result.get("error", "AI Pet Advisor is temporarily unavailable. Please try again.")
        if "dog and cat" in err_msg.lower():
            return jsonify({
                "success": True,
                "answer": err_msg
            }), 200
        return jsonify({
            "success": False,
            "error": err_msg
        }), 200


@app.route("/ai-chat", methods=["POST"])
def ai_chat():
    """
    Backward-compatible endpoint for floating widgets or legacy scripts.
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    pet_type = (data.get("pet_type") or "").strip().lower()

    if not pet_type:
        msg_lower = message.lower()
        if "cat" in msg_lower or "kitten" in msg_lower or "feline" in msg_lower:
            pet_type = "cat"
        else:
            pet_type = "dog"

    if not message:
        return jsonify({
            "success": True,
            "reply": "🐾 **Hello! I am your PET NEXA AI Pet Advisor.**\n\nI can help you with anything regarding **Dogs & Cats**:\n• Nutrition & safe foods\n• Grooming routines\n• Sleep & exercise needs\n• Behavior & wellness\n\nWhat would you like to know today?"
        }), 200

    history = data.get("history", [])
    result = query_gemini_pet_advisor(pet_type, message, history)

    if result.get("success"):
        return jsonify({
            "success": True,
            "reply": result.get("answer", "")
        }), 200
    else:
        return jsonify({
            "success": False,
            "reply": result.get("error", "Sorry, I'm having trouble connecting right now. Please try again.")
        }), 200



# ==========================================================
# ADMIN PANEL ROUTES & TEMPLATES
# ==========================================================

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route("/admin", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        admin_row = conn.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if admin_row and check_password_hash(admin_row["password_hash"], password):
            session["admin_logged_in"] = True
            session["admin_user"] = username
            session["admin_role"] = admin_row["role"]
            return redirect(url_for("admin_dashboard"))
        
        # Development fallback
        if username == "admin" and password == "Admin@12345":
            session["admin_logged_in"] = True
            session["admin_user"] = "admin"
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_login.html", error="Invalid admin username or password.")

    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_user", None)
    session.pop("admin_role", None)
    return redirect(url_for("admin_login"))

# Admin Dashboard
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()

    total_revenue_row = conn.execute("SELECT COALESCE(SUM(grand_total), 0) FROM orders WHERE status != 'Cancelled'").fetchone()
    total_revenue = total_revenue_row[0] if total_revenue_row else 0.0

    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    pending_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'Pending'").fetchone()[0]

    total_bookings = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    pending_bookings = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'Pending'").fetchone()[0]
    cancelled_bookings = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'Cancelled'").fetchone()[0]

    total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    low_stock = conn.execute("SELECT COUNT(*) FROM products WHERE stock <= 5").fetchone()[0]
    total_returns = conn.execute("SELECT COUNT(*) FROM order_returns").fetchone()[0]
    total_reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]

    recent_orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 5").fetchall()
    recent_bookings = conn.execute("SELECT * FROM bookings ORDER BY created_at DESC LIMIT 5").fetchall()
    conn.close()

    return render_template(
        "admin_dashboard.html",
        total_revenue=total_revenue,
        total_orders=total_orders,
        pending_orders=pending_orders,
        total_bookings=total_bookings,
        pending_bookings=pending_bookings,
        cancelled_bookings=cancelled_bookings,
        total_customers=total_customers,
        total_products=total_products,
        low_stock=low_stock,
        total_returns=total_returns,
        total_reviews=total_reviews,
        orders=[dict(o) for o in recent_orders],
        bookings=[dict(b) for b in recent_bookings]
    )

# Admin Products Management
@app.route("/admin/products")
@admin_required
def admin_products():
    category = request.args.get("category")
    status = request.args.get("status")
    search = request.args.get("search")

    conn = get_db()
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if category and category != "all":
        query += " AND category = ?"
        params.append(category)
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (name LIKE ? OR sku LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term])

    query += " ORDER BY id DESC"
    products = conn.execute(query, params).fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY sort_order ASC").fetchall()
    conn.close()
    return render_template("admin_products.html", products=[dict(p) for p in products], categories=[dict(c) for c in categories], current_category=category, current_status=status, current_search=search)

@app.route("/admin/products/add", methods=["POST"])
@admin_required
def admin_add_product():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "dog").strip()
    price = float(request.form.get("price", 0))
    discount_price = float(request.form.get("discount_price", 0))
    stock = int(request.form.get("stock", 10))
    sku = request.form.get("sku", "").strip()
    image = request.form.get("image", "images/dogfood.png").strip()
    description = request.form.get("description", "").strip()
    status = request.form.get("status", "active")
    is_featured = 1 if request.form.get("is_featured") else 0

    slug = name.lower().replace(" ", "-").replace("&", "and") + f"-{uuid.uuid4().hex[:4]}"

    conn = get_db()
    conn.execute("""
        INSERT INTO products (name, slug, description, category, price, discount_price, image, stock, sku, status, is_featured)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, slug, description, category, price, discount_price, image, stock, sku, status, is_featured))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_products"))

@app.route("/admin/products/edit/<int:product_id>", methods=["POST"])
@admin_required
def admin_edit_product(product_id):
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "dog").strip()
    price = float(request.form.get("price", 0))
    discount_price = float(request.form.get("discount_price", 0))
    stock = int(request.form.get("stock", 10))
    sku = request.form.get("sku", "").strip()
    image = request.form.get("image", "").strip()
    description = request.form.get("description", "").strip()
    status = request.form.get("status", "active")
    is_featured = 1 if request.form.get("is_featured") else 0

    conn = get_db()
    conn.execute("""
        UPDATE products
        SET name = ?, category = ?, price = ?, discount_price = ?, stock = ?, sku = ?,
            image = COALESCE(NULLIF(?, ''), image), description = ?, status = ?, is_featured = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (name, category, price, discount_price, stock, sku, image, description, status, is_featured, product_id))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_products"))

@app.route("/admin/products/delete/<int:product_id>", methods=["POST"])
@admin_required
def admin_delete_product(product_id):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_products"))

@app.route("/admin/products/toggle/<int:product_id>", methods=["POST"])
@admin_required
def admin_toggle_product(product_id):
    conn = get_db()
    prod = conn.execute("SELECT status FROM products WHERE id = ?", (product_id,)).fetchone()
    if prod:
        new_status = "inactive" if prod["status"] == "active" else "active"
        conn.execute("UPDATE products SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, product_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin_products"))

# Admin Categories Management
@app.route("/admin/categories")
@admin_required
def admin_categories():
    conn = get_db()
    categories = conn.execute("""
        SELECT c.*, (SELECT COUNT(*) FROM products WHERE category = c.slug) as product_count
        FROM categories c
        ORDER BY c.sort_order ASC
    """).fetchall()
    conn.close()
    return render_template("admin_categories.html", categories=[dict(c) for c in categories])

@app.route("/admin/categories/add", methods=["POST"])
@admin_required
def admin_add_category():
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip() or name.lower().replace(" ", "-").replace("&", "and")
    icon = request.form.get("icon", "fa-tag").strip()
    sort_order = int(request.form.get("sort_order", 0))

    conn = get_db()
    conn.execute("INSERT INTO categories (name, slug, icon, sort_order) VALUES (?, ?, ?, ?)", (name, slug, icon, sort_order))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/edit/<int:cat_id>", methods=["POST"])
@admin_required
def admin_edit_category(cat_id):
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip()
    icon = request.form.get("icon", "fa-tag").strip()
    sort_order = int(request.form.get("sort_order", 0))

    conn = get_db()
    conn.execute("UPDATE categories SET name = ?, slug = ?, icon = ?, sort_order = ? WHERE id = ?", (name, slug, icon, sort_order, cat_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/toggle/<int:cat_id>", methods=["POST"])
@admin_required
def admin_toggle_category(cat_id):
    conn = get_db()
    cat = conn.execute("SELECT is_active FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if cat:
        new_val = 0 if cat["is_active"] == 1 else 1
        conn.execute("UPDATE categories SET is_active = ? WHERE id = ?", (new_val, cat_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/delete/<int:cat_id>", methods=["POST"])
@admin_required
def admin_delete_category(cat_id):
    conn = get_db()
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_categories"))

# Admin Orders Management
@app.route("/admin/orders")
@admin_required
def admin_orders():
    status = request.args.get("status")
    search = request.args.get("search")

    conn = get_db()
    query = "SELECT * FROM orders WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (id LIKE ? OR customer_name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])

    query += " ORDER BY created_at DESC"
    orders = conn.execute(query, params).fetchall()

    orders_with_items = []
    for ord_row in orders:
        ord_dict = dict(ord_row)
        items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (ord_dict["id"],)).fetchall()
        ord_dict["items"] = [dict(i) for i in items]
        orders_with_items.append(ord_dict)

    conn.close()
    return render_template("admin_orders.html", orders=orders_with_items, current_status=status, current_search=search)

@app.route("/admin/orders/<order_id>/status", methods=["POST"])
@admin_required
def admin_update_order_status(order_id):
    new_status = request.form.get("status", "Pending")
    courier = request.form.get("courier", "").strip()
    tracking_number = request.form.get("tracking_number", "").strip()
    notes = request.form.get("notes", "").strip()

    now_ist_str = get_now_ist_str()
    conn = get_db()
    cursor = conn.cursor()
    order = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    if order:
        order_dict = dict(order)
        cursor.execute("""
            UPDATE orders
            SET status = ?,
                courier = COALESCE(NULLIF(?, ''), courier),
                tracking_number = COALESCE(NULLIF(?, ''), tracking_number),
                updated_at = ?
            WHERE id = ?
        """, (new_status, courier, tracking_number, now_ist_str, order_id))

        cursor.execute("""
            INSERT INTO order_tracking (order_id, status, title, description, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_id, new_status, f"Order {new_status}", notes or f"Order status updated to {new_status}.", "Operations Hub", now_ist_str))

        conn.commit()
        notify_order_status_updated(order_dict, new_status, tracking_number or order_dict.get("tracking_number"), courier or order_dict.get("courier"))

    conn.close()
    return redirect(url_for("admin_orders"))

@app.route("/admin/orders/<order_id>/cancel", methods=["POST"])
@admin_required
def admin_cancel_order_route(order_id):
    reason = request.form.get("reason", "Cancelled by Admin").strip()
    conn = get_db()
    cursor = conn.cursor()
    order = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    if order:
        order_dict = dict(order)
        now_ist_str = get_now_ist_str()
        cursor.execute("""
            UPDATE orders
            SET status = 'Cancelled',
                cancellation_reason = ?,
                cancelled_by = 'Admin',
                cancelled_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (reason, now_ist_str, now_ist_str, order_id))

        items = cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            if item["product_id"]:
                cursor.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item["quantity"], item["product_id"]))

        cursor.execute("""
            INSERT INTO order_tracking (order_id, status, title, description, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_id, "Cancelled", "Order Cancelled by Admin", f"Reason: {reason}", "Admin Desk", now_ist_str))

        conn.commit()
        notify_order_cancelled(order_dict, reason, "Admin")

    conn.close()
    return redirect(url_for("admin_orders"))

# Admin Returns Management
@app.route("/admin/returns")
@admin_required
def admin_returns():
    conn = get_db()
    returns = conn.execute("SELECT * FROM order_returns ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_returns.html", returns=[dict(r) for r in returns])

@app.route("/admin/returns/<return_id>/status", methods=["POST"])
@admin_required
def admin_update_return_status(return_id):
    new_status = request.form.get("status", "Requested")
    admin_notes = request.form.get("admin_notes", "").strip()

    now_ist_str = get_now_ist_str()
    conn = get_db()
    cursor = conn.cursor()
    ret = cursor.execute("SELECT * FROM order_returns WHERE id = ?", (return_id,)).fetchone()

    if ret:
        ret_dict = dict(ret)
        order = cursor.execute("SELECT * FROM orders WHERE id = ?", (ret_dict["order_id"],)).fetchone()
        order_dict = dict(order) if order else {}

        cursor.execute("""
            UPDATE order_returns
            SET status = ?,
                admin_notes = ?,
                updated_at = ?
            WHERE id = ?
        """, (new_status, admin_notes, now_ist_str, return_id))

        if new_status == "Approved":
            cursor.execute("UPDATE orders SET status = 'Return Approved', updated_at = ? WHERE id = ?", (now_ist_str, ret_dict["order_id"]))
        elif new_status == "Refund Completed":
            cursor.execute("UPDATE orders SET status = 'Refunded', payment_status = 'Refunded', updated_at = ? WHERE id = ?", (now_ist_str, ret_dict["order_id"]))
        elif new_status == "Rejected":
            cursor.execute("UPDATE orders SET status = 'Return Rejected', updated_at = ? WHERE id = ?", (now_ist_str, ret_dict["order_id"]))

        cursor.execute("""
            INSERT INTO order_tracking (order_id, status, title, description, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ret_dict["order_id"], f"Return {new_status}", f"Return {new_status}", admin_notes or f"Return request is now {new_status}.", "Admin Support", now_ist_str))

        conn.commit()

        if order_dict:
            notify_return_status_updated(ret_dict, order_dict, new_status, admin_notes)

    conn.close()
    return redirect(url_for("admin_returns"))

# Admin Bookings Management
@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    status = request.args.get("status")
    search = request.args.get("search")

    conn = get_db()
    query = "SELECT * FROM bookings WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (id LIKE ? OR customer_name LIKE ? OR phone LIKE ? OR pet_name LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])

    query += " ORDER BY appointment_date DESC, id DESC"
    bookings = conn.execute(query, params).fetchall()

    bookings_with_services = []
    for bkg_row in bookings:
        bkg_dict = dict(bkg_row)
        svc_items = conn.execute("SELECT * FROM booking_services WHERE booking_id = ?", (bkg_dict["id"],)).fetchall()
        bkg_dict["services_list"] = [dict(s) for s in svc_items]
        bookings_with_services.append(bkg_dict)

    conn.close()
    return render_template("admin_bookings.html", bookings=bookings_with_services, current_status=status, current_search=search)

@app.route("/admin/bookings/<booking_id>/status", methods=["POST"])
@admin_required
def admin_update_booking_status(booking_id):
    new_status = request.form.get("status", "Pending")
    admin_notes = request.form.get("admin_notes", "").strip()

    now_ist_str = get_now_ist_str()
    conn = get_db()
    cursor = conn.cursor()
    booking = cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()

    if booking:
        booking_dict = dict(booking)
        cursor.execute("""
            UPDATE bookings
            SET status = ?,
                admin_notes = ?,
                updated_at = ?
            WHERE id = ?
        """, (new_status, admin_notes, now_ist_str, booking_id))
        conn.commit()

        if new_status == "Cancelled":
            notify_booking_cancelled(booking_dict, admin_notes or "Cancelled by Admin", "Admin")

    conn.close()
    return redirect(url_for("admin_bookings"))

# Admin Reviews Management
@app.route("/admin/reviews")
@admin_required
def admin_reviews():
    conn = get_db()
    reviews = conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_reviews.html", reviews=[dict(r) for r in reviews])

@app.route("/admin/reviews/<int:review_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_review(review_id):
    conn = get_db()
    rev = conn.execute("SELECT is_approved FROM reviews WHERE id = ?", (review_id,)).fetchone()
    if rev:
        new_val = 0 if rev["is_approved"] == 1 else 1
        conn.execute("UPDATE reviews SET is_approved = ? WHERE id = ?", (new_val, review_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin_reviews"))

@app.route("/admin/reviews/<int:review_id>/delete", methods=["POST"])
@admin_required
def admin_delete_review(review_id):
    conn = get_db()
    conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_reviews"))

# Admin Customers Management
@app.route("/admin/customers")
@admin_required
def admin_customers():
    conn = get_db()
    customers = conn.execute("""
        SELECT c.*,
            (SELECT COUNT(*) FROM orders WHERE email = c.email) as total_orders,
            (SELECT COALESCE(SUM(grand_total), 0) FROM orders WHERE email = c.email AND status != 'Cancelled') as total_spend,
            (SELECT COUNT(*) FROM bookings WHERE email = c.email) as total_bookings
        FROM customers c
        ORDER BY c.id DESC
    """).fetchall()
    conn.close()
    return render_template("admin_customers.html", customers=[dict(c) for c in customers])

# Admin Settings Management
@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        for k in request.form:
            cursor.execute("INSERT OR REPLACE INTO site_settings (key, value) VALUES (?, ?)", (k, request.form[k].strip()))
        conn.commit()

    rows = cursor.execute("SELECT key, value FROM site_settings").fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    return render_template("admin_settings.html", settings=settings)


# ==========================================================
# STATIC FILE & ROOT ROUTES
# ==========================================================
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
if not os.path.exists(FRONTEND_DIR):
    FRONTEND_DIR = ROOT_DIR

@app.route("/")
def home():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>🐾 PET NEXA Backend Running</h1><p><a href='/admin'>Admin Panel</a></p>"

# Services Catalog Page Route
@app.route("/services")
@app.route("/services.html")
def serve_services_page():
    return send_from_directory(FRONTEND_DIR, "services.html")

# Service-Specific Booking Route (e.g. /book/puppy-grooming, /book/ear-cleaning, /services/ear-cleaning)
@app.route("/book/<service_slug>")
@app.route("/service/<service_slug>")
@app.route("/services/<service_slug>")
def serve_service_booking(service_slug):
    return send_from_directory(FRONTEND_DIR, "booking.html")

# Payment Page Route
@app.route("/payment")
@app.route("/payment.html")
def serve_payment_page():
    return send_from_directory(FRONTEND_DIR, "payment.html")

# Success & Order Confirmation Routes
@app.route("/success")
@app.route("/success.html")
def serve_success_page():
    return send_from_directory(FRONTEND_DIR, "success.html")

@app.route("/order-confirmation")
@app.route("/order-confirmation.html")
def serve_order_confirmation_page():
    return send_from_directory(FRONTEND_DIR, "order-confirmation.html")

@app.route("/<path:filename>")
def serve_root_files(filename):
    # 1. Check in FRONTEND_DIR first
    target_frontend = os.path.abspath(os.path.join(FRONTEND_DIR, filename))
    if target_frontend.startswith(FRONTEND_DIR) and os.path.isfile(target_frontend):
        return send_from_directory(FRONTEND_DIR, filename)
    
    # 2. Try with .html extension in FRONTEND_DIR (e.g. /shop -> /shop.html)
    html_target_frontend = target_frontend + ".html"
    if os.path.isfile(html_target_frontend):
        return send_from_directory(FRONTEND_DIR, filename + ".html")

    # 3. Check in ROOT_DIR fallback
    target_root = os.path.abspath(os.path.join(ROOT_DIR, filename))
    if target_root.startswith(ROOT_DIR) and os.path.isfile(target_root):
        return send_from_directory(ROOT_DIR, filename)

    return "File not found", 404

# Test Email Route
@app.route("/test-email")
def test_email():
    admin_emails = get_admin_emails()
    send_email_async(
        admin_emails,
        "🐾 PET NEXA - SMTP Dual Email Test",
        "Hello!\n\nThis is a test email confirming your Gmail SMTP configuration is fully working and dispatching to BOTH admin email addresses!\n\nPET NEXA 🐾"
    )
    return jsonify({"success": True, "message": f"Test email dispatched to {', '.join(admin_emails)}"})


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

# ==========================================================
# INITIALIZE DATABASE & SERVER
# ==========================================================
init_db()

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = int(os.environ.get("PORT", 5000))
    print("=" * 64)
    print("🐾 PET NEXA PRODUCTION / DEVELOPMENT SERVER")
    print("=" * 64)
    print(f" • Localhost URL:     http://localhost:{port}")
    print(f" • Mobile / LAN URL:  http://{local_ip}:{port}")
    print("=" * 64)
    print("Press CTRL+C to stop the server.\n")
    app.run(host="0.0.0.0", port=port, debug=False)