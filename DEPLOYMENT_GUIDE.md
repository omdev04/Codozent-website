# 🚀 Codozent Production Deployment Guide (100% Free Hybrid Architecture)

This guide takes you step-by-step from code to a live production deployment:
- **Database**: Supabase PostgreSQL (Already migrated & active! ✅)
- **Backend API & Admin Panel**: Render.com (Free Tier)
- **Public Website Frontend**: Cloudflare Pages (Free Tier - Unlimited Bandwidth)
- **Images & Media**: Cloudinary CDN
- **24/7 Always Awake**: UptimeRobot (Free ping monitor)

---

## Step 1: Push Your Code to GitHub (2 Minutes)

Open your terminal in `D:\luminos` and run:

```bash
# 1. Initialize git
git init

# 2. Add all files (.gitignore automatically protects your .env and credentials)
git add .

# 3. Commit
git commit -m "feat: production codozent website with pure supabase backend"

# 4. Rename main branch
git branch -M main

# 5. Connect to your GitHub repository (replace with your repo URL)
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY_NAME.git

# 6. Push code
git push -u origin main
```

---

## Step 2: Deploy Backend to Render.com (Free Tier)

1. Go to [https://dashboard.render.com](https://dashboard.render.com) and log in.
2. Click **"New +"** (top-right) -> select **"Web Service"**.
3. Choose **"Build and deploy from a Git repository"** and connect your GitHub repo.
4. Fill in the settings:
   - **Name**: `codozent-backend` (or any name you choose)
   - **Region**: Choose closest to you (e.g. `Singapore` or `Oregon`)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install --upgrade pip && pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn cms.server:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type**: Select **"Free"** ($0/month)

5. Scroll down to **"Environment Variables"** and click **"Add Environment Variable"**:

| Key | Value | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres` | Your live Supabase connection string |
| `ENVIRONMENT` | `production` | Production mode |
| `ADMIN_EMAIL` | `codozent.help@gmail.com` | Verified admin email |
| `ADMIN_INITIAL_PASSWORD` | *(Your admin password)* | Admin password |
| `CMS_SECRET_KEY` | *(Click "Generate" or type 32 random letters)* | Session encryption key |
| `CORS_ORIGINS` | `https://codozent.com,https://www.codozent.com` | Allowed frontend domains |
| `CLOUDINARY_CLOUD_NAME` | *(Your Cloudinary cloud name)* | From your Cloudinary dashboard |
| `CLOUDINARY_API_KEY` | *(Your Cloudinary API key)* | From your Cloudinary dashboard |
| `CLOUDINARY_API_SECRET` | *(Your Cloudinary API secret)* | From your Cloudinary dashboard |

6. Click **"Create Web Service"**.
7. Wait ~2-3 minutes for Render to build and deploy. Once finished, Render will give you a public URL like:
   ```text
   https://codozent-backend.onrender.com
   ```
8. **Verify Backend Health**: Open in your browser:
   `https://codozent-backend.onrender.com/api/health`
   You should see:
   `{"status": "healthy", "service": "codozent-cms", "database": {"status": "ok", "engine": "supabase_postgresql"}}`

---

## Step 3: Connect Cloudflare Pages Proxy Rule

Once you have your Render URL (e.g., `https://codozent-backend.onrender.com`):

Open your local file `_redirects` and update line 9-11 with your Render URL:
```text
/api/*   https://codozent-backend.onrender.com/api/:splat   200
/admin   https://codozent-backend.onrender.com/admin        200
/admin/* https://codozent-backend.onrender.com/admin/:splat 200
```
Commit and push this change to GitHub:
```bash
git add _redirects
git commit -m "chore: point cloudflare proxy to render backend"
git push
```

---

## Step 4: Deploy Frontend to Cloudflare Pages (3 Minutes)

1. Go to [https://dash.cloudflare.com](https://dash.cloudflare.com) and log in.
2. In the left menu, click **Workers & Pages** -> **Overview** -> **Create application**.
3. Select the **"Pages"** tab -> click **"Connect to Git"**.
4. Select your GitHub repository.
5. In **Set up builds and deployments**:
   - **Project name**: `codozent` (or `codozent-frontend`)
   - **Production branch**: `main`
   - **Framework preset**: `None`
   - **Build command**: *(Leave blank - pure static HTML/CSS/JS)*
   - **Build output directory**: `.` *(single dot, meaning root directory)*
6. Click **"Save and Deploy"**.
7. Cloudflare Pages will deploy your website in less than 30 seconds! It will give you a live URL like:
   ```text
   https://codozent.pages.dev
   ```

---

## Step 5: Setup Custom Domain (e.g., codozent.com)

In your Cloudflare Pages dashboard:
1. Go to **Custom domains** tab -> click **"Set up a custom domain"**.
2. Enter `codozent.com` and `www.codozent.com`.
3. Cloudflare will automatically configure the SSL certificate and DNS.
4. Now your website will load on `https://codozent.com` and your admin panel will be at `https://codozent.com/admin`!

---

## Step 6: Keep Render 24/7 Awake with UptimeRobot (Free)

Render Free web services sleep after 15 minutes of inactivity. To keep your API instantly fast 24/7 without ever sleeping:

1. Go to [https://uptimerobot.com](https://uptimerobot.com) and create a free account.
2. Click **"+ Add New Monitor"**.
3. Choose:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `Codozent Backend API`
   - **URL**: `https://codozent-backend.onrender.com/api/health`
   - **Monitoring Interval**: `5 minutes`
4. Click **"Create Monitor"**.

Done! UptimeRobot will ping your backend every 5 minutes. Render will see active traffic and will **never sleep**!
