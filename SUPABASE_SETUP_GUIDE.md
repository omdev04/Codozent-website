# 🚀 Codozent CMS: Production Supabase Setup Guide

This guide explains how to connect your **Supabase Cloud PostgreSQL Database** to the Codozent CMS so that:
- **₹0 Cost**: 100% Free Tier on both Supabase and Render.
- **Zero Data Loss**: Even if Render restarts, sleeps, or rebuilds, every blog, image, work item, and user remains permanently safe in Supabase.
- **24/7 Always Awake**: With UptimeRobot pinging `/api/health`, Render Free never goes to sleep.

---

## Step 1: Create a Free Supabase Project (2 Minutes)

1. Go to [https://supabase.com](https://supabase.com) and Sign In (or Sign Up with GitHub).
2. Click **"New Project"**.
3. Fill in the project details:
   - **Name**: `codozent-cms` (or any name you prefer)
   - **Database Password**: Choose a strong password and **save it safely**.
   - **Region**: Choose the region closest to your users or Render service (e.g. `US East`, `EU Frankfurt`, or `Singapore`).
   - **Pricing Plan**: Free Tier ($0/month - 500MB DB storage, unlimited API calls).
4. Click **"Create new project"** and wait ~60 seconds for Supabase to provision your PostgreSQL database.

---

## Step 2: Get Your Supabase Connection String (URI)

1. In your Supabase Dashboard, go to **Project Settings** (gear icon in the bottom-left sidebar) -> **Database**.
2. Scroll down to **"Connection string"**.
3. Click the **"URI"** tab.
4. Select **"Transaction"** mode (Port `6543`) — *Recommended for Render/cloud apps* (or Session mode on Port `5432`).
5. Copy the connection string. It will look like this:
   ```text
   postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
   ```
6. Replace `[YOUR-PASSWORD]` with the database password you chose in Step 1.

---

## Step 3: One-Click Migrate Your Local Data to Supabase

To copy all your existing admin user (`codozent.help@gmail.com`), homepage images, work case studies, blogs, and media assets from local SQLite into Supabase, simply run this command in your terminal:

```bash
python -m cms.migrate_to_supabase --url "postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres"
```

The script will automatically:
1. Create all 10 tables in Supabase with production PostgreSQL constraints.
2. Transfer all existing data.
3. Automatically align serial ID sequences so future inserts never have primary key collisions.

---

## Step 4: Configure Render.com Free Tier

When creating or configuring your backend web service on [Render.com](https://dashboard.render.com):

1. **Environment Variables**:
   In your Render Web Service settings, add the following under **Environment**:
   - `DATABASE_URL`: `postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres`
   - `ENVIRONMENT`: `production`
   - `ADMIN_EMAIL`: `codozent.help@gmail.com`
   - `CORS_ORIGINS`: `https://codozent.com,https://www.codozent.com`
   - `CLOUDINARY_CLOUD_NAME`: *(Your Cloudinary cloud name)*
   - `CLOUDINARY_API_KEY`: *(Your Cloudinary API key)*
   - `CLOUDINARY_API_SECRET`: *(Your Cloudinary API secret)*
   - `CMS_SECRET_KEY`: *(Click Generate or enter any 32+ character random string)*

2. **Deploy Service**:
   - Build Command: `pip install --upgrade pip && pip install -r requirements.txt`
   - Start Command: `uvicorn cms.server:app --host 0.0.0.0 --port $PORT`
   - Plan: **Free**

---

## Step 5: Prevent Render 15-Minute Sleep with UptimeRobot (Free)

Render Free web services spin down after 15 minutes of inactivity. To keep your API and Admin panel **instantly fast and 100% awake 24/7**:

1. Go to [https://uptimerobot.com](https://uptimerobot.com) and create a free account.
2. Click **"+ Add New Monitor"**.
3. Fill in:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `Codozent CMS API Health`
   - **URL (or IP)**: `https://your-render-app-name.onrender.com/api/health`
   - **Monitoring Interval**: Every `5 minutes` (or `10 minutes`)
4. Click **"Create Monitor"**.

UptimeRobot will ping your `/api/health` endpoint every 5 minutes. Render will recognize the active traffic and **never sleep**, keeping your CMS always warm and ready!

---

## Verification

You can verify the database connection at any time by visiting:
```text
https://your-render-app-name.onrender.com/api/health
```

Expected Response:
```json
{
  "status": "healthy",
  "service": "codozent-cms",
  "database": {
    "status": "ok",
    "engine": "supabase_postgresql"
  },
  "environment": "production",
  "timestamp": "2026-11-25T17:10:13.517992+00:00"
}
```
