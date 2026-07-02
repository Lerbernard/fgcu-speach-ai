# -*- coding: utf-8 -*-
"""
test_speak_fallback.py — verifies the /speak failover behavior with no real
network and no API keys. It stubs httpx (the ElevenLabs call) and edge_tts so we
can drive every branch:

  A) ElevenLabs returns audio        -> use ElevenLabs, do NOT latch
  B) ElevenLabs returns quota error  -> switch to edge-tts, LATCH the flag
  C) after a latch                   -> skip ElevenLabs entirely, use edge-tts
  D) ElevenLabs raises (timeout)     -> use edge-tts, do NOT latch (transient)

Run:  python test_speak_fallback.py
"""
import sys
import types
import io
import asyncio
import contextlib
import importlib
from unittest.mock import MagicMock


# --- A controllable fake for the ElevenLabs HTTP call -----------------------
class _FakeResp:
    def __init__(self, status_code, content=b"", text="", content_type="audio/mpeg"):
        self.status_code = status_code
        self.content = content
        self._text = text or (content.decode("utf-8", "ignore") if content else "")
        self.headers = {"content-type": content_type}

    @property
    def text(self):
        return self._text


class _FakeHTTP:
    """Records calls and returns a queued response, or raises if told to."""
    def __init__(self):
        self.next_response = None
        self.raise_exc = None
        self.post_calls = 0

    def client(self, *a, **k):
        outer = self

        class _Client:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *a):
                return False

            async def post(self_, url, **kw):
                outer.post_calls += 1
                if outer.raise_exc:
                    raise outer.raise_exc
                return outer.next_response

        return _Client()


FAKE = _FakeHTTP()


# --- Stub modules BEFORE importing main -------------------------------------
def _install_stubs():
    def mod(name):
        m = types.ModuleType(name); sys.modules[name] = m; return m

    li = mod("llama_index"); lic = mod("llama_index.core")
    lic.VectorStoreIndex = MagicMock(); lic.Settings = MagicMock(); lic.PromptTemplate = MagicMock(); li.core = lic
    vs = mod("llama_index.core.vector_stores")
    vs.MetadataFilters = vs.MetadataFilter = vs.FilterOperator = MagicMock(); lic.vector_stores = vs
    lvs = mod("llama_index.vector_stores"); lpc = mod("llama_index.vector_stores.pinecone")
    lpc.PineconeVectorStore = MagicMock(); lvs.pinecone = lpc; li.vector_stores = lvs
    le = mod("llama_index.embeddings"); lhf = mod("llama_index.embeddings.huggingface")
    lhf.HuggingFaceEmbedding = MagicMock(); le.huggingface = lhf; li.embeddings = le
    ll = mod("llama_index.llms"); lg = mod("llama_index.llms.groq")
    lg.Groq = MagicMock(); ll.groq = lg; li.llms = ll

    pc = mod("pinecone")
    class _Index:
        def query(self, *a, **k): return {"matches": []}
    class _PC:
        def __init__(self, *a, **k): pass
        def Index(self, *a, **k): return _Index()
    pc.Pinecone = _PC

    dv = mod("dotenv"); dv.load_dotenv = lambda *a, **k: None

    # httpx -> our controllable fake
    hx = mod("httpx")
    hx.AsyncClient = lambda *a, **k: FAKE.client(*a, **k)

    # edge_tts -> records the chosen voice, yields fake audio
    et = mod("edge_tts")
    et.last_voice = None
    class _Communicate:
        def __init__(self, text, voice):
            et.last_voice = voice
            self._text = text
        async def stream(self):
            yield {"type": "audio", "data": b"EDGE_AUDIO_BYTES"}
    et.Communicate = _Communicate

    fa = mod("fastapi")
    class _App:
        def add_middleware(self, *a, **k): pass
        def _deco(self, *a, **k):
            def d(fn): return fn
            return d
        post = _deco; get = _deco
    fa.FastAPI = lambda *a, **k: _App()
    fa.UploadFile = object
    fa.File = fa.Form = fa.Body = lambda *a, **k: None
    # Response: keep the attributes main.py / our asserts read
    class _Response:
        def __init__(self, content=b"", media_type=None, status_code=200, **k):
            self.body = content if isinstance(content, bytes) else str(content).encode()
            self.media_type = media_type
            self.status_code = status_code
    fa.Response = _Response
    famw = mod("fastapi.middleware"); facors = mod("fastapi.middleware.cors")
    facors.CORSMiddleware = object; famw.cors = facors; fa.middleware = famw
    fares = mod("fastapi.responses"); fares.Response = _Response; fa.responses = _Response and fares


_install_stubs()
with contextlib.redirect_stdout(io.StringIO()):
    main = importlib.import_module("main")
import edge_tts as et  # the stub


def run():
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"[PASS] {name}")
        else:
            failed += 1; print(f"[FAIL] {name}")

    # --- A) ElevenLabs returns audio -> use it, no latch --------------------
    main._elevenlabs_quota_hit = False
    FAKE.raise_exc = None
    FAKE.post_calls = 0
    FAKE.next_response = _FakeResp(200, content=b"ELEVEN_AUDIO", content_type="audio/mpeg")
    r = asyncio.run(main.speak("Hello there"))
    check("A: returns ElevenLabs audio", r.body == b"ELEVEN_AUDIO" and r.media_type == "audio/mpeg")
    check("A: ElevenLabs was called", FAKE.post_calls == 1)
    check("A: quota flag NOT latched", main._elevenlabs_quota_hit is False)

    # --- B) ElevenLabs quota error -> switch to edge-tts, latch -------------
    main._elevenlabs_quota_hit = False
    FAKE.post_calls = 0
    FAKE.next_response = _FakeResp(401, text='{"detail":{"status":"quota_exceeded"}}',
                                   content_type="application/json")
    r = asyncio.run(main.speak("¿Qué enseña el profesor Allen?"))
    check("B: falls back to edge-tts audio", r.body == b"EDGE_AUDIO_BYTES")
    check("B: quota flag latched", main._elevenlabs_quota_hit is True)
    check("B: edge picked the Spanish voice", et.last_voice == "es-ES-ElviraNeural")

    # --- C) after latch -> skip ElevenLabs entirely -------------------------
    FAKE.post_calls = 0
    et.last_voice = None
    FAKE.next_response = _FakeResp(200, content=b"SHOULD_NOT_BE_USED")
    r = asyncio.run(main.speak("Allen教授は何を教えますか"))
    check("C: ElevenLabs NOT called after latch", FAKE.post_calls == 0)
    check("C: still returns edge-tts audio", r.body == b"EDGE_AUDIO_BYTES")
    check("C: edge picked the Japanese voice", et.last_voice == "ja-JP-NanamiNeural")

    # --- D) transient ElevenLabs failure -> edge-tts, do NOT latch ----------
    main._elevenlabs_quota_hit = False
    FAKE.post_calls = 0
    FAKE.raise_exc = RuntimeError("connection reset")
    r = asyncio.run(main.speak("Bonjour"))
    check("D: falls back on transient error", r.body == b"EDGE_AUDIO_BYTES")
    check("D: ElevenLabs was attempted", FAKE.post_calls == 1)
    check("D: quota flag NOT latched (transient)", main._elevenlabs_quota_hit is False)
    FAKE.raise_exc = None

    # --- helper: quota-error classifier -------------------------------------
    check("quota: 401 -> True", main._is_elevenlabs_quota_error(401, "") is True)
    check("quota: 402 -> True", main._is_elevenlabs_quota_error(402, "") is True)
    check("quota: 429 -> True", main._is_elevenlabs_quota_error(429, "") is True)
    check("quota: 200 -> False", main._is_elevenlabs_quota_error(200, "ok") is False)
    check("quota: 500 server error -> False", main._is_elevenlabs_quota_error(500, "boom") is False)
    check("quota: body says quota -> True", main._is_elevenlabs_quota_error(403, "quota_exceeded") is True)

    # --- _speakable: spell course codes so TTS doesn't read them as words ---
    check("speak: COP 1500 -> spelled", main._speakable("COP 1500") == "C O P 1500")
    check("speak: embedded code spelled",
          main._speakable("Tell me about COP 1500.") == "Tell me about C O P 1500.")
    check("speak: trailing letter spelled", main._speakable("EGN 3331C") == "E G N 3331 C")
    check("speak: no-space code spelled", main._speakable("COP1500") == "C O P 1500")
    check("speak: 'the 2026' left alone", main._speakable("the 2026 catalog") == "the 2026 catalog")
    check("speak: plain prose untouched",
          main._speakable("I have 1500 dollars") == "I have 1500 dollars")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())