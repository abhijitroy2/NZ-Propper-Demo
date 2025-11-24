# Railway Deployment Steps - CLI Guide

## Step 1: Initialize or Link Railway Project

### Option A: Create a New Project
```bash
railway init
```
- This will prompt you to create a new project
- Enter a project name (e.g., "nz-propper")
- This creates a new Railway project and links it to your current directory

### Option B: Link to Existing Project
```bash
railway link
```
- This will show a list of your existing Railway projects
- Select the project you want to use
- Or provide project ID: `railway link <project-id>`

---

## Step 2: Check Project Status
```bash
railway status
```
- Verify the project is linked correctly
- Shows current project and environment info

---

## Step 3: Deploy Backend Service

### 3a. Navigate to Backend Directory
```bash
cd backend
```

### 3b. Link Backend Service (if not already linked)
```bash
railway service
```
- Select "Create a new service" or link to existing backend service
- Name it something like "backend" or "api"

### 3c. Check Variables
```bash
railway variables
```
- Verify `PORT` is set (Railway sets this automatically)
- You can also check in Railway dashboard

### 3d. Deploy Backend
```bash
railway up
```
- This will build and deploy the backend service
- Railway will detect the Dockerfile automatically
- Wait for deployment to complete

### 3e. Get Backend URL
```bash
railway domain
```
- This shows/generates the public domain for your backend
- Copy this URL (e.g., `https://your-backend.railway.app`)
- You'll need this for the frontend `BACKEND_URL` variable

### 3f. Verify Backend Health
```bash
curl https://your-backend.railway.app/api/health
```
- Or visit the URL in your browser
- Should return: `{"status":"healthy","service":"NZ PROPPER API"}`

---

## Step 4: Deploy Frontend Service

### 4a. Navigate to Frontend Directory
```bash
cd ../frontend
```

### 4b. Link Frontend Service
```bash
railway service
```
- Select "Create a new service" or link to existing frontend service
- Name it something like "frontend" or "web"

### 4c. Set Backend URL Environment Variable
```bash
railway variables
```
- Check current variables
- Add `BACKEND_URL` variable:
```bash
railway variables set BACKEND_URL=https://your-backend.railway.app
```
- Replace `your-backend.railway.app` with your actual backend domain from Step 3e

### 4d. Deploy Frontend
```bash
railway up
```
- This will build and deploy the frontend service
- Railway will detect the Dockerfile automatically
- Wait for deployment to complete

### 4e. Get Frontend URL
```bash
railway domain
```
- This shows/generates the public domain for your frontend
- Copy this URL (e.g., `https://your-frontend.railway.app`)

---

## Step 5: Verify Deployment

### Check Backend Logs
```bash
cd ../backend
railway logs
```
- Look for any errors or warnings
- Should see uvicorn starting successfully

### Check Frontend Logs
```bash
cd ../frontend
railway logs
```
- Look for any errors or warnings
- Should see nginx starting successfully

### Test the Application
1. Visit your frontend URL in a browser
2. Try uploading a CSV file
3. Verify the API connection works

---

## Useful Commands Reference

### View All Variables
```bash
railway variables
```

### Set a Variable
```bash
railway variables set VARIABLE_NAME=value
```

### View Logs
```bash
railway logs
```

### View Logs (Follow Mode)
```bash
railway logs --follow
```

### Open Railway Dashboard
```bash
railway open
```

### Check Deployment Status
```bash
railway status
```

### Redeploy Latest
```bash
railway redeploy
```

---

## Troubleshooting

### If Backend Fails to Start
- Check logs: `railway logs`
- Verify PORT is set: `railway variables`
- Check Dockerfile is correct

### If Frontend Can't Connect to Backend
- Verify BACKEND_URL is set correctly: `railway variables`
- Check backend is running: `curl https://your-backend.railway.app/api/health`
- Check CORS settings in backend (should allow all origins)

### If Services Aren't Showing Up
- Make sure you're in the correct directory
- Check service is linked: `railway service`
- Verify project is linked: `railway status`

---

## Quick Reference: Full Deployment Sequence

```bash
# 1. Initialize project (if new)
railway init

# 2. Deploy backend
cd backend
railway service  # Create/link backend service
railway up
railway domain   # Copy backend URL

# 3. Deploy frontend
cd ../frontend
railway service  # Create/link frontend service
railway variables set BACKEND_URL=https://your-backend.railway.app
railway up
railway domain   # Copy frontend URL

# 4. Verify
railway logs     # Check both services
```

