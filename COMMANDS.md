# Command Reference — Development & Deployment

## 🏠 Local Development

### Setup (one-time)
```bash
# Clone repo
git clone https://github.com/yourusername/AISearchEngine.git
cd AISearchEngine

# Create Python venv
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy env template
cp .env.example .env
# Edit .env with your local values (API keys optional)

# Run migrations (creates database schema)
python -m alembic upgrade head

# Start backend
uvicorn backend.app.main:app --reload --port 8000

# In another terminal: Start frontend
cd frontend
npm install
npm run dev
```

**Access:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

---

### Daily Development
```bash
# Activate venv
source venv/bin/activate  # or `venv\Scripts\activate`

# Run tests
python -m pytest tests/ -v

# Start backend
uvicorn backend.app.main:app --reload --port 8000

# Start frontend (different terminal)
cd frontend && npm run dev

# Check types
cd frontend && npm run typecheck

# Format code
cd frontend && npm run format
```

---

## 🚀 Deployment (Vercel + Render + Neon + Upstash)

### Step 1: Prepare for Deployment

```bash
# Commit all changes
git add .
git commit -m "Ready for production deployment"

# Push to GitHub
git push origin main
```

### Step 2: Create Services (Web Dashboard)

**Neon PostgreSQL** (https://console.neon.tech):
```bash
# Web dashboard only — copy CONNECTION STRING
# Format: postgresql://user:password@host/dbname
```

**Upstash Redis** (https://console.upstash.com):
```bash
# Web dashboard only — copy REDIS_URL
# Format: redis://:password@host:port
```

**Render Backend** (https://dashboard.render.com):
```bash
# Web dashboard — create Web Service
# Repository: Your GitHub repo
# Build Command: pip install -r requirements.txt && python -m alembic upgrade head
# Start Command: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --workers 4

# Environment Variables:
# DATABASE_URL=<from Neon>
# REDIS_URL=<from Upstash>
# FRONTEND_ORIGIN=https://yourapp.vercel.app
# CACHE_BACKEND=redis
# RUN_DB_MIGRATIONS_ON_START=true
# LOG_FORMAT=json
```

**Vercel Frontend** (https://vercel.com/new):
```bash
# Web dashboard — import Git repository
# Framework: Next.js
# Root Directory: ./frontend

# Environment Variables:
# NEXT_PUBLIC_API_URL=https://your-render-backend.onrender.com
```

---

## 🛠️ Render CLI Commands (Alternative to Web Dashboard)

### Install Render CLI
```bash
# macOS
brew install render-cli

# Linux
curl -fsSL https://install.render.com/linux | sh

# Windows (PowerShell)
iwr https://install.render.com/windows -OutFile render.exe
```

### Login to Render
```bash
render login
# Follow prompts to authenticate with your Render account
```

### Deploy Backend with render.yaml
```bash
# This will use render.yaml configuration automatically
render deploy

# Or trigger deploy for specific service
render deploy --service signalscope-api

# Check deployment status
render logs --service signalscope-api --follow
```

### View Logs
```bash
# Real-time logs
render logs --service signalscope-api --follow

# Last 100 lines
render logs --service signalscope-api --lines 100

# Specific time range
render logs --service signalscope-api --tail 50
```

### Manage Environment Variables
```bash
# List variables
render env --service signalscope-api list

# Set variable
render env --service signalscope-api set DATABASE_URL="postgresql://..."

# Update multiple
render env --service signalscope-api set \
  DATABASE_URL="postgresql://..." \
  REDIS_URL="redis://..." \
  FRONTEND_ORIGIN="https://..."
```

### Check Service Status
```bash
# List all services
render services list

# Get service details
render services get --service signalscope-api

# Check health
render services health --service signalscope-api
```

### Scale Service
```bash
# Scale to 2 instances (paid plan only)
render services scale --service signalscope-api --num 2

# View metrics
render metrics --service signalscope-api
```

---

## 🔍 Testing & Debugging

### Backend Tests
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_auth.py -v

# Run with coverage
python -m pytest tests/ --cov=backend

# Run only failed tests
python -m pytest tests/ --lf

# Stop on first failure
python -m pytest tests/ -x
```

### Frontend Tests
```bash
cd frontend

# Run Jest tests
npm test

# Run specific test file
npm test -- AuthPanel.test.tsx

# Watch mode
npm test -- --watch

# Coverage
npm test -- --coverage

# TypeScript check
npm run typecheck

# Lint
npm run lint

# Format code
npm run format
```

### Local Database
```bash
# Connect to local SQLite
sqlite3 data/retriever.db

# View tables
.tables

# Check schema
.schema auth_sessions

# Query data
SELECT * FROM auth_users LIMIT 5;

# Exit
.quit
```

### Production Database (Neon)
```bash
# Install psql if needed
# macOS: brew install postgresql
# Ubuntu: sudo apt-get install postgresql-client
# Windows: https://www.postgresql.org/download/windows/

# Connect to Neon database
psql "postgresql://user:password@host/signalscope"

# View tables
\dt

# Query data
SELECT * FROM auth_users;

# Exit
\q
```

### Test API Endpoints
```bash
# Local
curl http://localhost:8000/health

# Production
curl https://your-render-backend.onrender.com/health

# With auth
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-render-backend.onrender.com/v1/me/profile

# POST request with JSON
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"Password123"}'
```

---

## 📦 Git & GitHub

### Commit & Push
```bash
# Stage all changes
git add .

# Commit with message
git commit -m "Add deployment configs"

# Push to main
git push origin main

# Check status
git status

# View commits
git log --oneline -10
```

### Create Pull Request (if using branches)
```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes and commit
git add .
git commit -m "Implement new feature"

# Push branch
git push origin feature/new-feature

# Create PR on GitHub (web dashboard)
# https://github.com/yourusername/AISearchEngine/pull/new/feature/new-feature
```

---

## 🔐 Secrets Management

### Local (.env file)
```bash
# Copy example
cp .env.example .env

# Edit with your values
nano .env  # or your editor

# Never commit
git add .gitignore  # .env is already in .gitignore
git push
```

### Render Environment Variables
```bash
# Via CLI
render env --service signalscope-api set KEY=VALUE

# Via Web Dashboard
# Service → Settings → Environment → Add Environment Variable

# DO NOT put secrets in render.yaml (it's in git)
# Use dashboard for: API keys, passwords, tokens
```

### Vercel Environment Variables
```bash
# Via Web Dashboard
# Project Settings → Environment Variables → Add

# For preview/production
# NEXT_PUBLIC_API_URL (public, safe to expose)
# Other secrets in .env.local (not in git)
```

---

## 🚨 Troubleshooting Commands

### Backend Won't Start
```bash
# Check logs
render logs --service signalscope-api --follow

# Verify dependencies
pip list | grep -E "fastapi|uvicorn|psycopg"

# Test migration locally
python -m alembic upgrade head

# Run migrations step-by-step
python -m alembic current
python -m alembic heads
python -m alembic upgrade head
```

### Frontend Won't Build
```bash
cd frontend

# Clear cache
rm -rf .next node_modules package-lock.json
npm install

# Check TypeScript
npm run typecheck

# Build locally
npm run build

# Run locally
npm run dev
```

### Database Connection Issues
```bash
# Test PostgreSQL connection
psql "postgresql://user:pass@host/dbname" -c "SELECT 1"

# Test Redis connection
redis-cli -u redis://:password@host:port ping

# Check environment variables
echo $DATABASE_URL
echo $REDIS_URL
```

---

## 📊 Monitoring & Logs

### Real-time Logs
```bash
# Backend logs
render logs --service signalscope-api --follow

# Frontend logs (Vercel)
vercel logs --follow

# Specific pod/instance
render logs --service signalscope-api --instance=1
```

### Historical Logs
```bash
# Last 500 lines
render logs --service signalscope-api --lines 500

# Last hour
render logs --service signalscope-api --since 1h

# Specific time range
render logs --service signalscope-api --since "2026-06-01 10:00:00" --until "2026-06-01 11:00:00"
```

---

## 🎯 Quick Deploy Checklist

```bash
# 1. Test locally
python -m pytest tests/ -v
cd frontend && npm test

# 2. Commit & push
git add .
git commit -m "Final fixes before deploy"
git push origin main

# 3. Deploy via dashboards:
#    - Render: Auto-deploys from main (if connected)
#    - Vercel: Auto-deploys from main (if connected)

# 4. Verify
curl https://your-backend.onrender.com/health
curl https://your-frontend.vercel.app/

# 5. Monitor
render logs --service signalscope-api --follow
```
