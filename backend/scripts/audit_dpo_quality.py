"""DPO 数据质量审计（为 PPT「质检矩阵通过率表」提供可复现出处）。

ppt_structure.md 曾引用 泄漏率 0.008 / 违规率 0.011 / 讲解率 1.0 / 呼应率 1.0，
但全仓无任何脚本产出这些数字。本脚本对最终产物 dpo_pairs.jsonl 复检，输出：
  leak_rate            round1（含 concept）chosen 侧被线上护栏 R1 拦截的比例——chosen 不应泄漏
  violation_rate       按 build_dpo_pairs.validate_pair / validate_general 复检失败的比例
  explanation_pass_rate round2/C-attempt chosen 含讲解的比例（plan §3.8 硬规则）
  hint_distribution    hint_level 分布（提示层级，plan 3.8；PPT 所谓「呼应层级」的实体）

参考解重建（行内不存 ref）：
  codelab/boundary → REFERENCE_SOLUTIONS[level]
  socratic/redteam  → prompt 内 code 块与数据集比对：
                       prompt_final（round2 attempt 命中）> bug_unique（bug_code 唯一解）
                       > rejected_argmax（同 bug 候选中 recall(rejected) 最大者，
                         round1 rejected 本就是泄题回复，取其命中的参考解）
                       > family_argmax（同族候选 argmax）
                       仍无法解析的行排除出 ref 类指标并计数。

用法：
  python scripts/audit_dpo_quality.py            # 输出 data/dpo/dpo_quality_audit.json
  python scripts/audit_dpo_quality.py --dry-run  # 只跑 G 层快速冒烟
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from build_dpo_pairs import (  # noqa: E402
    DEFAULT_DATASET_DIR,
    REFERENCE_SOLUTIONS,
    ends_with_question,
    has_explanation,
    load_reference_solutions,
    family_of,
    validate_general,
    validate_pair,
    PairDraft,
)
from evaluate_direct_code_rate import load_cases  # noqa: E402
from services.answer_guard_service import apply_guard, evaluate  # noqa: E402

DEFAULT_PAIRS = BACKEND / "data" / "dpo" / "dpo_pairs.jsonl"
DEFAULT_OUT = BACKEND / "data" / "dpo" / "dpo_quality_audit.json"


def _prompt_texts(prompt) -> str:
    """prompt 可能是 str 或 messages 列表（多轮格式）。"""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, list):
        return "\n".join(str(m.get("content", "")) for m in prompt if isinstance(m, dict))
    return ""


def _code_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:python|cpp|c\+\+)?\n(.*?)```", text or "", re.S)


def build_ref_index(cases) -> tuple[dict, dict, dict]:
    """(bug_code -> set(final), family -> set(final), bug_code -> case)"""
    by_bug: dict[str, set[str]] = collections.defaultdict(set)
    by_family: dict[str, set[str]] = collections.defaultdict(set)
    bug_case: dict[str, object] = {}
    for c in cases:
        by_bug[c.bug_code].add(c.final_code)
        by_family[family_of(c.file)].add(c.final_code)
        bug_case.setdefault(c.bug_code, c)
    return by_bug, by_family, bug_case


def resolve_ref(row: dict, by_bug, by_family, finals_in_prompt: set[str]) -> tuple[str, str]:
    """返回 (ref, 解析方式)。"""
    src = row.get("source")
    if src in ("codelab", "boundary") and row.get("family", "").startswith("codelab_"):
        ref = REFERENCE_SOLUTIONS.get(row["family"].split("_", 1)[1])
        if ref:
            return ref, "codelab"

    prompt = _prompt_texts(row.get("prompt"))
    # 1) round2 的 attempt 块就是 final_code，直接命中
    for block in _code_blocks(prompt):
        bs = block.strip()
        if bs in finals_in_prompt:
            return bs, "prompt_final"
        for f in finals_in_prompt:
            if f and f in bs:
                return f, "prompt_final"
    # 2) bug_code 唯一解
    candidates: set[str] = set()
    for block in _code_blocks(prompt):
        candidates |= by_bug.get(block.strip(), set())
    method = "bug_unique"
    if not candidates:
        candidates = by_family.get(row.get("family", ""), set())
        method = "family_argmax"
    if not candidates:
        return "", "unresolved"
    if len(candidates) == 1:
        return next(iter(candidates)), method
    # 3) 同 bug 多解：round1 rejected 本就是泄题回复，取其 recall 最大的候选为参考解
    rejected = row.get("rejected", "") or ""
    best, best_score = "", -1.0
    for cand in candidates:
        score = float(evaluate(rejected, cand).metrics.get("max_recall", 0) or 0)
        if score > best_score:
            best, best_score = cand, score
    return best, "rejected_argmax" if method == "bug_unique" else "family_argmax"


def main() -> int:
    parser = argparse.ArgumentParser(description="DPO 数据质量审计（泄漏/违规/讲解/层级）")
    parser.add_argument("--pairs", default=str(DEFAULT_PAIRS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--dry-run", action="store_true", help="只复检 G 层（不加载参考解/数据集）")
    args = parser.parse_args()

    rows = [json.loads(line) for line in Path(args.pairs).read_text(encoding="utf-8").splitlines() if line.strip()]

    if args.dry_run:
        by_bug, by_family, finals, bug_case = {}, {}, set(), {}
    else:
        REFERENCE_SOLUTIONS.clear()
        REFERENCE_SOLUTIONS.update(load_reference_solutions())
        cases = load_cases(DEFAULT_DATASET_DIR)
        # DS&A 补充素材（与 build_dpo_pairs 同源，_buggy 族只存在于该目录）
        ds_a = BACKEND / "data" / "dpo" / "materials_ds_a"
        if ds_a.is_dir():
            cases = cases + load_cases(ds_a)
        by_bug, by_family, bug_case = build_ref_index(cases)
        finals = {c.final_code for c in cases}

    resolve_stats: collections.Counter = collections.Counter()
    ref_unresolved = 0
    leak_checked = leak_hits = 0
    violation_fails: list[dict] = []
    explanation_checked = explanation_pass = 0
    hint_dist: collections.Counter = collections.Counter()

    for row in rows:
        layer, rnd = row.get("layer"), row.get("round")
        subtype = row.get("subtype") or ""
        chosen, rejected = row.get("chosen", "") or "", row.get("rejected", "") or ""
        hint_dist[str(row.get("hint_level", 0))] += 1

        # ── 讲解率（plan §3.8：round2/C-attempt chosen 禁止裸代码）──
        if (layer in ("P", "A") and rnd == 2) or (layer == "C" and subtype == "attempt"):
            explanation_checked += 1
            explanation_pass += bool(has_explanation(chosen))

        # ── 泄漏率：round1 引导类 chosen 不应命中线上 R1。
        #    concept（概念直答）按 plan「概念类问题照常直接回答」不适用 R1，排除。──
        if layer in ("P", "A", "X") and rnd == 1 and subtype != "concept":
            ref, method = resolve_ref(row, by_bug, by_family, finals)
            resolve_stats[method] += 1
            if not ref:
                ref_unresolved += 1
                continue
            leak_checked += 1
            verdict = apply_guard(chosen, ref)[1]
            if getattr(verdict, "blocked", False):
                leak_hits += 1

        # ── 违规率：按质检矩阵复检 ──
        if layer == "G":
            ok, why = validate_general(chosen, rejected)
        elif layer in ("P", "A", "C", "X"):
            ref, _method = resolve_ref(row, by_bug, by_family, finals)
            if not ref and layer != "C":
                continue  # ref 类复检项跳过（已在 ref_unresolved 计数外，C 层 concept 不用 ref）
            # meta["case"] 影响 is_direct_fix 分支（与原构建同判据），按 prompt 内 bug_code 重建
            case_obj = None
            for b in _code_blocks(_prompt_texts(row.get("prompt"))):
                case_obj = bug_case.get(b.strip())
                if case_obj:
                    break
            draft = PairDraft(
                layer=layer, source=row.get("source", ""), family=row.get("family", ""),
                round=rnd or 0, lang=row.get("lang", "zh"), ref=ref,
                user_prompt="", chosen=chosen, rejected=rejected, subtype=subtype,
                meta={"case": case_obj} if case_obj else {},
            )
            ok, why = validate_pair(draft)
        else:
            ok, why = False, f"未知层 {layer}"
        if not ok:
            violation_fails.append({"layer": layer, "round": rnd, "subtype": subtype,
                                    "family": row.get("family", ""), "reason": why})

    n = len(rows)
    audit = {
        "pairs_file": str(Path(args.pairs).name),
        "n_pairs": n,
        "dry_run": args.dry_run,
        "definitions": {
            "leak_rate": "round1 引导类 chosen（排除概念直答）命中线上护栏 R1 的比例；chosen 侧不应泄漏",
            "violation_rate": "按 build_dpo_pairs.validate_pair / validate_general 对最终 pairs 全量复检的失败比例",
            "explanation_pass_rate": "round2 / C-attempt chosen 去代码后含讲解表述的比例（plan §3.8 硬规则）",
            "hint_distribution": "hint_level（提示层级 1-4 / 0=无）分布，即 PPT 所谓「呼应层级」的实体",
        },
        "leak_rate": round(leak_hits / leak_checked, 4) if leak_checked else None,
        "leak_checked": leak_checked,
        "leak_hits": leak_hits,
        "violation_rate": round(len(violation_fails) / n, 4) if n else None,
        "violation_fails": len(violation_fails),
        "violation_examples": violation_fails[:20],
        "explanation_pass_rate": round(explanation_pass / explanation_checked, 4) if explanation_checked else None,
        "explanation_checked": explanation_checked,
        "hint_distribution": dict(sorted(hint_dist.items())),
        "ref_resolution": dict(resolve_stats),
        "ref_unresolved": ref_unresolved,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in audit.items() if k != "violation_examples"},
                     ensure_ascii=False, indent=2))
    if violation_fails:
        print("\n违规样例（前 10）:")
        for item in violation_fails[:10]:
            print(" ", item)
    print(f"\n审计报告: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
