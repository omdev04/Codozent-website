# 🚀 Codozent Technologies: 100% Cloudflare Edge Worker Deployment Guide

This guide explains how your production website and CMS run entirely on **Cloudflare Edge Workers + Supabase REST API**:
- **0ms Cold Starts**: Never goes to sleep (unlike free VMs like Render).
- **Unlimited Scalability & Global CDN**: Served from 330+ Cloudflare edge locations worldwide.
- **Edge Server-Side Rendering (SSR)**: Dynamic live content rendered directly at the edge via Cloudflare `HTMLRewriter`.
- **Pure Cloudflare Hosting**: No Python backend server needed in production; all authentication, APIs, and CMS logic are executed inside `_worker.js`.
- **Zero Secrets on GitHub**: All credentials are provided exclusively via Cloudflare Environment Variables & Secrets.

---

## 🔑 The 5 Environment Variables Needed in Cloudflare

You ONLY need to add these **5 variables** in Cloudflare. No other variables are required!

| Variable Name | Type | Example / Value | Where to find it / Description |
|---|---|---|---|
| `SUPABASE_URL` | Plain text | `https://[YOUR-PROJECT-REF].supabase.co` | From your Supabase Dashboard -> **Project Settings** -> **API** -> **Project URL** |
| `SUPABASE_KEY` | Secret | `eyJhbGciOi...` | From Supabase Dashboard -> **Project Settings** -> **API** -> `service_role` secret key (recommended) or `anon` public key |
| `ADMIN_EMAIL` | Plain text | `codozent.help@gmail.com` | The email you want to use to log in to the admin panel |
| `ADMIN_PASSWORD` | Secret | `[YOUR-STRONG-PASSWORD]` | The password you want to use to log in to the admin panel |
| `CMS_SECRET_KEY` | Secret | `[YOUR-32-CHAR-RANDOM-SECRET-STRING]` | Any random 32+ character string used to encrypt JWT login sessions |

> [!IMPORTANT]
> **No `DATABASE_URL` is needed!**
> Cloudflare Workers connect directly to Supabase via lightweight HTTPS REST APIs over port 443, eliminating database connection pooling issues and timeout errors.

---

## 🛠️ Step-by-Step Cloudflare Configuration

### Step 1: Open Your Worker in Cloudflare Dashboard
1. Log in to your [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. In the left navigation menu, click **Workers & Pages**.
3. Click on your project: **`codozent-website`**.

---

### Step 2: Add Environment Variables & Secrets
1. Inside your `codozent-website` project, click on the **Settings** tab.
2. Select **Variables and Secrets** from the sub-menu.
3. Click **Add** (or **Add Variable**) for each of the 5 variables:
   - Name: `SUPABASE_URL` | Value: `https://[YOUR-PROJECT-REF].supabase.co` | Click **Save**
   - Name: `SUPABASE_KEY` | Value: *(Paste your Supabase service_role key)* | Click **Encrypt** -> Click **Save**
   - Name: `ADMIN_EMAIL` | Value: `codozent.help@gmail.com` | Click **Save**
   - Name: `ADMIN_PASSWORD` | Value: *(Your chosen admin password)* | Click **Encrypt** -> Click **Save**
   - Name: `CMS_SECRET_KEY` | Value: *(32+ character random string)* | Click **Encrypt** -> Click **Save**
4. If there is a **Deploy** or **Save and Deploy** button at the bottom, click it to activate your new variables.

---

### Step 3: Connect Your Custom Domain (`codozent.com`)
1. In the same project under **Settings**, click **Domains & Routes**.
2. Click **Add** -> select **Custom Domain**.
3. Type: `codozent.com` and click **Add Custom Domain**.
4. Repeat to add: `www.codozent.com`.
5. Cloudflare will automatically configure the SSL certificate and route all traffic to your worker.

---

### Step 4: Verify Your Live Edge Worker
1. **Health & Configuration Check:**
   Open in your browser:
   ```text
   https://codozent.com/api/health
   ```
   You will receive a real-time diagnostics response confirming:
   ```json
   {
     "status": "healthy",
     "service": "Codozent Cloudflare Edge Worker",
     "config": {
       "SUPABASE_URL": "CONFIGURED",
       "SUPABASE_KEY": "CONFIGURED",
       "ADMIN_EMAIL": "CONFIGURED",
       "ADMIN_PASSWORD": "CONFIGURED",
       "CMS_SECRET_KEY": "CONFIGURED"
     },
     "database_status": "CONNECTED"
   }
   ```
2. **Access Admin Panel:**
   Open:
   ```text
   https://codozent.com/admin
   ```
   - It will automatically redirect to `/admin/login` if you are not signed in.
   - Enter your `ADMIN_EMAIL` (`codozent.help@gmail.com`) and your `ADMIN_PASSWORD`.
   - You will be logged into the Codozent Admin Dashboard (`https://codozent.com/admin`).

3. **Verify Admin-to-Frontend Sync:**
   - In the Admin Panel, go to **Video Section** or **Homepage Images**.
   - Make a change (e.g. toggle video or update alt text) and click **Save**.
   - Open `https://codozent.com` in an incognito window: your changes are immediately live on the homepage without needing a site rebuild or delay!

---

## 🔒 Security Best Practice: Rotate Supabase Database Password

Because older git commit attempts had strings exposed in previous commits prior to our history squash, perform this 1-minute rotation in Supabase:
1. Go to [Supabase Dashboard](https://supabase.com/dashboard) -> Select your project (`mgpbwahtkyrfxydovrwu`).
2. Go to **Project Settings** -> **Database**.
3. Scroll to **Database password** and click **Reset Database Password**.
4. Choose a fresh new strong password.
5. Your Cloudflare Worker uses `SUPABASE_KEY` (API REST key), so resetting the PostgreSQL database password will **NOT** affect your Cloudflare website or CMS!
