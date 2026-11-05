# -*- coding: utf-8 -*-
"""The embedder seam. An embedder is any callable `embed(texts) -> list[vector]` with a
`model` attribute naming the model; the index records that name and refuses to search
with a different one. OllamaEmbedder is the real adapter; tests pass a fake."""
import json
import urllib.request

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3-embedding:0.6b"


class OllamaEmbedder:
    """Embeds through a running Ollama server's /api/embed. Never starts Ollama. Raises
    OSError (URLError, timeouts) when no server answers, RuntimeError on a bad reply."""

    def __init__(self, url=DEFAULT_URL, model=DEFAULT_MODEL, timeout=120):
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout

    @classmethod
    def from_config(cls, c):
        e = c.get("embed", {})
        return cls(e.get("url"), e.get("model"))

    def __call__(self, texts):
        texts = list(texts)
        body = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        req = urllib.request.Request(self.url + "/api/embed", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        vecs = data.get("embeddings") if isinstance(data, dict) else None
        if not vecs or len(vecs) != len(texts):
            raise RuntimeError(f"embed returned {0 if not vecs else len(vecs)} vectors "
                               f"for {len(texts)} inputs")
        out = []
        for v in vecs:
            norm = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / norm for x in v])
        return out
