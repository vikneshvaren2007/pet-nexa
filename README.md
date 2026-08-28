# 🐾 PET NEXA — Professional Pet Care & E-Commerce Platform

A production-ready full-stack Flask web application providing comprehensive pet grooming bookings, multi-category pet shop e-commerce, live order & appointment tracking, customer portal, Razorpay test payment integration, dual admin email notifications, AI Pet Advisor (Google Gemini), and an interactive Admin Management Dashboard.

---

## 🚀 Render Live Deployment Quickstart

### Target Live URL
**`https://pet-nexa.onrender.com`**

### Prerequisites
1. Push your repository to **GitHub** (e.g. `https://github.com/your-username/pet-nexa`).
2. Sign in to [Render](https://render.com).

### Step-by-Step Render Setup
1. On your Render Dashboard, click **New +** -> **Web Service**.
2. Connect your GitHub repository: `pet-nexa`.
3. Configure the following service settings:
   - **Name**: `pet-nexa`
   - **Region**: Singapore / Oregon / Frankfurt (any preferred region)
   - **Branch**: `main` (or `master`)
   - **Root Directory**: *(leave blank — defaults to repo root)*
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app`
   - **Instance Type**: `Free`

4. Click **Advanced** -> **Add Environment Variable** and configure:
   | Key | Example Value | Description |
   | :--- | :--- | :--- |
   | `RESEND_API_KEY` | `your_resend_api_key_here` | Resend API key for cloud email delivery |
   | `RESEND_FROM` | `PET NEXA <onboarding@resend.dev>` | Verified Resend sender format |
   | `SECRET_KEY` | `pawzo-care-super-secret-key-2026` | Flask session encryption key |
   | `EMAIL_USER` | `your_email@gmail.com` | Gmail SMTP sender address (fallback) |
   | `EMAIL_PASSWORD` | `your_16_char_google_app_password` | Google App Password (fallback) |
   | `ADMIN_EMAIL` | `vikneshvaren2@gmail.com,karthikthanesh92@gmail.com` | Dual admin alert recipients |
   | `GEMINI_API_KEY` | `your_gemini_api_key_here` | Google Gemini AI Key |
   | `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model version |
   | `RAZORPAY_KEY_ID` | `rzp_test_pawzocare2026` | Razorpay Sandbox Key ID |
   | `RAZORPAY_KEY_SECRET` | `pawzosecretkey2026` | Razorpay Sandbox Secret |

5. Click **Deploy Web Service**.
6. Render will automatically build the service, install dependencies, initialize the database (`pawzo.db`), and make the site live at `https://pet-nexa.onrender.com`!

---

## 🛠️ Local Development

### Option A: Run via Batch Script
Double-click `start_server.bat` in Windows Explorer.

### Option B: Run via Terminal
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the application
python wsgi.py
# Server will run at http://localhost:5000
```

---

## 📁 Project Directory Structure

```text
PET NEXA/
├── frontend/                     # All Client-Side Files & Assets
│   ├── images/                   # Product & Pet Images, Doctor Photos, Logo, QR
│   ├── index.html                # Home Landing Page
│   ├── shop.html                 # Pet Food & Accessories E-Commerce
│   ├── cart.html                 # Cart & Checkout summary
│   ├── customer.html             # Customer Information Details
│   ├── payment.html              # Single Pay Now / Payment Selection Flow
│   ├── success.html              # Green Tick Order & Booking Confirmation
│   ├── booking.html              # Pet Grooming & Separate Bath Booking
│   ├── booking-track.html        # Booking Tracking & Rescheduling Portal
│   ├── track.html                # Live Order Tracking & Return Requests
│   ├── services.html             # Grooming Services Catalog
│   ├── ai.html                   # Google Gemini AI Pet Advisor
│   ├── doctor.html               # Pet Veterinary & Specialists Directory
│   ├── style.css, booking.css... # Modular Stylesheets
│   └── script.js, booking.js...  # Interactive Frontend Controllers
│
├── backend/                      # Server-Side Engine & Database
│   ├── templates/                # Jinja Admin Panel Templates
│   ├── static/                   # Admin CSS
│   ├── pawzo.db                  # Primary SQLite Database (IST Timestamps)
│   ├── app.py                    # Flask REST API & Admin Controllers
│   ├── .env                      # API Keys & Secrets Configuration
│   └── requirements.txt          # Python Dependencies
│
├── wsgi.py                       # Production WSGI Entry Point (Render)
├── Procfile                      # Render / Gunicorn Web Process Spec
├── render.yaml                   # Infrastructure-as-Code Configuration
├── start_server.bat              # One-Click Local Development Server
└── requirements.txt              # Root Dependencies
```

---

## 🧭 Key Features & Live Routes

- **Homepage**: `/` or `/index.html`
- **Services Catalog**: `/services` or `/services.html`
- **Service Booking**: `/book/puppy-grooming`, `/booking.html`
- **Booking Management & Rescheduling**: `/booking-track.html`
- **Pet Shop E-Commerce**: `/shop.html`
- **Shopping Cart & Checkout**: `/cart.html` -> `/customer.html` -> `/payment.html`
- **Live Order Tracking**: `/track.html`
- **AI Pet Advisor**: `/ai.html`
- **Admin Control Panel**: `/admin`
  - Default Admin Credentials: `admin` / `Admin@12345`
  - Manage Orders, Returns, Bookings, Products, Categories, Reviews, and Site Settings.
