"""
Pinecone-hosted embedding for llama-index.

Uses Pinecone Inference to embed text with `multilingual-e5-large` — the SAME
model the index was originally built with — instead of loading a ~2 GB local
model into the container. This removes the torch / transformers / sentence-
transformers dependency, so the backend fits a 512 MB host (Render free tier)
and boots in seconds instead of loading model weights.

Compatibility: the existing Pinecone vectors were produced from
`intfloat/multilingual-e5-large` with the e5 "query:" / "passage:" prefix
convention. Pinecone's hosted copy applies that same convention via the
`input_type` parameter ("query" vs "passage"), so query embeddings produced
here line up with the passage vectors already in the index. No re-indexing.
"""
from typing import List

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr


def _values(item):
    """Pinecone SDK embedding items support both attribute and item access
    depending on version; handle either."""
    v = getattr(item, "values", None)
    if v is None:
        v = item["values"]
    return list(v)


class PineconeInferenceEmbedding(BaseEmbedding):
    """Embed via Pinecone Inference (hosted multilingual-e5-large)."""

    _pc = PrivateAttr()
    _model: str = PrivateAttr()

    def __init__(self, pc, model: str = "multilingual-e5-large", **kwargs):
        # model_name is just a label used in llama-index logging.
        kwargs.setdefault("model_name", model)
        super().__init__(**kwargs)
        self._pc = pc
        self._model = model

    def _embed(self, texts: List[str], input_type: str) -> List[List[float]]:
        resp = self._pc.inference.embed(
            model=self._model,
            inputs=texts,
            parameters={"input_type": input_type, "truncate": "END"},
        )
        # resp is an EmbeddingsList; resp.data (or iterating resp) yields items.
        data = getattr(resp, "data", None) or list(resp)
        return [_values(d) for d in data]

    # --- queries use input_type="query"; documents use "passage" ---
    def _get_query_embedding(self, query: str) -> List[float]:
        return self._embed([query], "query")[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._embed([text], "passage")[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts, "passage")

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)
