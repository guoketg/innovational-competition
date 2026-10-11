"""基于公开数据集的"导师直接改代码次数"量化评测。

数据集: Socratic Debugging Benchmark (BEA@ACL'23 / SIGCSE'24)
  https://github.com/taisazero/socratic-debugging-benchmark
  已内置子集: data/eval/socratic_debugging_benchmark/evaluation_dataset（150 个问题）

评测协议:
  1. 从数据集解析: 题目 / 学生带 bug 的代码 / 标准修复(bug_fixes) / 最终正确代码。
  2. 构造学生求助提示(原始求助话术 + bug 代码), 让导师模型作答(每次生成复用两组)。
  3. 基线组 = 模型原始输出; 护栏组 = 经 answer_guard.apply_guard 过滤后的学生可见输出。
  4. 核心指标"直接改代码" = 回答中出现标准修复内容(或给出≥85%相似的完整正确代码)。
     统计两组的直接改代码次数/比例, 以及护栏 R1 拦截、R2 记录次数。

用法:
  set EVAL_API_KEY=...            # 可选 EVAL_BASE_URL / EVAL_MODEL
  python scripts/evaluate_direct_code_rate.py --limit 30 --runs 3
  python scripts/evaluate_direct_code_rate.py --dry-run            # 无 API 冒烟
  python scripts/evaluate_direct_code_rate.py --aggregate-csv data/eval/human_verification_xxx.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from services.answer_guard_service import (  # noqa: E402
    apply_guard,
    evaluate,
    extract_code_blocks,
)

DEFAULT_DATASET_DIR = BACKEND / "data" / "eval" / "socratic_debugging_benchmark" / "evaluation_dataset"
DEFAULT_REPORT = BACKEND / "data" / "eval" / "direct_code_rate_report.json"
DEFAULT_CSV = BACKEND / "data" / "eval" / "human_verification.csv"

SYSTEM_PROMPT = (
    "你是一位耐心的编程导师，帮助学生调试代码、理解问题。"
    "如实回答学生的问题。"
)

# ── 数据集解析 ──


@dataclass
class ProblemCase:
    file: str
    problem: str
    bug_code: str
    final_code: str
    fix_targets: list[str] = field(default_factory=list)
    user_turns: list[str] = field(default_factory=list)
    prompt: str = ""


def _section(text: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    return match.group(1).strip() if match else ""


def _strip_numbering(code: str) -> str:
    return "\n".join(re.sub(r"^\d+\.\s?", "", line) for line in code.splitlines())


def _significant_norm_lines(text: str) -> set[str]:
    out: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if len(line) < 5:
            continue
        if line.startswith(("#", "//", "/*", "*", "--")):
            continue
        out.add(re.sub(r"\s+", "", line))
    return out


def _parse_fix_targets(bug_fixes: str) -> list[str]:
    targets = []
    for line in bug_fixes.splitlines():
        match = re.search(r"Replace\s+`(.+?)`\s+with\s+`(.+?)`\s+on line", line)
        if match:
            targets.append(match.group(2).strip())
    return targets


def parse_problem_file(path: Path) -> ProblemCase | None:
    raw = path.read_text(encoding="utf-8")
    problem = _section(raw, "problem")
    bug_code_raw = _section(raw, "bug_code")
    bug_fixes = _section(raw, "bug_fixes")
    dialogue = _section(raw, "dialogue")
    if not (problem and bug_code_raw and dialogue):
        return None

    bug_code = _strip_numbering(bug_code_raw)
    fix_targets = _parse_fix_targets(bug_fixes)

    # 最终正确代码: 对话中最后一个 <code> 块; 没有则用首个修复替换 bug 代码
    code_blocks = re.findall(r"<code>(.*?)</code>", dialogue, re.S)
    final_code = _strip_numbering(code_blocks[-1]).strip() if code_blocks else ""
    if len(_significant_norm_lines(final_code)) < 5 and fix_targets:
        corrected = bug_code
        for target in fix_targets:
            source = _fix_source_for(bug_fixes, target)
            if source and source in corrected:
                corrected = corrected.replace(source, target)
        final_code = corrected

    user_turns = [
        line[len("User:"):].strip()
        for line in dialogue.splitlines()
        if line.startswith("User: ")
    ]
    if not user_turns or len(_significant_norm_lines(final_code)) < 3:
        return None

    opener = "\n".join(user_turns[:2])
    prompt = (
        f"{opener}\n\n"
        f"这是我现在的代码：\n```python\n{bug_code}\n```\n"
        f"请帮我看看问题出在哪里。"
    )
    return ProblemCase(
        file=path.name,
        problem=problem,
        bug_code=bug_code,
        final_code=final_code,
        fix_targets=fix_targets,
        user_turns=user_turns,
        prompt=prompt,
    )


def _fix_source_for(bug_fixes: str, target: str) -> str | None:
    for line in bug_fixes.splitlines():
        match = re.search(r"Replace\s+`(.+?)`\s+with\s+`(.+?)`\s+on line", line)
        if match and match.group(2).strip() == target:
            return match.group(1).strip()
    return None


def load_cases(dataset_dir: Path) -> list[ProblemCase]:
    cases = []
    for path in sorted(dataset_dir.glob("*.txt")):
        case = parse_problem_file(path)
        if case:
            cases.append(case)
    return cases


# ── 指标 ──


def is_direct_fix(response: str, case: ProblemCase) -> bool:
    """回答是否'直接改了代码': 告知标准修复内容, 或给出基本完整的正确代码。"""
    norm = re.sub(r"\s+", "", response or "")
    for target in case.fix_targets:
        t = re.sub(r"\s+", "", target)
        if t and t in norm:
            return True
    # 兜底: 给出基本完整的正确代码也算直接改代码
    # (覆盖数据集 bug_fixes 与最终代码写法不一致, 如 `n-1 + n-2` 与 `n-2 + n-1` 顺序互换)
    final_lines = _significant_norm_lines(case.final_code)
    if not final_lines:
        return False
    for block in extract_code_blocks(response or ""):
        block_lines = _significant_norm_lines(block["code"])
        if not block_lines:
            continue
        recall = len(block_lines & final_lines) / len(final_lines)
        if recall >= 0.85:
            return True
    return False


def gave_long_code(response: str) -> bool:
    """回答是否给出大段代码（R2 口径: 单块≥15 行有效代码）。"""
    for block in extract_code_blocks(response or ""):
        lines = [ln for ln in block["code"].splitlines() if ln.strip()]
        if len(lines) >= 15:
            return True
    return False


# ── LLM 调用 ──


async def _chat_once(session, base_url: str, api_key: str, model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 800,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = base_url.rstrip("/") + "/chat/completions"
    async with session.post(url, json=payload, headers=headers, timeout=aiohttp_timeout()) as resp:
        resp.raise_for_status()
        data = await resp.json()
    return data["choices"][0]["message"]["content"]


def aiohttp_timeout():
    import aiohttp

    return aiohttp.ClientTimeout(total=90)


async def chat(session, cfg: dict, prompt: str) -> str:
    import aiohttp

    last_err: Exception | None = None
    for _ in range(2):
        try:
            return await _chat_once(session, cfg["base_url"], cfg["api_key"], cfg["model"], prompt)
        except Exception as err:  # noqa: BLE001 重试一次再抛出
            last_err = err
            await asyncio.sleep(1.5)
    raise RuntimeError(f"LLM 调用失败: {last_err}")


def stub_response(case: ProblemCase) -> str:
    """--dry-run 假响应: 模拟一个'直接甩完整答案'的模型, 用于验证评测链路。"""
    return f"问题在你的代码里，我直接帮你改好了：\n```python\n{case.final_code}\n```\n"


# ── 评测主流程 ──


async def run_evaluation(cases: list[ProblemCase], runs: int, cfg: dict | None, dry_run: bool) -> list[dict]:
    import aiohttp

    rows: list[dict] = []
    semaphore = asyncio.Semaphore(4)

    async def one(case: ProblemCase, run_idx: int) -> list[dict]:
        if dry_run:
            raw = stub_response(case)
        else:
            async with semaphore:
                raw = await chat(session, cfg, case.prompt)
        verdict_raw = evaluate(raw, case.final_code)
        visible, verdict_guarded = apply_guard(raw, case.final_code)
        base = {
            "sample_id": case.file,
            "run": run_idx,
            "prompt": case.prompt,
            "raw_response": raw,
        }
        return [
            {
                **base,
                "arm": "baseline",
                "visible_response": raw,
                "direct_fix": is_direct_fix(raw, case),
                "long_code": gave_long_code(raw),
                "guard_severity": verdict_raw.severity,
                "guard_blocked": verdict_raw.blocked,
            },
            {
                **base,
                "arm": "guarded",
                "visible_response": visible,
                "direct_fix": is_direct_fix(visible, case),
                "long_code": gave_long_code(visible),
                "guard_severity": verdict_guarded.severity,
                "guard_blocked": verdict_guarded.blocked,
            },
        ]

    async with aiohttp.ClientSession() as session:
        tasks = [one(case, run_idx) for case in cases for run_idx in range(1, runs + 1)]
        for coro in asyncio.as_completed(tasks):
            rows.extend(await coro)
    rows.sort(key=lambda r: (r["sample_id"], r["run"], r["arm"]))
    return rows


def summarize(rows: list[dict]) -> dict:
    def arm_stats(arm: str) -> dict:
        sub = [r for r in rows if r["arm"] == arm]
        n = len(sub)
        return {
            "n": n,
            "direct_fix_count": sum(r["direct_fix"] for r in sub),
            "direct_fix_rate": round(sum(r["direct_fix"] for r in sub) / n, 4) if n else 0.0,
            "long_code_count": sum(r["long_code"] for r in sub),
            "guard_blocked_count": sum(r["guard_blocked"] for r in sub),
            "guard_partial_count": sum(1 for r in sub if r["guard_severity"] == "partial"),
        }

    return {"baseline": arm_stats("baseline"), "guarded": arm_stats("guarded")}


# ── 人工验证 CSV ──


def export_human_csv(rows: list[dict], path: Path, sample_n: int) -> int:
    """分层抽样基线/护栏两组各半, 导出人工标注表。返回导出行数。"""
    baseline = [r for r in rows if r["arm"] == "baseline"]
    guarded = [r for r in rows if r["arm"] == "guarded"]
    half = max(1, sample_n // 2)
    picked = baseline[:half] + guarded[:half]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "sample_id", "run", "arm", "auto_label", "guard_severity",
        "annotator", "human_label", "response",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in picked:
            writer.writerow({
                "sample_id": row["sample_id"],
                "run": row["run"],
                "arm": row["arm"],
                "auto_label": "直接改代码" if row["direct_fix"] else "未直接改代码",
                "guard_severity": row["guard_severity"],
                "annotator": "",
                "human_label": "",
                "response": row["visible_response"],
            })
    return len(picked)


def aggregate_human_csv(path: Path) -> dict:
    """汇总最多 3 人的标注: 逐条多人一致率 + 自动指标与人工多数票一致率。"""
    items: dict[str, list[tuple[str, str]]] = {}
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            annotator = (row.get("annotator") or "").strip()
            label = (row.get("human_label") or "").strip()
            if not annotator or not label:
                continue
            key = f"{row['sample_id']}|{row.get('run', '')}|{row['arm']}"
            items.setdefault(key, []).append((annotator, label))

    labeled_items = 0
    unanimous = 0
    pair_total = 0
    pair_agree = 0
    auto_keys = {}
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            key = f"{row['sample_id']}|{row.get('run', '')}|{row['arm']}"
            auto_keys[key] = (row.get("auto_label") or "").strip()

    auto_correct = 0
    auto_checked = 0
    for key, labels in items.items():
        labeled_items += 1
        vals = [label for _, label in labels]
        if len(set(vals)) == 1:
            unanimous += 1
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                pair_total += 1
                pair_agree += int(vals[i] == vals[j])
        # 多数票 vs 自动指标
        counts: dict[str, int] = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        majority = max(counts, key=counts.get)
        auto = auto_keys.get(key, "")
        if auto:
            auto_checked += 1
            auto_correct += int(auto == majority)

    return {
        "annotators": sorted({a for labels in items.values() for a, _ in labels}),
        "labeled_items": labeled_items,
        "unanimous_items": unanimous,
        "pairwise_agreement": round(pair_agree / pair_total, 4) if pair_total else 0.0,
        "auto_vs_human_majority_agreement": round(auto_correct / auto_checked, 4) if auto_checked else 0.0,
    }


# ── CLI ──


def main() -> int:
    parser = argparse.ArgumentParser(description="公开数据集上的'直接改代码次数'量化评测")
    parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR))
    parser.add_argument("--limit", type=int, default=30, help="抽样问题数")
    parser.add_argument("--runs", type=int, default=1, help="每个问题重复生成次数")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="不调 API, 用假响应验证链路")
    parser.add_argument("--model", default=os.getenv("EVAL_MODEL", "gpt-4o-mini"))
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", ""))
    parser.add_argument("--out", default=str(DEFAULT_REPORT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--human-sample", type=int, default=30, help="人工抽检导出行数(两组各半)")
    parser.add_argument("--aggregate-csv", default="", help="汇总已填好的人工标注 CSV 后退出")
    args = parser.parse_args()

    if args.aggregate_csv:
        summary = aggregate_human_csv(Path(args.aggregate_csv))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not args.dry_run and not args.api_key:
        print("缺少 EVAL_API_KEY（或 --api-key）；无 API 时可加 --dry-run 冒烟", file=sys.stderr)
        return 2

    dataset_dir = Path(args.dataset_dir)
    cases = load_cases(dataset_dir)
    if not cases:
        print(f"数据集为空: {dataset_dir}", file=sys.stderr)
        return 2
    random.Random(args.seed).shuffle(cases)
    cases = cases[: max(1, args.limit)]
    print(f"样本 {len(cases)} 题 x {args.runs} 轮（{'dry-run' if args.dry_run else args.model}）")

    cfg = {"base_url": args.base_url, "api_key": args.api_key, "model": args.model}
    rows = asyncio.run(run_evaluation(cases, args.runs, cfg, args.dry_run))
    summary = summarize(rows)
    report = {
        "dataset": str(dataset_dir),
        "model": "dry-run" if args.dry_run else args.model,
        "limit": len(cases),
        "runs": args.runs,
        "summary": summary,
        "reduction": {
            "direct_fix_baseline": summary["baseline"]["direct_fix_count"],
            "direct_fix_guarded_visible": summary["guarded"]["direct_fix_count"],
        },
        "rows": rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    picked = export_human_csv(rows, Path(args.csv), args.human_sample)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"报告: {out_path}")
    print(f"人工抽检表 {picked} 行: {args.csv}（填 annotator / human_label 后用 --aggregate-csv 汇总）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
