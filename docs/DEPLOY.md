# Production Deployment Checklist: NyaySetu

This step-by-step checklist is written for a non-expert. Follow the numbered steps in exact order to deploy the backend on Render and the frontend on Vercel.

---

## Deployment Order Overview

1. **Deploy Backend on Render First**: Generates your live API URL and initializes persistent storage.
2. **Verify Backend Health**: Verify the `/health` and `/dashboard` endpoints return HTTP 200.
3. **Deploy Frontend on Vercel Second**: Uses the Render API URL as `VITE_API_URL`.
4. **Update CORS on Render**: Restrict `ALLOWED_ORIGINS` to your new Vercel domain.
5. **Verify Live Web App**: Test ingestion, ledger, and judgment views in browser.

---

## Step 1: Deploy Backend on Render

1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click the blue **New +** button in the top right, then select **Web Service**.
3. Choose **Build and deploy from a Git repository** and select the `NyaySetu` repository.
4. Fill in the service configuration:
   - **Name**: `nyaysetu-api`
   - **Region**: Choose `Singapore` or `Frankfurt` (closest to your users).
   - **Branch**: `main`
   - **Runtime**: Select **Docker** (uses repository `Dockerfile`).
5. Scroll down to **Disks** and click **Add Disk**:
   - **Name**: `radar-data`
   - **Mount Path**: `/data`
   - **Size**: `1 GB` (or default minimum).
6. Scroll down to **Environment Variables** and add the following keys (paste variable names only, fill in your own values):
   - `GEMINI_API_KEY`: *(paste your Google Gemini API key)*
   - `GEMINI_MODEL`: `gemini-2.5-flash`
   - `GEMINI_FALLBACK_MODEL`: `gemini-1.5-flash`
   - `DATABASE_URL`: `sqlite:////data/compliance_radar.db`
   - `S3_BUCKET`: `indian-high-court-judgments`
   - `AWS_DEFAULT_REGION`: `ap-south-1`
   - `SERVICE_LAG_DAYS`: `30`
   - `DAILY_GEMINI_BUDGET`: `250`
   - `ALLOWED_ORIGINS`: `*` *(we will restrict this in Step 4)*
7. Click **Create Web Service**.
8. Render will build the Docker container and start the service. Note your public backend URL (e.g., `https://nyaysetu-api.onrender.com`).

---

## Step 2: Verify Backend Deployment

Run these two commands in your terminal or browser (replace with your actual Render URL):

### 1. Health Verification:
```bash
curl -f https://nyaysetu-api.onrender.com/health
```
**Expected response**:
```json
{"status":"ok","database":"sqlite","database_status":"connected"}
```

### 2. Dashboard Telemetry Verification:
```bash
curl -f https://nyaysetu-api.onrender.com/dashboard
```
**Expected response**: JSON payload with `status_counts`, `top_departments`, and `link_stats`.

---

## Step 3: Deploy Frontend on Vercel

1. Log in to your [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New...** $\rightarrow$ **Project**.
3. Import the `NyaySetu` repository.
4. In the **Configure Project** screen:
   - **Framework Preset**: `Vite`
   - **Root Directory**: Click **Edit** and select `frontend`.
   - **Build and Output Settings**:
     - Build Command: `npm run build`
     - Output Directory: `dist`
5. Expand the **Environment Variables** section and add:
   - **Key**: `VITE_API_URL`
   - **Value**: `https://nyaysetu-api.onrender.com` *(your Render URL from Step 1, without trailing slash)*
6. Click **Deploy**.
7. Vercel will build the frontend in ~20 seconds and assign your live URL (e.g., `https://nyaysetu.vercel.app`).

---

## Step 4: Restrict CORS on Render

Now that your frontend domain is known, lock down backend access:

1. Return to your [Render Dashboard](https://dashboard.render.com).
2. Open your `nyaysetu-api` service $\rightarrow$ **Environment** tab.
3. Locate `ALLOWED_ORIGINS` and change its value from `*` to your Vercel URL:
   ```text
   https://nyaysetu.vercel.app
   ```
4. Click **Save Changes**. Render will automatically redeploy the service.

---

## Step 5: End-to-End Verification Checklist

Visit your live Vercel site in any web browser and verify:

- [ ] **Principal Register (Dashboard)**: Displays the ruled row of headline numbers (`10 COMPLIED`, `4 PENDING`, `93 UNVERIFIED`) and department table.
- [ ] **Compliance Ledger**: Filter by department (e.g., "School Education"), click any row to expand evidence, and test the **Export Ledger CSV** button.
- [ ] **Law Report (Judgments)**: Select an order, view the serif law report, and click a direction margin note to scroll to the yellow highlighted quote.
- [ ] **Case Timeline**: Select `MAT/408/2022` or `WPA/5477/2022` to see the chronological chain linking original writs to subsequent contempt petitions.
- [ ] **Evaluation View**: Verifies the evaluation harness with Citation-resolution rate (rule adherence) and the note: *"Linkable pairs were ingested by targeted search, so this is not an accuracy estimate."*
- [ ] **Diagnostics Page**: Verifies SQLite persistence, unsigned S3 connectivity, and Gemini API budget status.

---

## Optional: CLI Deployment Commands

If you have the CLIs installed and logged in locally, you can use these commands (do not run without user consent):

### Vercel CLI (Frontend):
```bash
# Preview deployment:
vercel --cwd frontend

# Production deployment:
vercel --cwd frontend --prod
```

### Render CLI / Blueprint:
```bash
# Validate Blueprint:
render blueprint validate render.yaml
```
