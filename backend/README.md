---
title: Ask The Eagle Backend
emoji: 🦅
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Ask the Eagle — Backend

Multilingual voice + text RAG assistant for FGCU's U.A. Whitaker College of
Engineering. This Space runs the FastAPI backend (retrieval, LLM, STT/TTS).

The frontend (Next.js) is deployed separately on Vercel and calls this API.

## Required secrets (set under Settings → Variables and secrets)

- `GROQ_API_KEY`
- `PINECONE_API_KEY`
- `PINECONE_INDEX_NAME`
- `COHERE_API_KEY`
- `ELEVENLABS_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY` (service_role / secret key — backend only)
- `ALLOWED_ORIGINS` (e.g. `https://your-app.vercel.app`)

Optional: `SUPABASE_TABLE`, `SUPABASE_ISSUES_TABLE`, `TURNSTILE_SECRET`,
`SESSION_SECRET`.
