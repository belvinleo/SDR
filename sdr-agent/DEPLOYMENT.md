### Prerequisites
- Railway.app account (free tier supports this scale)
- All API keys from `.env.example` obtained

### Step 1: Create Railway project
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Step 2: Add managed services on Railway dashboard
- Add Redis plugin (free tier: 25MB — enough for <500 leads)
- Add Postgres plugin (free tier: 1GB)
- Railway auto-injects `REDIS_URL` and `DATABASE_URL` env vars

### Step 3: Set environment variables
In Railway dashboard → Variables, add every key from `.env.example` except `REDIS_URL` and `DATABASE_URL` (auto-set by plugins).

### Step 4: Deploy
```bash
railway up
```

### Step 5: Verify
```bash
railway logs --tail
curl https://your-app.railway.app/health
```
Expected: `{"status": "ok", "graph_ready": true}`

### Step 6: Trigger your first real lead
```bash
curl -X POST https://your-app.railway.app/webhook/lead \
  -H "Content-Type: application/json" \
  -d '{
    "email": "yourtest@realdomain.com",
    "name": "Your Name",
    "company": "Test Company",
    "domain": "realdomain.com",
    "title": "VP of Sales"
  }'
```

### Monitoring
- LangSmith: https://smith.langchain.com → project `sdr-agent`
- Railway logs: `railway logs --tail`
- Lead status: `GET /webhook/lead/{lead_id}/status`

### Cost at <500 leads/month
| Service | Cost |
|---------|------|
| Railway Hobby | $5/month |
| Apollo.io Basic | $49/month |
| Tavily | ~$10/month |
| Instantly.ai | $37/month |
| Unipile | $20/month |
| Claude API (Sonnet + Haiku) | ~$15/month |
| **Total** | **~$136/month** |
