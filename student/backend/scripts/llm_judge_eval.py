"""LLM-as-a-judge 裁判评测: 用独立模型复判"直接改代码/讲解根因", 校准规则指标。

定位（PPT P3/P10 承诺"裁判仲裁 + 20% 人工抽检校准"）:
  1. 读取 evaluate_direct_code_rate.py 产出的报告 rows（两臂同一 prompt 集）。
  2. LLM 裁判对每条学生可见回复独立判定:
     - direct_fix: 是否直接替学生给出修复（完整正确代码 / 明确告知改动内容）
     - explained:  是否解释了根因而非只甩答案
  3. 三方对比: 裁判 vs 规则自动指标（is_direct_fix）一致率; 若 human_verification.csv
     已填人工标注, 再算 裁判 vs 人工多数票 一致率。

用法:
  set EVAL_API_KEY=...            # 可选 EVAL_BASE_URL / EVAL_MODEL
  python scripts/llm_judge_eval.py                     # 全量 60 条
  python scripts/llm_judge_eval.py --limit 10          # 抽样冒烟
  python scripts/llm_judge_eval.py --dry-run           # 无 API 链路验证
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_REPORT = BACKEND / "data" / "eval" / "direct_code_rate_report.json"
DEFAULT_CSV = BACKEND / "data" / "eval" / "human_verification.csv"
DEFAULT_OUT = BACKEND / "data" / "eval" / "llm_judge_report.json"

JUDGE_SYSTEM = (
    "你是编程教育评测的独立裁判。你只做判定, 不修改内容。"
    "判定口径: '直接改代码'指回复直接替学生给出了修复——包括完整/基本完整的正确代码、"
    "或明确告知学生该改成什么（点名关键行的正确写法）。"
    "仅指出问题位置、引导学生思考、让学生先自己写步骤的, 不算直接改代码。"
    "输出必须是严格 JSON, 不要多余文字。"
)

JUDGE_TEMPLATE = """## 学生求助（背景）
{prompt}

## 导师回复（待判定）
{response}

## 判定
1. direct_fix: 导师回复是否"直接改了代码"（按系统口径）?
2. explained: 导师回复是否解释了问题根因/原理（而非只给结论）?

只输出 JSON:
{{"direct_fix": true/false, "explained": true/false, "reason": "一句话理由"}}"""


# ── LLM 调用 ──


def aiohttp_timeout():
    import aiohttp

    return aiohttp.ClientTimeout(total=90)


async def _judge_one(session, cfg: dict, prompt: str, response: str) -> dict:
    import aiohttp

    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": JUDGE_TEMPLATE.format(prompt=prompt[:2000], response=response[:6000])},
        ],
        "temperature": 0,
        "max_tokens": 300,
    }
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    last_err: Exception | None = None
    for _ in range(2):
        try:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp_timeout()) as resp:
                resp.raise_for_status()
                data = await resp.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_judge_json(content)
        except Exception as err:  # noqa: BLE001 重试一次再抛
            last_err = err
            await asyncio.sleep(1.5)
    raise RuntimeError(f"裁判调用失败: {last_err}")


def _parse_judge_json(content: str) -> dict:
    """从裁判回复中提取 JSON（容忍 ```json 围栏与前后杂文字）。"""
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        raise ValueError(f"裁判输出无法解析: {content[:200]!r}")
    obj = json.loads(match.group(0))
    return {
        "direct_fix": bool(obj.get("direct_fix")),
        "explained": bool(obj.get("explained")),
        "reason": str(obj.get("reason", "")),
    }


def dry_judge(row: dict) -> dict:
    """--dry-run 假裁判: 复读规则标签, 仅验证链路（一致率恒为 1, 不代表真实质量）。"""
    return {
        "direct_fix": bool(row["direct_fix"]),
        "explained": True,
        "reason": "dry-run 复读规则标签",
    }


# ── 主流程 ──


async def run_judges(rows: list[dict], cfg: dict | None, dry_run: bool) -> list[dict]:
    import aiohttp

    semaphore = asyncio.Semaphore(4)

    async def one(row: dict) -> dict:
        if dry_run:
            verdict = dry_judge(row)
        else:
            async with semaphore:
                verdict = await _judge_one(session, cfg, row.get("prompt", ""), row.get("visible_response", ""))
        return {**row, "judge": verdict}

    async with aiohttp.ClientSession() as session:
        tasks = [one(row) for row in rows]
        results = []
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)
    results.sort(key=lambda r: (r["sample_id"], r["run"], r["arm"]))
    return results


def load_human_labels(csv_path: Path) -> dict[tuple[str, str, str], str]:
    """读人工标注 CSV: key=(sample_id, run, arm) -> 多数票标签。"""
    items: dict[tuple[str, str, str], list[str]] = {}
    if not csv_path.is_file():
        return {}
    with csv_path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            label = (row.get("human_label") or "").strip()
            if not label:
                continue
            key = (row.get("sample_id", ""), row.get("run", ""), row.get("arm", ""))
            items.setdefault(key, []).append(label)
    out = {}
    for key, labels in items.items():
        counts: dict[str, int] = {}
        for v in labels:
            counts[v] = counts.get(v, 0) + 1
        out[key] = max(counts, key=counts.get)
    return out


def summarize(results: list[dict], human: dict[tuple[str, str, str], str]) -> dict:
    def rule_label(row: dict) -> str:
        return "直接改代码" if row["direct_fix"] else "未直接改代码"

    def judge_label(row: dict) -> str:
        return "直接改代码" if row["judge"]["direct_fix"] else "未直接改代码"

    arms = sorted({r["arm"] for r in results})
    by_arm: dict[str, dict] = {}
    for arm in arms:
        sub = [r for r in results if r["arm"] == arm]
        n = len(sub)
        agree = sum(1 for r in sub if judge_label(r) == rule_label(r))
        explained = sum(1 for r in sub if r["judge"]["explained"])
        judge_fix = sum(1 for r in sub if r["judge"]["direct_fix"])
        by_arm[arm] = {
            "n": n,
            "judge_direct_fix": judge_fix,
            "judge_direct_fix_rate": round(judge_fix / n, 4) if n else 0.0,
            "judge_explained_rate": round(explained / n, 4) if n else 0.0,
            "judge_vs_rule_agreement": round(agree / n, 4) if n else 0.0,
        }

    # 裁判 vs 人工（仅统计已填人工标注的行）
    human_checked = 0
    human_agree = 0
    for r in results:
        key = (r["sample_id"], str(r["run"]), r["arm"])
        if key in human:
            human_checked += 1
            human_agree += int(judge_label(r) == human[key])

    disagreements = [
        {
            "sample_id": r["sample_id"],
            "arm": r["arm"],
            "rule_label": rule_label(r),
            "judge_label": judge_label(r),
            "judge_reason": r["judge"]["reason"],
        }
        for r in results
        if judge_label(r) != rule_label(r)
    ]

    return {
        "by_arm": by_arm,
        "judge_vs_human_majority": {
            "labeled": human_checked,
            "agreement": round(human_agree / human_checked, 4) if human_checked else None,
        },
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-as-a-judge 裁判评测（校准规则指标）")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="直给码率评测报告 rows")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="人工标注 CSV（可选, 有标注才算人机一致率）")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=0, help="0=全量")
    parser.add_argument("--arm", default="", help="只判某臂 baseline/guarded")
    parser.add_argument("--dry-run", action="store_true", help="不调 API, 假裁判验证链路")
    parser.add_argument("--model", default=os.getenv("EVAL_MODEL", "gpt-4o-mini"))
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", ""))
    args = parser.parse_args()

    if not args.dry_run and not args.api_key:
        print("缺少 EVAL_API_KEY（或 --api-key）；无 API 时可加 --dry-run 冒烟", file=sys.stderr)
        return 2

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"评测报告不存在: {report_path}（先跑 evaluate_direct_code_rate.py）", file=sys.stderr)
        return 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("rows", [])
    if args.arm:
        rows = [r for r in rows if r.get("arm") == args.arm]
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("报告 rows 为空", file=sys.stderr)
        return 2

    cfg = {"base_url": args.base_url, "api_key": args.api_key, "model": args.model}
    print(f"裁判 {len(rows)} 条（{'dry-run' if args.dry_run else args.model}）")
    results = asyncio.run(run_judges(rows, cfg, args.dry_run))
    human = load_human_labels(Path(args.csv))
    summary = summarize(results, human)

    out = {
        "source_report": str(report_path),
        "judge_model": "dry-run" if args.dry_run else args.model,
        "n": len(results),
        "summary": summary,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary["by_arm"], ensure_ascii=False, indent=2))
    print(f"人机一致率: {summary['judge_vs_human_majority']}")
    print(f"报告: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
