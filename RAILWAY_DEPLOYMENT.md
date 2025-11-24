# Railway Deployment Guide

## Overview
This project consists of two services:
1. **Backend** - FastAPI application (Python)
2. **Frontend** - React application (Node.js/nginx)

## Prerequisites
- Railway CLI installed and logged in
- Git repository connected to Railway

## Deployment Steps

### 1. Create Railway Project
```bash
railway init
```

### 2. Deploy Backend Service

#### Option A: Using Railway Dashboard
1. Go to Railway dashboard
2. Click "New Service"
3. Select "GitHub Repo" or "Deploy from GitHub repo"
4. Select this repository
5. Set root directory to `backend`
6. Railway will auto-detect the Dockerfile
7. Set environment variable: `PORT` (Railway sets this automatically)

#### Option B: Using Railway CLI
```bash
railway link
railway up --service backend
```

### 3. Deploy Frontend Service

1. Create a new service in Railway dashboard
2. Set root directory to `frontend`
3. Railway will auto-detect the Dockerfile
4. Set environment variable:
   - `BACKEND_URL` = Your backend service's public URL (e.g., `https://your-backend.railway.app`)

### 4. Environment Variables

#### Backend Service
- `PORT` - Automatically set by Railway (default: 8000)

#### Frontend Service
- `BACKEND_URL` - Backend service public URL (required)
  - Example: `https://your-backend-service.railway.app`
  - This will be used to proxy API requests

### 5. Get Service URLs

After deployment, Railway will provide:
- Backend URL: `https://your-backend.railway.app`
- Frontend URL: `https://your-frontend.railway.app`

### 6. Update Frontend Environment Variable

Once backend is deployed:
1. Go to Frontend service settings
2. Add/Update `BACKEND_URL` environment variable
3. Redeploy frontend service

## Verification

1. Check backend health:
   ```bash
   curl https://your-backend.railway.app/api/health
   ```

2. Visit frontend URL in browser
3. Test file upload functionality

## Troubleshooting

### Backend Issues
- Check logs: `railway logs --service backend`
- Verify PORT environment variable is set
- Check that requirements.txt is up to date

### Frontend Issues
- Check logs: `railway logs --service frontend`
- Verify BACKEND_URL is set correctly
- Check nginx configuration
- Verify build completed successfully

### CORS Issues
- Backend CORS is configured to allow all origins (`allow_origins=["*"]`)
- If issues persist, update CORS settings in `backend/app/main.py`

## Notes

- Railway automatically provides `$PORT` environment variable
- Frontend uses nginx to serve static files and proxy API requests
- Both services can be deployed from the same repository using different root directories

