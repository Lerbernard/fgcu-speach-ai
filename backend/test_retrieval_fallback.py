# -*- coding: utf-8 -*-
"""
test_retrieval_fallback.py — verifies the answer_question() empty-result safety
net: when a course-code query matches no chunks, it should retry across
offering+description, then code-only, instead of dead-ending as "Empty Response".

Stubs the heavy deps and replaces make_engine with a recorder, so no Pinecone /
Groq / keys are needed. Run:  python test_retrieval_fallback.py
"""
import sys, types, io, contextlib, importlib
from unittest.mock import MagicMock


def _install_stubs():
    def mod(n):
        m = types.ModuleType(n); sys.modules[n] = m; return m
    li = mod("llama_index"); lic = mod("llama_index.core")
    lic.VectorStoreIndex = MagicMock(); lic.Settings = MagicMock(); li.core = lic
    vs = mod("llama_index.core.vector_stores")
    vs.MetadataFilters = vs.MetadataFilter = vs.FilterOperator = MagicMock(); lic.vector_stores = vs
    lvs = mod("llama_index.vector_stores"); lpc = mod("llama_index.vector_stores.pinecone")
    lpc.PineconeVectorStore = MagicMock(); lvs.pinecone = lpc; li.vector_stores = lvs
    le = mod("llama_index.embeddings"); lhf = mod("llama_index.embeddings.huggingface")
    lhf.HuggingFaceEmbedding = MagicMock(); le.huggingface = lhf; li.embeddings = le
    ll = mod("llama_index.llms"); lg = mod("llama_index.llms.groq")
    lg.Groq = MagicMock(); ll.groq = lg; li.llms = ll
    pc = mod("pinecone")
    class _I:
        def query(self, *a, **k): return {"matches": []}
    class _P:
        def __init__(self, *a, **k): pass
        def Index(self, *a, **k): return _I()
    pc.Pinecone = _P
    mod("dotenv").load_dotenv = lambda *a, **k: None
    mod("httpx"); mod("edge_tts")
    fa = mod("fastapi")
    class _App:
        def add_middleware(self, *a, **k): pass
        def _d(self, *a, **k):
            def d(f): return f
            return d
        post = _d; get = _d
    fa.FastAPI = lambda *a, **k: _App()
    fa.UploadFile = object; fa.File = fa.Form = fa.Body = lambda *a, **k: None
    fa.Response = object
    famw = mod("fastapi.middleware"); fac = mod("fastapi.middleware.cors")
    fac.CORSMiddleware = object; famw.cors = fac; fa.middleware = famw
    far = mod("fastapi.responses"); far.Response = object; fa.responses = far


_install_stubs()
with contextlib.redirect_stdout(io.StringIO()):
    main = importlib.import_module("main")
main.KNOWN_PROFESSORS = ["allen paul"]


class FakeResp:
    def __init__(self, text, has_nodes=True):
        self._t = text
        self.source_nodes = [object()] if has_nodes else []
    def __str__(self): return self._t


EMPTY = lambda: FakeResp("Empty Response", has_nodes=False)

# Recorder make_engine: logs each call and returns the next queued response.
CALLS = []
QUEUE = []


def fake_make_engine(doc_types, program, term, course_code=None, professor=None):
    CALLS.append({"doc_types": doc_types, "course_code": course_code,
                  "professor": professor, "term": term})
    idx = len(CALLS) - 1
    resp = QUEUE[idx] if idx < len(QUEUE) else EMPTY()
    class _E:
        def query(self, prompt): return resp
    return _E()


main.make_engine = fake_make_engine


def scenario(name, question, history, queue):
    global CALLS, QUEUE
    CALLS, QUEUE = [], queue
    text, _ui = main.answer_question(question, history)
    return text, list(CALLS)


def run():
    p = f = 0
    def check(n, c):
        nonlocal p, f
        if c: p += 1; print(f"[PASS] {n}")
        else: f += 1; print(f"[FAIL] {n}")

    # E1: offering empty -> broaden to offering+description -> answers
    text, calls = scenario(
        "E1", "Who teaches COP 1500 and what is the course about?", None,
        [EMPTY(), FakeResp("COP 1500 is an intro course covering ...")])
    check("E1: returns the broadened answer", text.startswith("COP 1500 is an intro"))
    check("E1: first try was course_offering+code",
          calls[0]["doc_types"] == ["course_offering"] and calls[0]["course_code"] == "cop 1500")
    check("E1: retry broadened to offering+description, term/prof dropped",
          calls[1]["doc_types"] == ["course_offering", "course_description"]
          and calls[1]["course_code"] == "cop 1500"
          and calls[1]["professor"] is None and calls[1]["term"] is None)
    check("E1: exactly two attempts", len(calls) == 2)

    # E2: offering empty, broaden empty -> code-only any doc type
    text, calls = scenario(
        "E2", "I don't want the schedule, just tell me what COP 1500 covers", None,
        [EMPTY(), EMPTY(), FakeResp("It covers variables, loops, and functions.")])
    check("E2: final code-only attempt answers", text.startswith("It covers"))
    check("E2: third attempt is code-only, no doc_type filter",
          calls[2]["doc_types"] is None and calls[2]["course_code"] == "cop 1500")
    check("E2: exactly three attempts", len(calls) == 3)

    # E3: first try succeeds -> no retry
    text, calls = scenario(
        "E3", "What is COP 2006 about?", None,
        [FakeResp("COP 2006 is Programming I.")])
    check("E3: single attempt when first succeeds", len(calls) == 1)
    check("E3: returns the answer", text.startswith("COP 2006 is"))

    # E4: a prof-teach query (no course_code) that finds nothing now falls through
    # to the universal unfiltered retry, so any professor's info stays reachable.
    text, calls = scenario(
        "E4", "What does Professor Allen teach?", None, [EMPTY()])
    check("E4: prof-teach empty -> universal unfiltered retry (2 attempts)", len(calls) == 2)
    check("E4: first attempt carried the professor filter, no code",
          calls[0]["professor"] == "allen paul" and calls[0]["course_code"] is None)
    check("E4: retry is unfiltered (no doc_type, professor, or code)",
          calls[1]["doc_types"] is None and calls[1]["professor"] is None
          and calls[1]["course_code"] is None)

    print(f"\n{p} passed, {f} failed")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(run())