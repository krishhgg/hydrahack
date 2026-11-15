"""A small incremental BM25 index. HydraDB has no text index, so entry points are resolved here."""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
STOP = frozenset(
    "the a an and or of to for in on with by is are be it this that i me my we our you your "
    "can could would will also some any from at as about need want like please get find "
    "provide give using use help know".split()
)


def tokenize(text: str) -> list[str]:
    return [w for w in _TOKEN.findall(text.lower()) if len(w) > 1 and w not in STOP]


class BM25:
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.postings: dict[str, tuple[list[int], list[int]]] = {}
        self.doc_ids: list[int] = []
        self.pos: dict[int, int] = {}
        self.lengths: list[int] = []
        self.total = 0
        self._arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._lengths: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.doc_ids)

    def add(self, doc_id: int, text: str) -> None:
        if doc_id in self.pos:
            return
        toks = tokenize(text)
        p = len(self.doc_ids)
        self.pos[doc_id] = p
        self.doc_ids.append(doc_id)
        self.lengths.append(len(toks))
        self.total += len(toks)
        for term, tf in Counter(toks).items():
            docs, tfs = self.postings.setdefault(term, ([], []))
            docs.append(p)
            tfs.append(tf)
            self._arrays.pop(term, None)
        self._lengths = None

    def search(self, text: str, top: int = 20) -> list[tuple[int, float]]:
        return self.search_scaled(text, top)[0]

    def search_scaled(self, text: str, top: int = 20) -> tuple[list[tuple[int, float]], float]:
        """Top hits plus the score ceiling for this query (every query term saturated in one
        document), so callers can turn a score into an absolute 0..1 similarity."""
        n = len(self.doc_ids)
        if not n:
            return [], 1.0
        if self._lengths is None or len(self._lengths) != n:
            self._lengths = np.asarray(self.lengths, dtype=np.float64)
        norm = self.k1 * (1 - self.b + self.b * self._lengths / (self.total / n))
        scores = np.zeros(n)
        ceiling = 0.0
        for term in set(tokenize(text)):
            post = self.postings.get(term)
            if not post:
                continue
            arr = self._arrays.get(term)
            if arr is None:
                arr = (np.asarray(post[0]), np.asarray(post[1], dtype=np.float64))
                self._arrays[term] = arr
            docs, tfs = arr
            idf = math.log(1 + (n - len(docs) + 0.5) / (len(docs) + 0.5))
            ceiling += idf * (self.k1 + 1)
            scores[docs] += idf * tfs * (self.k1 + 1) / (tfs + norm[docs])
        k = min(top, n)
        best = np.argpartition(-scores, k - 1)[:k]
        best = best[np.argsort(-scores[best])]
        hits = [(self.doc_ids[i], float(scores[i])) for i in best if scores[i] > 0]
        return hits, ceiling or 1.0
