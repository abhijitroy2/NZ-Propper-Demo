# Railway Docker Build Fix

## Problem
Railway is trying to use Railpack/Nixpacks instead of Docker, causing build failures.

## Solution Options

### Option 1: Configure via Railway Dashboard (RECOMMENDED)

1. **Open Railway Dashboard:**
   ```bash
   railway open
   ```

2. **Go to your backend service:**
   - Click on your backend service
   - Go to **Settings** tab
   - Scroll to **Build** section

3. **Change Builder:**
   - Find **Builder** dropdown
   - Change from "Nixpacks" or "Railpack" to **"Dockerfile"**
   - Save changes

4. **Redeploy:**
   - Go to **Deployments** tab
   - Click **Redeploy** on the latest deployment
   - Or trigger a new deployment: `railway up`

### Option 2: Delete Procfile (if it exists)

The Procfile might be causing Railway to prefer buildpacks:

```bash
cd backend
# Backup first
cp Procfile Procfile.backup
# Remove it (Railway will use Dockerfile instead)
rm Procfile
railway up
```

### Option 3: Ensure Dockerfile is in Root

Make sure the Dockerfile is in the backend directory where you're running `railway up`:

```bash
cd backend
ls Dockerfile  # Should show the file
railway up
```

### Option 4: Use Railway CLI to Set Builder

Try explicitly setting the builder:

```bash
cd backend
railway variables set RAILWAY_BUILDER=DOCKERFILE
railway up
```

## Verification

After applying the fix:

1. **Check build logs:**
   ```bash
   railway logs
   ```
   - Should see "Building Docker image" instead of "Railpack" or "Nixpacks"

2. **Verify deployment:**
   ```bash
   railway domain
   curl https://your-backend.railway.app/api/health
   ```

## Most Reliable Method

**Use the Railway Dashboard** (Option 1) - This is the most reliable way to ensure Docker is used:
- Go to service settings
- Change builder to Dockerfile
- Save and redeploy

