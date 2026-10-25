# Ask the Eagle 🦅

A multilingual voice and text assistant for FGCU's U.A. Whitaker College of Engineering. Students ask about courses, advising, deadlines and the academic calendar, by typing or speaking, and get answers grounded in the college's own pages.

**Live:** https://fgcu-speach-ai.vercel.app

## How it works

```
Browser (Next.js on Vercel)
   │  text or audio
   ▼
FastAPI backend (Docker, Hugging Face Space)
   ├─ /transcribe   Groq Whisper speech-to-text
   ├─ /ask          retrieve from Pinecone → Cohere rerank → Groq LLM answer
   ├─ /speak        ElevenLabs text-to-speech (edge-tts fallback)
   └─ /feedback, /report, /verify   Supabase logging, issue reports, Turnstile
   ▲
data/  (scraped FGCU pages, course catalogs, academic calendar)
   └─ updater/ re-scrapes daily → PR → merged → ingest.yml pushes changes to Pinecone
```

- **Retrieval:** LlamaIndex over a Pinecone index (Pinecone-hosted embeddings), Cohere cross-encoder reranking, Groq-hosted LLM for the final answer.
- **Voice:** Groq Whisper for transcription, ElevenLabs for speech, with a free `edge-tts` fallback when the quota runs out.
- **Languages:** the question's language is detected (`langdetect`) and the answer is pinned to it.
- **Data freshness:** `updater/` re-scrapes the sources in `updater/sources.yaml` every morning and opens a pull request with the diff. Nothing reaches the live index until that PR is merged; then `ingest.yml` pushes only the changed files to Pinecone.

## Repository layout

| Folder | What it is |
| --- | --- |
| `frontend/` | Next.js 16 + Tailwind app (Vercel) |
| `backend/` | FastAPI service, Dockerfile, ingest scripts (deployed to a Hugging Face Space by `sync-to-hf.yml`) |
| `data/` | Scraped source documents the index is built from |
| `updater/` | Daily scraper that keeps `data/` current |
| `tests/` | Unit tests for chunking and the updater |
| `.github/workflows/` | `update-data`, `ingest`, `sync-to-hf`, `tests` |

## Running it locally

**Backend**

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
# put the keys below in backend/.env
uvicorn main:app --reload --port 7860
```

Required environment variables: `GROQ_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `COHERE_API_KEY`, `ELEVENLABS_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `ALLOWED_ORIGINS`. Optional: `SUPABASE_TABLE`, `SUPABASE_ISSUES_TABLE`, `TURNSTILE_SECRET`, `SESSION_SECRET`.

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Point the frontend at the backend URL in `frontend/.env.local` and open http://localhost:3000.

**Tests**

```bash
pytest tests
```

## Author

Lee Bernard · [lerbernard.github.io](https://lerbernard.github.io)
