# -*- coding: utf-8 -*-
"""DPO 存量对转换：文本对 → 工具决策对（plan §3.10 ②，不重新生成对话）。

chosen/rejected 改写为三工具调用 JSON（give_hint / give_answer / modify_code），
新增 tool_decision 字段；layer / source / family 不变。
不涉工具的场景（概念直答、G 层通用）保留纯文本对，防学成「凡事必调工具」。

映射：
  P/A/X round1   chosen=give_hint(level,text)          rejected=give_answer(code,缺why)
                 或 modify_code(patch,首轮=违规)       tool_decision=hint_vs_answer|hint_vs_modify
  P/A round2     chosen=give_answer(code,why) 或       rejected=give_hint(释放条件已满足=违规)
                 modify_code(patch,why) 轮换           tool_decision=answer_vs_hint|modify_vs_hint
  C attempt      同 round2                             同上
  C/A concept    纯文本保留                            tool_decision=text_only
  G              纯文本保留                            tool_decision=text_only

质检（查表，build_dpo_pairs.validate_tool_call）：
  chosen 侧零违规；rejected 侧至少命中一条违规（否则方向反了）。
不合格对丢弃并计数。转换后 20% 人工抽检（--sample 输出抽样文件）。

用法：
  python scripts/convert_dpo_to_tools.py                 # train + eval 全量转换
  python scripts/convert_dpo_to_tools.py --sample 0.2    # 额外输出 20%% 抽检文件
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from build_dpo_pairs import (  # noqa: E402
    make_tool_call,
    parse_tool_call,
    strip_code,
    validate_tool_call,
)
from services.answer_guard_service import extract_code_blocks  # noqa: E402

DEFAULT_OUT_DIR = BACKEND / "data" / "dpo"


def extract_code(text: str) -> str:
    """取回复中最长的代码块（即完整实现）；无代码块时退化为去围栏文本（泄题 rejected 兜底）。

    教学式回复常含多个代码块（完整实现 + diff 片段 + 测试调用），全拼接会把
    碎屑混进 code/patch。抽检统计：最长块几乎总是完整实现，其余片段的讲解
    在 why（strip_code 后正文）中仍有叙述，丢弃不损语义。
    """
    blocks = [b["code"].strip() for b in extract_code_blocks(text or "") if b.get("code", "").strip()]
    if blocks:
        return max(blocks, key=len)
    return (text or "").strip()


def clean_why(text: str) -> str:
    """strip_code 移除围栏代码后正文会留下连续空行，压缩为单个空行。"""
    import re
    out = re.sub(r"(?:[ \t]*\n){3,}", "\n\n", (text or "").strip())
    out = re.sub(r"[ \t]+\n", "\n", out)
    return out.strip()


def alt(seed: str) -> bool:
    """确定性轮换：同 seed 恒定，避免每次转换漂移。"""
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % 2 == 0


def convert_row(row: dict, stats: dict) -> dict | None:
    layer = row.get("layer")
    subtype = row.get("subtype") or ""
    rnd = int(row.get("round") or 0)
    chosen, rejected = row["chosen"], row["rejected"]
    seed = f"{row.get('family')}|{layer}|{rnd}|{subtype}|{row.get('lang')}|{len(chosen)}"

    # 不涉工具场景：概念直答 + G 层通用 + A 层反谄媚 → 纯文本保留
    if layer == "G" or subtype in ("concept", "sycophancy"):
        out = dict(row)
        out["tool_decision"] = "text_only"
        stats["text_only"] += 1
        return out

    release_expected = rnd == 2 or layer == "C"  # round2 / C：学生已展示尝试，释放条件已满足

    if release_expected:
        # chosen：给码（give_answer / modify_code 轮换，均带 why=讲解）
        why = clean_why(strip_code(chosen))
        code = extract_code(chosen)
        if alt(seed):
            chosen_tool = "modify_code"
            chosen_call = {"tool": chosen_tool, "args": {"patch": code, "why": why}}
            decision = "modify_vs_hint"
        else:
            chosen_tool = "give_answer"
            chosen_call = {"tool": chosen_tool, "args": {"code": code, "why": why}}
            decision = "answer_vs_hint"
        # rejected：过度引导的 hint（释放后仍 hint = 违规）
        rejected_call = {"tool": "give_hint", "args": {"level": 1, "text": clean_why(strip_code(rejected))}}
    else:
        # round1（含 bypass/X）：chosen=引导 hint；rejected=泄题（缺 why 的 answer 或首轮 modify）
        level = int(row.get("hint_level") or 1)
        chosen_call = {"tool": "give_hint", "args": {"level": level, "text": chosen.strip()}}
        code = extract_code(rejected)
        if alt(seed):
            rejected_call = {"tool": "modify_code", "args": {"patch": code}}
            decision = "hint_vs_modify"
        else:
            rejected_call = {"tool": "give_answer", "args": {"code": code}}
            decision = "hint_vs_answer"

    # 查表质检：chosen 零违规；rejected 至少一条违规
    c_obj = parse_tool_call(make_tool_call(**chosen_call))  # 结构自检
    r_obj = parse_tool_call(make_tool_call(**rejected_call))
    c_bad = validate_tool_call(c_obj, rnd, release_expected) if c_obj else ["chosen 结构非法"]
    r_bad = validate_tool_call(r_obj, rnd, release_expected) if r_obj else ["rejected 结构非法"]
    if c_bad:
        stats["dropped_chosen_violation"] += 1
        stats.setdefault("chosen_violation_reasons", {})
        for reason in c_bad:
            stats["chosen_violation_reasons"][reason] = stats["chosen_violation_reasons"].get(reason, 0) + 1
        return None
    if not r_bad:
        stats["dropped_rejected_clean"] += 1
        return None

    out = dict(row)
    out["chosen"] = json.dumps(chosen_call, ensure_ascii=False)
    out["rejected"] = json.dumps(rejected_call, ensure_ascii=False)
    out["tool_decision"] = decision
    stats["converted"] += 1
    stats.setdefault("decisions", {})
    stats["decisions"][decision] = stats["decisions"].get(decision, 0) + 1
    return out


def convert_file(src_path: Path, dst_path: Path) -> dict:
    stats: dict = {"input": 0, "converted": 0, "text_only": 0,
                   "dropped_chosen_violation": 0, "dropped_rejected_clean": 0}
    rows_out: list[dict] = []
    for line in src_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        stats["input"] += 1
        out = convert_row(row, stats)
        if out:
            rows_out.append(out)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with dst_path.open("w", encoding="utf-8") as fh:
        for r in rows_out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats["output"] = len(rows_out)
    return stats


def write_sample(src: Path, dst: Path, ratio: float) -> int:
    """按 1/ratio 等距抽样，输出人类可读的抽检文件。"""
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    step = max(1, round(1 / ratio))
    picked = rows[::step]
    lines = []
    for i, r in enumerate(picked, 1):
        prompt = r["prompt"][-1]["content"] if isinstance(r["prompt"], list) else str(r["prompt"])
        lines.append(
            f"===== #{i} [{r['layer']}/{r['source']}/{r.get('tool_decision')}] "
            f"family={r['family']} round={r['round']} =====\n"
            f"[PROMPT] {prompt[:400]}\n"
            f"[CHOSEN] {r['chosen']}\n"
            f"[REJECTED] {r['rejected']}\n"
        )
    dst.write_text("\n".join(lines), encoding="utf-8")
    return len(picked)


def main() -> int:
    parser = argparse.ArgumentParser(description="存量 DPO 文本对 → 工具决策对")
    parser.add_argument("--train", default=str(DEFAULT_OUT_DIR / "dpo_pairs.jsonl"))
    parser.add_argument("--eval", default=str(DEFAULT_OUT_DIR / "dpo_eval_pairs.jsonl"))
    parser.add_argument("--train-out", default=str(DEFAULT_OUT_DIR / "dpo_pairs_tools.jsonl"))
    parser.add_argument("--eval-out", default=str(DEFAULT_OUT_DIR / "dpo_eval_pairs_tools.jsonl"))
    parser.add_argument("--report", default=str(DEFAULT_OUT_DIR / "dpo_tool_convert_report.json"))
    parser.add_argument("--sample", type=float, default=0.0, help="人工抽检比例（如 0.2）")
    args = parser.parse_args()

    report: dict = {}
    for name, src, dst in (
        ("train", Path(args.train), Path(args.train_out)),
        ("eval", Path(args.eval), Path(args.eval_out)),
    ):
        if not src.exists():
            print(f"跳过 {name}: 不存在 {src}", file=sys.stderr)
            continue
        report[name] = convert_file(src, dst)
        print(f"{name}: {report[name]}")

    if args.sample > 0:
        smp = Path(args.train_out).with_suffix(".sample.txt")
        n = write_sample(Path(args.train_out), smp, args.sample)
        report["sample_file"] = str(smp)
        report["sample_n"] = n
        print(f"抽检文件({n} 条): {smp}")

    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
