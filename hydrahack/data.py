"""ToolBench G3 (COLT split): download, parse and split.

The COLT `query_tool_tune.txt` file is byte-identical to the test file, so it is never read.
Validation is a fixed slice of train.
"""

from __future__ import annotations

import json
import os
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import httpx

HF_BASE = "https://huggingface.co/datasets/Tool-COLT/ToolBenchG3/resolve/main"
FILES = ["corpus.jsonl", "queries.jsonl", "query_tool_train.txt", "query_tool_test.txt"]
DATA_DIR = Path(os.environ.get("WAYPOINT_DATA", Path(__file__).resolve().parent.parent / "data"))
VAL_SIZE = 2000
SPLIT_SEED = 7

_FIELD = re.compile(
    r"category_name:(?P<cat>.*?), tool_name:(?P<tool>.*?), api_name:(?P<api>.*?), "
    r"api_description:(?P<desc>.*?), required_params:"
)


@dataclass
class Api:
    idx: int
    category: str
    tool: str
    name: str
    description: str
    text: str


@dataclass
class Dataset:
    apis: list[Api]
    queries: dict[str, str]
    train: dict[str, set[int]]
    val: dict[str, set[int]]
    test: dict[str, set[int]]
    stream_order: list[str] = field(default_factory=list)


def download(dest: Path = DATA_DIR / "ToolBenchG3") -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        path = dest / name
        if path.exists() and path.stat().st_size > 0:
            continue
        with httpx.stream("GET", f"{HF_BASE}/{name}", follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    return dest


def _pairs(path: Path) -> dict[str, set[int]]:
    out: dict[str, set[int]] = defaultdict(set)
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            out[parts[0]].add(int(parts[1]))
    return dict(out)


def load(root: Path | None = None) -> Dataset:
    root = root or download()
    apis = []
    for line in (root / "corpus.jsonl").read_text().splitlines():
        row = json.loads(line)
        text = row["text"]
        m = _FIELD.search(text)
        cat, tool, name, desc = (
            (m["cat"], m["tool"], m["api"], m["desc"].strip()) if m else ("", "", text[:60], "")
        )
        apis.append(Api(int(row["_id"]), cat, tool, name, desc, text))
    apis.sort(key=lambda a: a.idx)
    queries = {}
    for line in (root / "queries.jsonl").read_text().splitlines():
        row = json.loads(line)
        queries[row["_id"]] = row["text"]
    train_all = _pairs(root / "query_tool_train.txt")
    test = _pairs(root / "query_tool_test.txt")
    ids = sorted(train_all, key=int)
    random.Random(SPLIT_SEED).shuffle(ids)
    val = {q: train_all[q] for q in ids[:VAL_SIZE]}
    stream = ids[VAL_SIZE:]
    train = {q: train_all[q] for q in stream}
    return Dataset(apis, queries, train, val, test, stream)
