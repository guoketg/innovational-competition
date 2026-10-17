# -*- coding: utf-8 -*-
"""DPO 存量对转换：文本对 → 工具决策对（plan §3.10 ②，不重新生成对话）。

chosen/rejected 改写为三工具调用 JSON（give_hint / give_answer / modify_code），
新增 tool_decision 字段；layer / source / family 不变。
不涉工具的场景（概念直答、G 层通用）保留纯文本对，防学成「凡事必调工具」。

映射（请求轴唯一化，plan §3.10 数据要求 v2）：
  先由 services.request_classifier 判定学生本回合请求语义（modify / hint / none
  + 工具性逃生门），再按"该不该动手"定方向，不再以轮次作合法性依据：
    should_act（明确请求改码 或 逃生门）→ chosen=modify_code(patch,why)   rejected=give_hint(死拦)   modify_vs_hint
    请求改码但贴码=参考解（无 bug 索改，L4）→ chosen=give_answer(说明无需修改)  rejected=modify_code(硬改)  answer_vs_modify
    未请求但 release_expected（round2 / C 层）→ chosen=give_answer(code,why)  rejected=give_hint(过度引导)  answer_vs_hint
    未请求且未到释放   → chosen=give_hint(level,text)  rejected=modify_code(patch,why)   hint_vs_modify
    G / concept / sycophancy → 纯文本保留（text_only）

  L4 无 bug 索改（plan §3.10 ④，2026-10-15 落地）：学生索改但贴码与参考解逐字等价
  （确证无缺陷，prompt_code_is_clean）时，正解工具是 give_answer（"没有发现问题，无需修改"
  + 讲解），而非再调 modify_code 落盘硬改——硬改正确代码即 no_bug_no_touch 违规。
  逃生门（tool_context）豁免：工具性使用允许按需改动正确代码（T1 对型）。
  码/讲解来源随对型而变：round1 的参考实现在 rejected（泄题侧，chosen 是引导）；
  round2/C 的参考实现在 chosen（讲解式答案侧，rejected 是过度引导）。
  这修复了原"round1 一律 modify_code→rejected"（224 对带病样本：学生明确索要代改
  却被标成该拒绝的行为）。

质检（查表，build_dpo_pairs.validate_tool_call）：
  chosen 侧零违规；rejected 侧至少命中一条违规（否则方向反了）。
  无 bug 检查（plan §3.10 ⑤）：学生贴码与 verify_lab_content 参考解逐字等价
  （确证无缺陷，忽略空白）时 chosen 不得为 modify_code（no_bug_no_touch）；
  无法确证（变异体 / 自由代码 / 无贴码）不触发，宁可漏检不误杀。
不合格对丢弃并计数。转换后 20% 人工抽检（--sample 输出抽样文件）。

多轮样本原生轨迹升级：
  真·多轮样本（round2，prompt 为 [user(r1), assistant(文本引导), user(r2)]）的
  round1 引导文本表述不出"先读文件再决策"的调工具行为，故就地改写为原生工具轨迹
  [user(r1), assistant(tool_calls=read_project_file), tool(学生代码), user(r2)]，
  使行为通道（调工具 + 多轮）进入 DPO 训练分布。chosen/rejected 目标不变（保持
  决策工具调用文本，训练脚本无需改动）。幂等：已升级样本重跑不变。

用法：
  python scripts/convert_dpo_to_tools.py                 # train + eval 全量转换
  python scripts/convert_dpo_to_tools.py --sample 0.2    # 额外输出 20%% 抽检文件
"""

from __future__ import annotations

import argparse
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
    build_tool_context,
    make_tool_call,
    parse_tool_call,
    strip_code,
    validate_tool_call,
)
from services.answer_guard_service import extract_code_blocks  # noqa: E402

DEFAULT_OUT_DIR = BACKEND / "data" / "dpo"

# L4 无 bug 索改的确认话术（plan §3.10 ④）：学生贴码=参考解时说明无需修改。
_NO_BUG_WHY = "我逐行检查了你贴出的代码，没有发现缺陷——当前实现已经是正确解，不需要修改。"


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
    out = re.sub(r"(?:[ \t]*\n){3,}", "\n\n", (text or "").strip())
    out = re.sub(r"[ \t]+\n", "\n", out)
    return out.strip()


_FENCE_RE = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.S)


def _solution_file_for(fence_lang: str) -> str:
    """围栏语言 → 工作区解答文件名（与 agent_lab_specs.LANGUAGE_SPECS 对齐）。"""
    if (fence_lang or "").lower() in ("cpp", "c++", "cc", "cxx"):
        return "solution.cpp"
    return "solution.py"


def _first_code_block(text: str) -> tuple[str, str]:
    """返回 (围栏语言, 代码文本)；无围栏时返回 ("", 原文) 以便调用方跳过。"""
    m = _FENCE_RE.search(text or "")
    if m:
        return m.group(1), m.group(2).strip()
    return "", ""


def upgrade_multiturn_trajectory(prompt) -> tuple[object, bool]:
    """多轮样本历史 → 原生工具轨迹（plan §3.10，2026-10-14 定）。

    文本通道的历史 [user(r1 含代码), assistant(纯文本引导), user(r2 追问)] 表述不出
    "先读文件再决策"，故改写为原生工具轨迹：
      [user(r1), assistant(tool_calls=read_project_file), tool(学生代码), user(r2)]
    只有存在"无 tool_calls 的 assistant 文本消息"、且其之前的 user 消息带围栏代码时改写；
    已升级样本再跑不变（幂等）。chosen/rejected 目标不改（仍为决策工具调用文本）。
    """
    if not isinstance(prompt, list):
        return prompt, False
    # 定位第一条无 tool_calls 的 assistant 文本消息（即 round1 的文本引导）
    idx = None
    for i, m in enumerate(prompt):
        if isinstance(m, dict) and m.get("role") == "assistant" and not m.get("tool_calls"):
            idx = i
            break
    if idx is None:
        return prompt, False
    # 取该 assistant 之前最近一条 user 消息里的围栏代码作为"文件内容"
    fence_lang, code = "", ""
    for m in reversed(prompt[:idx]):
        if isinstance(m, dict) and m.get("role") == "user":
            fence_lang, code = _first_code_block(str(m.get("content") or ""))
            if code:
                break
    if not code:
        return prompt, False
    tool_call_id = "call_read_1"
    read_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": "read_project_file",
                "arguments": {"path": _solution_file_for(fence_lang)},
            },
        }],
    }
    tool_msg = {"role": "tool", "tool_call_id": tool_call_id,
                "name": "read_project_file", "content": code}
    return prompt[:idx] + [read_msg, tool_msg] + prompt[idx + 1:], True


def convert_row(row: dict, stats: dict) -> dict | None:
    layer = row.get("layer")
    subtype = row.get("subtype") or ""
    rnd = int(row.get("round") or 0)
    chosen, rejected = row["chosen"], row["rejected"]

    out = dict(row)
    # 多轮样本：历史升级为原生工具轨迹（读取文件 → 追问 → 决策）
    new_prompt, upgraded = upgrade_multiturn_trajectory(row.get("prompt"))
    if upgraded:
        out["prompt"] = new_prompt
        stats["multiturn_upgraded"] = stats.get("multiturn_upgraded", 0) + 1

    # 不涉工具场景：概念直答 + G 层通用 + A 层反谄媚 → 纯文本保留
    if layer == "G" or subtype in ("concept", "sycophancy"):
        out["tool_decision"] = "text_only"
        stats["text_only"] += 1
        return out

    release_expected = rnd == 2 or layer == "C"  # round2 / C：学生已展示尝试，释放条件已满足
    ctx = build_tool_context(row["prompt"], round_no=rnd, release_expected=release_expected)
    should_act = ctx["requested"] or ctx["tool_context"]

    # 码 / 讲解的来源随对型而变：round1 参考实现在 rejected（泄题侧，chosen 是引导）；
    # round2/C 参考实现在 chosen（讲解式答案侧，rejected 是过度引导）。
    if release_expected:
        hint_text = rejected.strip()
        ref_code = extract_code(chosen)
        ref_prose = clean_why(strip_code(chosen))
    else:
        hint_text = chosen.strip()
        ref_code = extract_code(rejected)
        ref_prose = clean_why(strip_code(rejected))
    # 部分 round1 泄题侧是纯代码（无散文），why 退化用引导语——引导常已点出根因，语义可接受。
    why = ref_prose or clean_why(strip_code(hint_text))
    level = min(max(int(row.get("hint_level") or 1), 1), 3)

    if subtype == "scope_overreach":
        # L3 越权修改：正解=只还原点名那一行；错误侧=顺手把整份修完。
        # 两侧都是 modify_code，区别在 patch 实际的改动区域数（由 validate_tool_call 查表）。
        chosen_call = {"tool": "modify_code", "args": {
            "patch": extract_code(chosen), "why": clean_why(strip_code(chosen))}}
        rejected_call = {"tool": "modify_code", "args": {
            "patch": extract_code(rejected), "why": clean_why(strip_code(rejected))}}
        decision = "narrow_vs_overreach"
    elif subtype == "step_confirm":
        # L5 分步确认：正解=先预览一处并请确认（give_hint，不落盘）；
        # 错误侧=没等确认就一次性全改（modify_code，step_confirm_violation）。
        chosen_call = {"tool": "give_hint", "args": {"level": 1, "text": chosen.strip()}}
        rejected_call = {"tool": "modify_code", "args": {
            "patch": extract_code(rejected), "why": clean_why(strip_code(rejected))}}
        decision = "step_confirm_vs_all"
    elif should_act and ctx.get("prompt_code_clean") and not ctx.get("tool_context"):
        # L4 无 bug 索改（plan §3.10 ④）：学生索改但贴码=参考解（确证无缺陷）→
        # 正解是说明无需修改（give_answer，不落盘），硬改该代码即 no_bug_no_touch 违规。
        # why 只用确认话术：ref_prose 是"改了什么"的修复叙述（相对 round1 带病码），
        # 与"无需修改"自相矛盾，不得附在确认侧（截图中曾出现"没有发现缺陷"+"把>=改成>"并存）。
        chosen_call = {"tool": "give_answer", "args": {"code": "", "why": _NO_BUG_WHY}}
        rejected_call = {"tool": "modify_code", "args": {"patch": ref_code, "why": why}}
        decision = "answer_vs_modify"
        stats["no_bug_confirmation"] = stats.get("no_bug_confirmation", 0) + 1
    elif should_act:
        # 学生明确索要代改 / 走逃生门 → 正当代改（modify_code），死拦为过度拦截
        chosen_call = {"tool": "modify_code", "args": {"patch": ref_code, "why": why}}
        rejected_call = {"tool": "give_hint", "args": {"level": 1, "text": hint_text}}
        decision = "modify_vs_hint"
    elif release_expected:
        # 未请求但已到释放（round2/C）→ 给讲解式答案，过度引导为违规
        chosen_call = {"tool": "give_answer", "args": {"code": ref_code, "why": why}}
        rejected_call = {"tool": "give_hint", "args": {"level": 1, "text": hint_text}}
        decision = "answer_vs_hint"
    else:
        # 未请求且未到释放（round1）→ 只给引导，主动代改即核心违规
        chosen_call = {"tool": "give_hint", "args": {"level": level, "text": hint_text}}
        rejected_call = {"tool": "modify_code", "args": {"patch": ref_code, "why": why}}
        decision = "hint_vs_modify"

    # 查表质检：chosen 零违规；rejected 至少一条违规
    c_obj = parse_tool_call(make_tool_call(**chosen_call))  # 结构自检
    r_obj = parse_tool_call(make_tool_call(**rejected_call))
    c_bad = validate_tool_call(c_obj, ctx) if c_obj else ["chosen 结构非法"]
    r_bad = validate_tool_call(r_obj, ctx) if r_obj else ["rejected 结构非法"]
    if c_bad:
        stats["dropped_chosen_violation"] += 1
        stats.setdefault("chosen_violation_reasons", {})
        for reason in c_bad:
            stats["chosen_violation_reasons"][reason] = stats["chosen_violation_reasons"].get(reason, 0) + 1
        return None
    if not r_bad:
        stats["dropped_rejected_clean"] += 1
        return None

    out["chosen"] = json.dumps(chosen_call, ensure_ascii=False)
    out["rejected"] = json.dumps(rejected_call, ensure_ascii=False)
    out["tool_decision"] = decision
    stats["converted"] += 1
    stats.setdefault("decisions", {})
    stats["decisions"][decision] = stats["decisions"].get(decision, 0) + 1
    return out


def convert_file(src_path: Path, dst_path: Path) -> dict:
    stats: dict = {"input": 0, "converted": 0, "text_only": 0, "multiturn_upgraded": 0,
                   "dropped_chosen_violation": 0, "dropped_rejected_clean": 0,
                   "no_bug_confirmation": 0}
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
