# SignalScope AI — Deployment Guide

Deploy on **Vercel** (frontend) + **Render** (backend) + **Neon** (database) + **Upstash** (Redis).

---

## Prerequisites

1. GitHub account (to push code)
2. Vercel account (https://vercel.com — free)
3. Render account (https://render.com — free)
4. Neon account (https://console.neon.tech — free PostgreSQL)
5. Upstash account (https://upstash.com — free Redis)

---

## Step 1: Set Up Neon PostgreSQL

1. Go to https://console.neon.tech
2. Create a new project: `signalscope-ai`
3. Create a database: `signalscope`
4. Copy the **Connection String** (looks like: `postgresql://user:password@host/dbname`)
5. **Keep this secret** — you'll use it in Render and for local testing

---

## Step 2: Set Up Upstash Redis

1. Go to https://console.upstash.com
2. Create a Redis database: `signalscope-redis`
3. Copy the **REDIS_URL** (looks like: `redis://:password@host:port`)
4. **Keep this secret** — you'll use it in Render

---

## Step 3: Deploy Backend on Render

### Option A: Using Dashboard (Recommended for first-time)

1. Go to https://render.com/dashboard
2. Click **New +** → **Web Service**
3. Connect your GitHub repo
4. Fill in:
   - **Name**: `signalscope-api`
   - **Environment**: `Python 3`
   - **Build Command**: 
     ```
     pip install -r requirements.txt && alembic upgrade head
     ```
   - **Start Command**:
     ```
     uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
     ```

5. Add **Environment Variables**:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | Paste from Neon |
| `REDIS_URL` | Paste from Upstash |
| `FRONTEND_ORIGIN` | `https://your-vercel-domain.vercel.app` |
| `APP_BASE_URL` | `https://your-vercel-domain.vercel.app` |
| `CACHE_BACKEND` | `redis` |
| `REDIS_PREFIX` | `signalscope` |
| `STRICT_REAL_EMBEDDINGS` | `false` |
| `RUN_DB_MIGRATIONS_ON_START` | `true` |
| `LOG_FORMAT` | `json` |
| `LOG_LEVEL` | `INFO` |
| `RATE_LIMIT_PER_MINUTE` | `90` |
| `WEB_CONCURRENCY` | `4` |

6. Click **Create Web Service**
7. Wait for deployment (3-5 minutes)
8. Copy the **Backend URL** (e.g., `https://signalscope-api.onrender.com`)

### Option B: Using render.yaml (Automated)

1. Push your code with `render.yaml` to GitHub
2. Go to https://render.com/dashboard
3. Click **New +** → **Web Service**
4. Select "Use render.yaml"
5. Connect and deploy automatically

---

## Step 4: Deploy Frontend on Vercel

1. Go to https://vercel.com/dashboard
2. Click **Add New +** → **Project**
3. Import your GitHub repository
4. **Framework Preset**: Auto-detect (should find Next.js)
5. **Root Directory**: `./frontend`
6. Add **Environment Variables**:

| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_API_URL` | `https://signalscope-api.onrender.com` |

7. Click **Deploy**
8. Wait 2-3 minutes
9. Copy the **Frontend URL** (e.g., `https://signalscope-ai.vercel.app`)

---

## Step 5: Update Environment Variables

### On Render Backend:

1. Go to your Render service → **Environment**
2. Update:

| Key | Value |
|-----|-------|
| `FRONTEND_ORIGIN` | Your Vercel URL |
| `APP_BASE_URL` | Your Vercel URL |

3. Service will auto-redeploy

### On Vercel Frontend:

1. Go to Settings → **Environment Variables**
2. Update:

| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_API_URL` | Your Render backend URL |

3. Redeploy (click **Deployments** → **Redeploy**)

---

## Step 6: Test the Deployment

1. Open your Vercel frontend URL
2. Verify sign-up/login works
3. Test search functionality
4. Check `/health` endpoint: `https://signalscope-api.onrender.com/health`

---

## Monitoring & Debugging

### Vercel Frontend
- Logs: Vercel Dashboard → **Deployments** → **Logs**
- Real-time logs: `vercel logs --follow`

### Render Backend
- Logs: Render Dashboard → Service → **Logs**
- Tail logs: Click **Tail Logs** button

### Neon Database
- Logs: Neon Console → **Monitoring**
- Query editor: Neon Console → **SQL Editor**

### Upstash Redis
- Monitoring: Upstash Console → **Stats** & **Logs**

---

## Cost Breakdown (Monthly)

| Service | Free Tier | Notes |
|---------|-----------|-------|
| **Vercel** | $0 | Generous free tier |
| **Render** | $0* | Web Service sleeps after 15 min (OK for API) |
| **Neon** | $0* | 0.5GB storage, good for MVP |
| **Upstash** | $0* | 10K commands/day free |

*Free tiers sufficient for MVP. Upgrade as needed.

---

## Production Considerations

For production (once you have users):

1. **Render Web Service** → Upgrade to **Standard** ($7/month) to prevent sleep
2. **Neon** → Upgrade to **Pro** ($15/month) if exceeding 0.5GB
3. **Upstash** → Upgrade to **Pro** if exceeding 10K commands/day
4. **Vercel** → Usually free; upgrade if needed for performance

---

## Troubleshooting

### Backend fails to start

**Check:**
1. Migrations ran: `alembic upgrade head` in Build Command
2. All env vars set correctly
3. DATABASE_URL format: `postgresql://user:password@host/dbname`
4. REDIS_URL format: `redis://:password@host:port`

**View logs:**
```bash
# Render dashboard → Service → Logs
```

### Frontend can't reach backend

**Check:**
1. `NEXT_PUBLIC_API_URL` is set on Vercel
2. Backend is running (check Render logs)
3. CORS is enabled: Check backend logs for "CORS" errors
4. Network connectivity: Open browser DevTools → Network tab

### Database connection fails

**Check:**
1. DATABASE_URL is correct (copy-paste from Neon)
2. IP whitelist on Neon (usually auto-allows all)
3. Database name matches (should be `signalscope`)

---

## Rollback

If something breaks:

**Vercel**: 
- Go to **Deployments** → click previous version → **Promote to Production**

**Render**:
- Go to **Logs** → find last good deployment → **Deploy**

---

## Next Steps

1. Set up monitoring/alerts (Render, Vercel, Upstash dashboards)
2. Configure custom domain (both Vercel and Render support this)
3. Set up CI/CD GitHub Actions to auto-deploy on push
4. Monitor costs and scale as needed
