# Production Deployment Guide: Court-Order Compliance Radar

This guide describes how to deploy NyaySetu (Court-Order Compliance Radar) to production environments such as Render, Railway, Docker, or bare-metal Linux VPS, with zero mock or synthetic data.

---

## 1. Environment Variables Reference

All runtime configuration is managed strictly through environment variables. **No secrets or credentials are hardcoded or committed to the repository.**

| Variable | Type | Default | Required | Purpose |
| :--- | :--- | :--- | :---: | :--- |
| `GEMINI_API_KEY` | `string` | `""` | **Yes** | Google Gemini API key for structured operative direction extraction and follow-up order classification. |
| `GEMINI_MODEL` | `string` | `gemini-flash-lite-latest` | No | Primary Gemini model name (e.g. `gemini-2.5-flash` or `gemini-flash-lite-latest`). |
| `GEMINI_FALLBACK_MODEL` | `string` | `gemini-1.5-flash` | No | Secondary fallback model when the primary encounters 503 capacity errors. |
| `DAILY_GEMINI_BUDGET` | `int` | `250` | No | Daily quota safety cap to prevent bill shock or quota exhaustion. |
| `DATABASE_URL` | `string` | `sqlite:///./compliance_radar.db` | **Yes** | Database connection string. Supports SQLite (`sqlite:////data/compliance_radar.db`) or PostgreSQL (`postgresql://user:pass@host/db`). |
| `S3_BUCKET` | `string` | `indian-high-court-judgments` | No | AWS Open Data public S3 bucket (`CC-BY-4.0`, unsigned public access). |
| `AWS_DEFAULT_REGION` | `string` | `ap-south-1` | No | S3 bucket region. |
| `SERVICE_LAG_DAYS` | `int` | `30` | No | Configurable delivery lag constant for government service date windows. |
| `ALLOWED_ORIGINS` | `string` | `*` | No | Comma-separated list of allowed CORS origins (e.g. `https://nyaysetu.vercel.app`). |
| `VITE_API_URL` | `string` | `""` | Frontend | Full URL of the backend API service (e.g. `https://api.nyaysetu.onrender.com`). |

---

## 2. Idempotent Real Bootstrap (`scripts/bootstrap.py`)

On first deployment, run the automated bootstrap script to initialize the database with real judgments from the official AWS Open Data repository:

```bash
python scripts/bootstrap.py
```

### Bootstrap Behavior & Hard Rules:
1. **S3 Pre-flight Connectivity Check**: Tests unsigned public access to `indian-high-court-judgments`. If AWS S3 is unreachable, **it immediately aborts with exit code 1** to prevent creating or seeding fake data.
2. **Idempotency**: If the database already contains the required number of analyzed judgments, bootstrap skips ingestion and logs that the database is already primed.
3. **Pipeline Stages**:
   - Ingests $N$ real judgments (`BOOTSTRAP_LIMIT=25`, configurable).
   - Extracts operative directions via the agent loop.
   - Computes deterministic deadline date windows.
   - Links follow-up contempt petitions to earlier writ orders.
   - Computes headline compliance statuses (`COMPLIED`, `PENDING`, `UNVERIFIED`).

---

## 3. Option A: Deployment via Render (Blueprint)

The repository includes a ready-to-use `render.yaml` blueprint with persistent disk storage:

1. Connect your repository in the [Render Dashboard](https://dashboard.render.com).
2. Click **New +** $\rightarrow$ **Blueprint**.
3. Select this repository. Render reads `render.yaml` and sets up:
   - **`compliance-radar-api`**: Python Web Service with 1GB persistent disk mounted at `/data`.
   - **`compliance-radar-ui`**: React/Vite Static Site with SPA rewrites.
4. Set the secret `GEMINI_API_KEY` in the Render Environment tab.
5. Deploy. The backend startup command runs `python scripts/bootstrap.py && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`.

---

## 4. Option B: Docker Container Deployment

### 1. Build Backend Image
```bash
docker build -t compliance-radar:latest .
```

### 2. Run Container with Persistent Volume
```bash
docker run -d \
  --name compliance-radar-app \
  -p 8000:8000 \
  -v compliance_radar_data:/data \
  -e DATABASE_URL="sqlite:////data/compliance_radar.db" \
  -e GEMINI_API_KEY="your-gemini-api-key" \
  -e ALLOWED_ORIGINS="http://localhost:5173,https://yourdomain.com" \
  compliance-radar:latest
```

### 3. Verify Container Health
```bash
docker ps
curl http://localhost:8000/health
```

---

## 5. Option C: Frontend Deployment (Vercel / Netlify)

1. **Vercel**:
   - Connect the repository on [Vercel](https://vercel.com).
   - Root directory: `frontend`.
   - Build Command: `npm run build`.
   - Output Directory: `dist`.
   - Environment Variable: Add `VITE_API_URL` pointing to your deployed backend (e.g. `https://api.nyaysetu.onrender.com`).
   - SPA rewrites are pre-configured in `frontend/vercel.json`.

2. **Netlify**:
   - Connect repository on [Netlify](https://netlify.com).
   - Base directory: `frontend`.
   - Build command: `npm run build`.
   - Publish directory: `frontend/dist`.
   - Environment Variable: Add `VITE_API_URL`.
   - SPA redirects are pre-configured in `frontend/netlify.toml`.

---

## 6. Verification Checklist

After deployment, verify the following endpoints:

| Endpoint | Method | Expected Output |
| :--- | :---: | :--- |
| `/health` | `GET` | `{"status": "healthy", "service": "court-order-compliance-radar", ...}` |
| `/dashboard` | `GET` | Status counts (`COMPLIED`, `PENDING`, `UNVERIFIED`), top 10 departments, pipeline feed |
| `/ledger?page=1&page_size=10` | `GET` | Real directions with cleaned department names & deadline windows |
| `/calendar?month=2023-10` | `GET` | Directions due in October 2023 |
| `/eval/results` | `GET` | Ground truth evaluation metrics or `"no human gold labels available"` |

