"""Reproducible measurements for COMPARISON.md: `make measure`.

1. UI code size per side (lines of code, by role; generated/vendored excluded)
2. Artifact sizes (ui:// views, A2UI client bundle, A2UI system prompt)
3. Per scenario, per side, median of N harness runs (Scripted mode by default):
   network bytes, UI payload bytes, round trips, time to first render
   (driven through the comparison UI by Playwright, read from its JSON export)

Outputs measurements/summary.json and docs/measurements.md (summary-live.json
and measurements-live.md in Live mode), and refreshes the matching generated
block of COMPARISON.md between its measurement markers.

Usage: uv run python scripts/measure.py [--runs 10] [--mode scripted|live]
                                        [--reuse]  (skip the browser runs)
"""

import argparse
import gzip
import json
import os
import platform
import statistics
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "measurements" / "raw"
COMPARISON = ROOT / "COMPARISON.md"


def outputs(mode: str) -> tuple[Path, Path, str, str]:
    """Summary, report and COMPARISON.md markers; Scripted and Live are kept apart."""
    suffix = "" if mode == "scripted" else f"-{mode}"
    tag = "measurements" + suffix
    return (
        ROOT / "measurements" / f"summary{suffix}.json",
        ROOT / "docs" / f"measurements{suffix}.md",
        f"<!-- {tag}:start -->",
        f"<!-- {tag}:end -->",
    )


# What counts as each side's code, by role. Business logic lives in core/ and
# is shared, so it is not counted for either side.
LOC_GROUPS: dict[str, dict[str, list[str]]] = {
    "MCP Apps": {
        "UI (ui:// views, TS + CSS + HTML)": [
            "mcp-apps/views/src/**/*.ts",
            "mcp-apps/views/src/**/*.css",
            "mcp-apps/views/*.html",
            "mcp-apps/views/build.mjs",
        ],
        "Server (tools, resources, transport)": ["mcp-apps/server/src/**/*.py"],
    },
    "A2UI": {
        "UI (surface builders, catalog: Python + TS custom components)": [
            "a2ui/agent/src/a2ui_agent/surfaces.py",
            "a2ui/agent/src/a2ui_agent/catalog.py",
            "a2ui/client/src/catalog.ts",
        ],
        "Agent (tools, prompt, executor, A2A server)": [
            "a2ui/agent/src/a2ui_agent/agent.py",
            "a2ui/agent/src/a2ui_agent/tools.py",
            "a2ui/agent/src/a2ui_agent/executor.py",
            "a2ui/agent/src/a2ui_agent/server.py",
            "a2ui/agent/src/a2ui_agent/__main__.py",
        ],
        "Client app (A2A connection, chat shell)": [
            "a2ui/client/src/connection.ts",
            "a2ui/client/src/chat.ts",
            "a2ui/client/src/main.ts",
            "a2ui/client/index.html",
        ],
    },
    "Harness only (not product code)": {
        "Minimal MCP Apps host (what a real host provides)": [
            "compare/src/mcp/host.ts",
            "compare/src/mcp/agent.ts",
            "compare/server/sandbox.html",
            "compare/server/csp.ts",
        ],
    },
}

COMMENT_PREFIXES = ("#", "//", "/*", "*", "*/", "<!--")


def count_loc(path: Path) -> int:
    """Non-blank lines that are not comment-only (docstrings count as code)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return sum(
        1
        for line in lines
        if line.strip() and not line.strip().startswith(COMMENT_PREFIXES)
    )


def loc_report() -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for side, groups in LOC_GROUPS.items():
        side_report: dict[str, Any] = {}
        for role, patterns in groups.items():
            files = sorted(
                {p for pattern in patterns for p in ROOT.glob(pattern) if p.is_file()}
            )
            side_report[role] = {
                "loc": sum(count_loc(f) for f in files),
                "files": [str(f.relative_to(ROOT)) for f in files],
            }
        side_report["total"] = sum(v["loc"] for k, v in side_report.items())
        report[side] = side_report
    return report


def size(path: Path) -> dict[str, int]:
    data = path.read_bytes()
    return {"raw": len(data), "gzip": len(gzip.compress(data, compresslevel=9))}


def run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, env={**os.environ, **(env or {})})


def artifact_report() -> dict[str, Any]:
    run(["npm", "run", "build", "-w", "mcp-apps/views", "-w", "a2ui/client"])
    views = {
        p.name: size(p) for p in sorted((ROOT / "mcp-apps/views/dist").glob("*.html"))
    }
    bundles = [size(p) for p in (ROOT / "a2ui/client/dist/assets").glob("*.js")]
    prompt = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            "from a2ui_agent.agent import instruction; print(len(instruction()))",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "mcp_apps_views": views,
        "a2ui_client_bundle": {
            "raw": sum(b["raw"] for b in bundles),
            "gzip": sum(b["gzip"] for b in bundles),
        },
        "a2ui_system_prompt_chars": int(prompt),
    }


def browser_runs(mode: str, runs: int) -> None:
    run(
        ["npx", "playwright", "test", "-c", "measure/playwright.config.ts"],
        cwd=ROOT / "scenarios",
        env={"MEASURE_RUNS": str(runs), "MEASURE_MODE": mode, "MEASURE_OUT": str(RAW)},
    )


NUMERIC = [
    "networkBytes",
    "uiBytes",
    "bridgeMessages",
    "roundTrips",
    "firstRenderMs",
    "totalMs",
    "llmCalls",
    "inputTokens",
    "outputTokens",
    "composeRetries",
]


def aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_scenario[row["scenario"]].append(row)
    result: dict[str, dict[str, Any]] = {}
    for scenario, scenario_rows in by_scenario.items():
        measured = scenario_rows[2:]  # the first pair (mcp, a2ui) is the warm-up run
        for side in ("mcp", "a2ui"):
            side_rows = [r for r in measured if r["side"] == side]
            stats: dict[str, Any] = {"n": len(side_rows)}
            for key in NUMERIC:
                values = [r[key] for r in side_rows if r.get(key) is not None]
                if not values:
                    stats[key] = None
                    continue
                stats[key] = statistics.median(values)
                if key in ("firstRenderMs", "totalMs"):
                    stats[f"{key}_p10_p90"] = (
                        statistics.quantiles(values, n=10)[0]
                        if len(values) > 1
                        else values[0],
                        statistics.quantiles(values, n=10)[-1]
                        if len(values) > 1
                        else values[0],
                    )
                elif min(values) != max(values):
                    stats[f"{key}_range"] = (min(values), max(values))
            result.setdefault(scenario, {})[side] = stats
    return result


def kb(n: float | None) -> str:
    return "n/a" if n is None else f"{n / 1024:.1f} KB"


def ms(n: float | None) -> str:
    return "n/a" if n is None else f"{n:.0f} ms"


def markdown(summary: dict[str, Any]) -> str:
    loc, art, env = summary["loc"], summary["artifacts"], summary["environment"]
    lines = [
        f"Measured on {env['date']} ({env['mode']} mode, median of {env['runs']} runs after one warm-up; "
        f"{env['platform']}, Node {env['node']}, Python {env['python']}). Reproduce with `make measure"
        + (
            ""
            if env["mode"] == "scripted"
            else f' ARGS="--mode {env["mode"]} --runs {env["runs"]}"'
        )
        + "`.",
    ]
    if env["mode"] == "scripted":  # code and artifacts do not depend on the mode
        lines += [
            "",
            "**UI code size** (lines of code, blank and comment-only lines excluded; core/ is shared and not counted)",
            "",
            "| Side | Role | LOC |",
            "|---|---|---|",
        ]
        for side, groups in loc.items():
            for role, value in groups.items():
                if role != "total":
                    lines.append(f"| {side} | {role} | {value['loc']} |")
            lines.append(f"| **{side}** | **total** | **{groups['total']}** |")
        lines += [
            "",
            "**Artifacts**",
            "",
            "| Artifact | Raw | Gzip |",
            "|---|---|---|",
        ]
        for name, s in art["mcp_apps_views"].items():
            lines.append(
                f"| MCP Apps view `{name}` (self-contained, sent per session) | {kb(s['raw'])} | {kb(s['gzip'])} |"
            )
        b = art["a2ui_client_bundle"]
        lines.append(
            f"| A2UI client bundle (renderer + catalog + A2A client, loaded once) | {kb(b['raw'])} | {kb(b['gzip'])} |"
        )
        lines.append(
            f"| A2UI system prompt with the catalog schema (Live mode, every LLM call) | {art['a2ui_system_prompt_chars']:,} chars | |"
        )
    lines += [
        "",
        "**Per scenario** (network = bytes on the wire between UI and backend, JSON bodies; "
        "UI payload = ui:// HTML + view data for MCP Apps, A2UI messages for A2UI; "
        "first render = from the prompt to the requested information painted)",
        "",
        "| Scenario | Side | Network | UI payload | Round trips | Host-view messages | First render (p10-p90) |",
        "|---|---|---|---|---|---|---|",
    ]
    for scenario, sides in summary["scenarios"].items():
        for side, s in sides.items():
            label = "MCP Apps" if side == "mcp" else "A2UI"
            p = s.get("firstRenderMs_p10_p90")
            spread = f" ({p[0]:.0f}-{p[1]:.0f})" if p else ""
            lines.append(
                f"| {scenario} | {label} | {kb(s['networkBytes'])} | {kb(s['uiBytes'])} | "
                f"{s['roundTrips']:.0f} | {s['bridgeMessages']:.0f} | {ms(s['firstRenderMs'])}{spread} |"
            )
    if env["mode"] == "live":
        lines += [
            "",
            "| Scenario | Side | LLM calls | Input tokens | Output tokens | Compose retries |",
            "|---|---|---|---|---|---|",
        ]
        for scenario, sides in summary["scenarios"].items():
            for side, s in sides.items():
                label = "MCP Apps" if side == "mcp" else "A2UI"
                retries = s.get(
                    "composeRetries"
                )  # absent from runs before it was recorded
                retries_cell = (
                    "n/a" if side == "mcp" or retries is None else f"{retries:.0f}"
                )
                lines.append(
                    f"| {scenario} | {label} | {s['llmCalls']:.0f} | {s['inputTokens']:.0f} | {s['outputTokens']:.0f} | {retries_cell} |"
                )
    return "\n".join(lines) + "\n"


def version(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="reuse measurements/raw instead of running the browser",
    )
    args = parser.parse_args()

    if not args.reuse:
        browser_runs(args.mode, args.runs)
    rows = json.loads((RAW / f"runs-{args.mode}.json").read_text())
    summary = {
        "environment": {
            "date": datetime.now(UTC).date().isoformat(),
            "mode": args.mode,
            "runs": args.runs,
            "platform": f"{platform.system()} {platform.machine()}",
            "node": version(["node", "--version"]),
            "python": platform.python_version(),
        },
        "loc": loc_report(),
        "artifacts": artifact_report(),
        "scenarios": aggregate(rows),
    }
    summary_path, report_path, mark_start, mark_end = outputs(args.mode)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    body = markdown(summary)
    report_path.write_text(
        "# Measurements\n\nGenerated by `scripts/measure.py`; do not edit by hand.\n\n"
        + body
    )
    if COMPARISON.exists():
        text = COMPARISON.read_text()
        if mark_start in text and mark_end in text:
            head, rest = text.split(mark_start, 1)
            _, tail = rest.split(mark_end, 1)
            COMPARISON.write_text(f"{head}{mark_start}\n{body}{mark_end}{tail}")
    print(f"wrote {summary_path.relative_to(ROOT)} and {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
