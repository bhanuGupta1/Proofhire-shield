# Deploy Guide — ProofHire Shield

Zero cost. No credit card. Backend on Hugging Face Spaces, frontend on Cloudflare Pages.

---

## Backend — Hugging Face Spaces (Docker)

### First time

1. Go to [huggingface.co](https://huggingface.co) → sign up / log in
2. Click **New Space**
3. Set:
   - Space name: `proofhire-shield-api`
   - SDK: **Docker**
   - Visibility: **Public**
4. Clone the empty Space repo:
   ```bash
   git clone https://huggingface.co/spaces/YOUR_HF_USERNAME/proofhire-shield-api
   cd proofhire-shield-api
   ```
5. Copy the backend folder contents into it:
   ```bash
   cp -r /path/to/proofhire-shield/backend/* .
   ```
   (The `backend/README.md` already has the HF Spaces frontmatter — keep it as-is)
6. Push:
   ```bash
   git add .
   git commit -m "feat: initial deploy"
   git push
   ```
7. HF Spaces builds the Docker image automatically. Watch logs in the Space UI.
8. Your API URL: `https://YOUR_HF_USERNAME-proofhire-shield-api.hf.space`

### Set CORS env var in HF Spaces

In the Space → **Settings → Variables and secrets**:
- Name: `CORS_ORIGINS`
- Value: `https://proofhire-shield.pages.dev` (your Cloudflare Pages URL — set this after step below)

### Updates

Push changes to the HF Space repo. Rebuild happens automatically:
```bash
# In your proofhire-shield-api HF Space clone
cp -r /path/to/proofhire-shield/backend/* .
git add . && git commit -m "feat: update" && git push
```

---

## Frontend — Cloudflare Pages

### First time

1. Go to [pages.cloudflare.com](https://pages.cloudflare.com) → sign up (free, no card)
2. Click **Create a project** → **Connect to Git**
3. Connect your GitHub account → select `proofhire-shield` repo
4. Build settings:
   - **Framework preset**: None (or Vite)
   - **Root directory**: `frontend`
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
5. Environment variables → Add:
   - Name: `VITE_API_URL`
   - Value: `https://YOUR_HF_USERNAME-proofhire-shield-api.hf.space`
6. Click **Save and Deploy**

Your URL: `https://proofhire-shield.pages.dev` (or Cloudflare assigns a subdomain)

### Updates

Just push to `main` on GitHub — Cloudflare Pages redeploys automatically.

---

## After both are live

1. Copy your Cloudflare Pages URL
2. Go to HF Space → Settings → Variables → update `CORS_ORIGINS` to your Pages URL
3. Restart the Space (Settings → Factory reset, or just push a trivial commit)
4. Test: open the Cloudflare URL, upload one of the `demo-cvs/` PDFs, verify scan works end-to-end

---

## Local dev (no deploy needed)

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Terminal 2 — frontend (proxies /scan-cv to localhost:8000 automatically)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

---

## Health check

```
GET https://YOUR_HF_USERNAME-proofhire-shield-api.hf.space/health
```

Should return `{"status": "ok"}`. Hit this before a demo to wake the Space if it's been idle.
