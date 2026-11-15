# Pick-stage proofs of concept

Throwaway Python scripts that produced the numbers in docs/candidates.md and docs/recommendation.md before the pick. They don't use HydraDB. eval/ (in the build PRs) is the real harness and supersedes them.

Data: download the Tool-COLT ToolBench G3 files (`corpus.jsonl`, `queries.jsonl`, `query_tool_train.txt`, `query_tool_test.txt`) from https://huggingface.co/datasets/Tool-COLT/ToolBenchG3 into a folder, then pass the folder:

| Script | Numbers (first 600 or 800 test tasks) | Run |
|---|---|---|
| `cousage_bm25.py` | BM25 C@5 0.117 and co-usage expansion (800 tasks) | `uv run --with rank_bm25 --with numpy python poc/cousage_bm25.py DIR` |
| `experience_knn.py` | BM25 C@5 0.123, R@5 0.375; with experience from 10k training runs C@5 0.688, R@5 0.828 (600 tasks) | `uv run --with rank_bm25 --with numpy python poc/experience_knn.py DIR` |
| `dense_baseline.py` | dense bge-small C@5 0.123, R@5 0.398 (600 tasks) | `uv run --with fastembed --with numpy python poc/dense_baseline.py DIR` |

Only training-split labels are ever used as experience; the test labels are used for scoring only. The COLT `query_tool_tune.txt` file is byte-identical to the test file and is not read.

The flat-memory figures (C@5 0.496 overall, 0.608 seen, 0.049 novel) came from the independent reviewer's ad-hoc check during the attack round and are not reproduced by a script here. `eval/run_eval.py` reports a flat-memory baseline (copy the nearest past task's tools) at every checkpoint, and docs/results.md quotes only those numbers.
