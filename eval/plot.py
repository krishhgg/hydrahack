"""Render eval/results/waypoint-test.json as an SVG learning curve (no plotting dependency).

uv run python -m eval.plot
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
W, H, L, R, T, B = 760, 420, 70, 150, 50, 60
SERIES = [
    ("waypoint", "Waypoint (learns in HydraDB)", "#22c55e", ""),
    ("flat_memory", "Flat memory (copy nearest run)", "#60a5fa", "6 4"),
    ("flat_knn", "Flat k-NN (same budget)", "#f59e0b", "3 3"),
    ("bm25", "Stateless BM25 tool search", "#9ca3af", "2 4"),
]


def render(result: dict) -> str:
    curve = result["curve"]
    xs = [p["runs"] for p in curve]
    xmax = max(xs) or 1
    ymax = 1.0

    def px(x: float) -> float:
        return L + (W - L - R) * x / xmax

    def py(y: float) -> float:
        return T + (H - T - B) * (1 - y / ymax)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Inter, Helvetica, Arial, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#0b0f17"/>',
        f'<text x="{L}" y="28" fill="#e5e7eb" font-size="17" font-weight="600">'
        f"Completeness@5 on {result['eval_tasks']:,} held-out ToolBench G3 tasks</text>",
    ]
    for i in range(6):
        y = i / 5
        out.append(
            f'<line x1="{L}" x2="{W - R}" y1="{py(y):.1f}" y2="{py(y):.1f}" stroke="#1f2937"/>'
            f'<text x="{L - 10}" y="{py(y) + 4:.1f}" fill="#9ca3af" font-size="12" '
            f'text-anchor="end">{y:.1f}</text>'
        )
    for x in xs:
        if x in (0, xmax) or x >= xmax * 0.2:
            out.append(
                f'<text x="{px(x):.1f}" y="{H - B + 20}" fill="#9ca3af" font-size="12" '
                f'text-anchor="middle">{x:,}</text>'
            )
    out.append(
        f'<text x="{(L + W - R) / 2:.0f}" y="{H - 15}" fill="#9ca3af" font-size="13" '
        f'text-anchor="middle">training runs fed back into the graph</text>'
    )
    for key, _label, color, dash in SERIES:
        pts = " ".join(f"{px(p['runs']):.1f},{py(p[key]['completeness']):.1f}" for p in curve)
        last = curve[-1][key]["completeness"]
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3" '
            f'stroke-dasharray="{dash}" stroke-linejoin="round"/>'
        )
        for p in curve:
            out.append(
                f'<circle cx="{px(p["runs"]):.1f}" cy="{py(p[key]["completeness"]):.1f}" '
                f'r="3" fill="{color}"/>'
            )
        out.append(
            f'<text x="{W - R + 10}" y="{py(last) + 4:.1f}" fill="{color}" font-size="13" '
            f'font-weight="600">{last:.3f}</text>'
        )
    for i, (_, label, color, dash) in enumerate(SERIES):
        y = T + 14 + i * 20
        out.append(
            f'<line x1="{L + 14}" x2="{L + 40}" y1="{y}" y2="{y}" stroke="{color}" '
            f'stroke-width="3" stroke-dasharray="{dash}"/>'
            f'<text x="{L + 48}" y="{y + 4}" fill="#e5e7eb" font-size="12">{label}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "waypoint-test"
    result = json.loads((RESULTS / f"{name}.json").read_text())
    (RESULTS / f"{name}.svg").write_text(render(result))


if __name__ == "__main__":
    main()
