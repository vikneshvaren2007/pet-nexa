# 🚀 PET NEXA — Render Step-by-Step Deployment Guide

Follow these simple steps to deploy your PET NEXA Flask project to Render with zero errors:

---

## 1. Commit and Push to GitHub

In your local terminal / Git client, commit all your files and push them to your GitHub repository:

```bash
git add .
git commit -m "Configure PET NEXA for Render deployment"
git push origin main
```

---

## 2. Create a New Web Service on Render

1. Log in to your [Render Dashboard](https://dashboard.render.com/).
2. Click the blue **New +** button in the top right corner.
3. Select **Web Service**.
4. Choose **Build and deploy from a Git repository**.
5. Connect your GitHub account and select your **PET NEXA** repository.

---

## 3. Configure the Service Settings

Fill in the settings form as follows:

| Field | Value |
| :--- | :--- |
| **Name** | `pet-nexa` *(or your custom name)* |
| **Language / Runtime** | `Python 3` |
| **Region** | `Singapore` *(recommended for India/Asia)* or `Oregon` |
| **Branch** | `main` |
| **Root Directory** | *(leave completely empty)* |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn wsgi:app` |
| **Plan Type** | `Free` |

---

## 4. Add Environment Variables

Scroll down to the **Environment Variables** section and add the following keys:

1. `SECRET_KEY` = `pawzo-care-super-secret-key-2026`
2. `EMAIL_USER` = `your_email@gmail.com`
3. `EMAIL_PASSWORD` = `your_16_char_google_app_password`
4. `ADMIN_EMAIL` = `your_admin_email@gmail.com`
5. `GEMINI_API_KEY` = `your_gemini_developer_key_here`
6. `GEMINI_MODEL` = `gemini-2.5-flash`
7. `RAZORPAY_KEY_ID` = `rzp_test_pawzocare2026`
8. `RAZORPAY_KEY_SECRET` = `pawzosecretkey2026`
9. `BASE_URL` = `https://pet-nexa.onrender.com` *(optional: Render provides RENDER_EXTERNAL_URL automatically)*

---

## 5. Health Check Path (Optional)

In the **Advanced** tab:
- **Health Check Path**: `/api/health`

---

## 6. Click "Deploy Web Service"

- Render will fetch your repository, install packages using `pip install -r requirements.txt`, start the WSGI server with Gunicorn, and initialize the SQLite database `pawzo.db`.
- Once the status changes to **Live**, open your link:
  👉 **`https://pet-nexa.onrender.com`**

---

## 7. Testing Your Live Website

Once deployed, you can verify everything:
1. **Homepage & Catalog**: Visit `https://pet-nexa.onrender.com` to see the hero slider, services, featured products, and live reviews.
2. **Book a Service**: Visit `/booking.html` or click any service card to book an appointment. Check your email for the confirmation link.
3. **Shop & Order**: Add items to cart from `/shop.html`, proceed to checkout `/customer.html`, and pay via `/payment.html`.
4. **Order Tracking**: Track using `/track.html?id=ORD-...`
5. **AI Pet Advisor**: Open `/ai.html` to chat with the Gemini AI model.
6. **Admin Dashboard**: Visit `https://pet-nexa.onrender.com/admin` (Username: `admin`, Password: `Admin@12345`).
