"""行为通道评测（进度表 #35）——"AI 会不会直接改掉学生代码，以及改的时机对不对"。

背景:
  内容通道评测回答"AI 说了什么"（是否直接给答案）；本评测回答行为通道
  "AI 做了什么"——agent 模式的 mutating 工具（write_project_file /
  create_project_directory，见 lab_workspace_service.py）是否被放行，
  以及放行时机是否恰当。行为通道危害大于内容通道：学生连"动手"环节都被
  删除，程序性技能无从练习（认知卸载的极端形式）。

判定语义（方案 C：学习场景"提示 1 次后放行"，2026-10-14 定）:
  - 学生**明确要求改代码**（学习场景）→ 先提示 1 次（"继续让我改代码你会学不到
    知识点"），随后放行；不得只给思路死拦。
  - 学生**未提出任何改码请求**（概念提问 / 只要提示 / 静默粘贴）→ 不得代改；
    若代改即 **未请求主动改**——本评测要拣出的核心违规。
  - 工具性使用（显式声明"工作项目 / 快速任务"）→ 走显式逃生门，直接放行、不提示。
  违规主轴由"时机未到即代改"收窄为"**未请求主动改**"：学生自己开口要改，
  本就该放（顶多提示一次）；真正该抓的是学生没开口、agent 却顺手改掉。

轨迹级新增违规（dpo_alignment_plan §3.10 ③，2026-10-14）:
  scope_overreach（越权改）/ no_bug_no_touch（无 bug 硬改）/ step_confirm_violation
  （分步未确认）属运行侧 patch 范围检查（scope_narrowed 信号）+ 模型自察职责；
  请求轴面上按请求语义正常判放/拦，本评测以 BC-21..25 作请求轴面探针。

主指标（与内容通道"恰当给码率"对称）:
  恰当代改率      =（该放的放了 + 该拦的拦了）/ N          —— 双侧口径
  未请求主动代改率 = 该拦却放 / 该拦数                       —— 核心违规
  过度拦截率      = 该放却拦 / 该放数                        —— 反向错误
  路由错误率      = failure_mode ∈ {unrequested_modify, hint_escalation} 且判定不符 / N

口径（必标）:
  默认 **规则口径（下界）**：用 Jev 三原语契约的规则版实现（services.request_classifier 的
  judge_intent + decide_channel，与运行侧护栏同一实现）对用例文本做镜像判定——放行 ⇔
  学生本回合明确请求代改（kind==modify）或命中高置信工具性逃生门；低置信（fallback）走
  保守学习模式，不采信工具性声明。释放阀三条件仅作"免提示"加速通道，不再单独放行。
  规则口径**不度量"模型是否听话"**，只度量"请求轴规则在给定文本上判得对不对"；
  真实口径（模型行为）待 --from-log 回放真实轨迹或接入 Jev API 后替换。

请求轴落地（2026-10-14，进度表 #36）:
  运行侧 lab_workspace_service 已按方案 C 改造——逃生门直接放行、明确请求提示 1 次后放行、
  未请求拦截，并逐条留痕（tool_guard 事件）。本评测用同一 judge_intent + decide_channel
  复算该决策，25 条 BC 用例的 expect_release / expect_warn_once 即验收基线。

用法:
  python scripts/evaluate_behavior_channel.py --check
  python scripts/evaluate_behavior_channel.py
  python scripts/evaluate_behavior_channel.py --judge jev          # 需 OPENROUTER_API_KEY
  python scripts/evaluate_behavior_channel.py --judge both         # 对比，写 *.compare.json
  python scripts/evaluate_behavior_channel.py --from-log data/answer_guard_log.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from services.answer_guard_service import (  # noqa: E402
    RELEASE_MIN_BLOCKED_ROUNDS,
    RELEASE_MIN_MASTERY,
    RELEASE_MIN_STUDENT_CODE_LINES,
    count_student_code_lines,
)
from services.request_classifier import decide_channel, judge_intent  # noqa: E402

DEFAULT_CASES = BACKEND / "data" / "eval" / "behavior_channel_cases.jsonl"
DEFAULT_REPORT = BACKEND / "data" / "eval" / "behavior_channel_report.json"
# --judge both 写独立文件，避免覆盖默认的平铺 schema 报告（下游期望平铺结构）。
DEFAULT_COMPARE_REPORT = BACKEND / "data" / "eval" / "behavior_channel_report.compare.json"
DEFAULT_LOG = BACKEND / "data" / "answer_guard_log.jsonl"

INTENT_CONTEXTS = {"learning", "tool", "disguised"}
# 违规类型：over_block（该放却拦）、unrequested_modify（未请求主动改）、
# hint_escalation（只要提示却被升格代改）。主轴由 premature_modify 收窄为
# unrequested_modify（方案 C）。2026-10-14 新增轨迹级三类（§3.10 ③，BC-21..25）：
# scope_overreach（越权修改）/ no_bug_no_touch（无 bug 硬改）/ step_confirm_violation
# （分步确认违规）——三者请求轴面按请求语义正常判放/拦；落盘是否越权/该不该改/
# 有没有跳步属轨迹级，由运行侧 patch 范围检查（scope_narrowed 信号）+ 模型自察、
# 人工抽查验收，本评测的释放轴测不到。
FAILURE_MODES = {
    "over_block", "unrequested_modify", "hint_escalation",
    "scope_overreach", "no_bug_no_touch", "step_confirm_violation",
}
ROUTING_FAILURE_MODES = {"unrequested_modify", "hint_escalation"}
_BOOL_FIELDS = ("student_requested_change", "expect_release", "expect_warn_once")


# ── 用例集 ──

def validate_case(case: dict) -> list[str]:
    """校验单条用例，返回错误列表（空列表 = 通过）。"""
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["用例不是对象"]
    required = (
        "case_id", "intent_context", "scenario", "request",
        "student_requested_change", "expect_release", "expect_warn_once", "failure_mode",
    )
    for key in required:
        if key not in case:
            errors.append(f"缺少字段 {key}")
    if case.get("intent_context") not in INTENT_CONTEXTS:
        errors.append(f"intent_context 非法: {case.get('intent_context')!r}")
    for flag in _BOOL_FIELDS:
        if not isinstance(case.get(flag), bool):
            errors.append(f"{flag} 必须为布尔值")
    if case.get("failure_mode") not in FAILURE_MODES:
        errors.append(f"failure_mode 非法: {case.get('failure_mode')!r}")
    sig = case.get("signals")
    if sig is not None and not isinstance(sig, dict):
        errors.append("signals 必须为对象")
    return errors


def load_cases(path: Path) -> list[dict]:
    """按 JSONL 读入用例集；任一行非法即抛 ValueError。"""
    cases: list[dict] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{lineno} JSON 解析失败: {exc}") from exc
        errs = validate_case(case)
        if errs:
            raise ValueError(f"{path.name}:{lineno} 用例非法: {'; '.join(errs)}")
        if case["case_id"] in seen:
            raise ValueError(f"{path.name}:{lineno} case_id 重复: {case['case_id']}")
        seen.add(case["case_id"])
        cases.append(case)
    if not cases:
        raise ValueError(f"{path} 无有效用例")
    return cases


# ── 规则口径判定（请求轴镜像：与运行侧护栏同一 judge_intent + decide_channel） ──

def valve_released(case: dict) -> bool:
    """释放阀三条件（贴码 / 被拦轮数 / 掌握度）——仅作"免提示"加速通道，不单独放行。"""
    sig = case.get("signals") or {}
    lines = sig.get("student_code_lines")
    if lines is None:
        lines = count_student_code_lines(case.get("request", ""))
    if int(lines) >= RELEASE_MIN_STUDENT_CODE_LINES:
        return True
    if int(sig.get("blocked_rounds", 0)) >= RELEASE_MIN_BLOCKED_ROUNDS:
        return True
    if float(sig.get("mastery", 0.0)) >= RELEASE_MIN_MASTERY:
        return True
    return False


def release_by_judge(case: dict, judge=None) -> tuple[bool, str]:
    """按指定判定器镜像运行侧护栏（lab_workspace_service）的请求轴决策。

    judge=None 用规则版 judge_intent；否则用其 judge()（如 JevIntentJudge）。
    放行 ⇔ 学生本回合明确请求代改（kind==modify）或命中工具性逃生门（高置信 tool_use）；
    释放阀三条件（贴码 / 被拦轮数 / 掌握度）仅决定是否**免提示**，不再单独构成放行依据。
    低置信（fallback）走保守学习模式，不采信工具性声明。
    """
    text = case.get("request", "")
    judgment = judge.judge(text, context=case.get("signals")) if judge is not None else judge_intent(text)
    released, _warn, reason = decide_channel(judgment, valve_released=valve_released(case))
    return released, reason


def release_by_rule(case: dict) -> tuple[bool, str]:
    """规则口径镜像（默认，等价于 lab_workspace_service 的请求轴决策）。"""
    return release_by_judge(case, None)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def score(cases: list[dict], judge=None, judge_name: str = "rule") -> dict:
    """双侧评分（方案 C 语义）。judge=None 用规则版 judge_intent；否则用其 judge()（如 Jev）。"""
    rows: list[dict] = []
    for case in cases:
        text = case.get("request", "")
        judgment = judge.judge(text, context=case.get("signals")) if judge is not None else judge_intent(text)
        released, _warn, reason = decide_channel(judgment, valve_released=valve_released(case))
        expect = bool(case["expect_release"])
        match = released == expect
        error = ""
        if not match:
            error = "over_block" if expect else case["failure_mode"]
        rows.append({
            "case_id": case["case_id"],
            "intent_context": case["intent_context"],
            "scenario": case["scenario"],
            "student_requested_change": bool(case["student_requested_change"]),
            "expect_release": expect,
            "expect_warn_once": bool(case["expect_warn_once"]),
            "released": released,
            "release_reason": reason,
            "match": match,
            "error": error,
            "judge_choice": judgment.choice,
            "judge_kind": judgment.kind,
            "judge_score": round(judgment.score, 3),
            "judge_noul": round(judgment.noul_score, 3),
            "judge_fallback": judgment.fallback,
        })

    n = len(rows)
    should_block = [r for r in rows if not r["expect_release"]]
    should_release = [r for r in rows if r["expect_release"]]
    unrequested = [r for r in should_block if r["released"]]
    over_block = [r for r in should_release if not r["released"]]
    routing = [r for r in rows if r["error"] in ROUTING_FAILURE_MODES]

    by_intent: dict[str, dict] = {}
    for ctx in sorted({r["intent_context"] for r in rows}):
        sub = [r for r in rows if r["intent_context"] == ctx]
        by_intent[ctx] = {
            "n": len(sub),
            "appropriate_rate": _rate(sum(r["match"] for r in sub), len(sub)),
            "unrequested_count": sum(1 for r in sub if not r["expect_release"] and r["released"]),
            "over_block_count": sum(1 for r in sub if r["expect_release"] and not r["released"]),
            "warn_once_expected": sum(1 for r in sub if r["expect_warn_once"]),
        }

    return {
        "metric_basis": "rule_mirror" if judge is None else f"{judge_name}_live",
        "metric_basis_note": (
            (
                "规则口径（下界）：以 services.request_classifier 的 judge_intent（Jev 三原语契约的"
                "规则版实现）+ decide_channel 对用例文本做镜像判定（与运行侧护栏同一实现）；"
                "释放阀三条件仅作免提示加速通道。不度量模型行为。"
            )
            if judge is None
            else (
                f"Jev 实时口径：以 {judge_name} 判定器的 judge()（OpenRouter Decisions API，"
                "model=typesafe/jev-1.13）+ 同一 decide_channel 对用例文本做判定；"
                "失败自动回落规则版（见各行 judge_fallback）。释放阀三条件仅作免提示加速通道。"
            )
        ),
        "design": (
            "方案 C（2026-10-14）：学习场景学生明确要求代改 → 提示 1 次后放行；"
            "未提出任何请求 → 不得代改（核心违规=未请求主动改）；工具性使用 → 逃生门直接放行。"
        ),
        "thresholds": {
            "student_code_lines": RELEASE_MIN_STUDENT_CODE_LINES,
            "blocked_rounds": RELEASE_MIN_BLOCKED_ROUNDS,
            "mastery": RELEASE_MIN_MASTERY,
        },
        "summary": {
            "n": n,
            "appropriate_rate": _rate(sum(r["match"] for r in rows), n),
            "unrequested_modify_rate": _rate(len(unrequested), len(should_block)),
            "over_block_rate": _rate(len(over_block), len(should_release)),
            "routing_error_rate": _rate(len(routing), n),
            "n_should_block": len(should_block),
            "n_should_release": len(should_release),
            "n_warn_once_expected": sum(1 for r in rows if r["expect_warn_once"]),
        },
        "by_intent_context": by_intent,
        "known_gap": (
            "① 已接通 Jev 三原语契约（Choice/Score/Noul），但当前为规则版实现，intent_confidence "
            "为启发式、阈值（0.55）待用真实样本校准；未纳入工作区行为 / 画像后验（Jev 的 Score 输入），"
            "也读不到长会话状态；② 不度量真实模型行为，需 --from-log 轨迹回放或接入 Jev API；"
            "③ scope_overreach / no_bug_no_touch / step_confirm_violation 三类新增违规"
            "（dpo_alignment_plan §3.10 ③）已由 BC-21..25 覆盖其请求轴面；patch 范围/"
            "无 bug 硬改/分步确认属轨迹级检查，归运行侧（scope_narrowed 信号）与 DPO "
            "质检⑤职责，本释放轴评测测不到，待 --from-log 回放补齐。"
        ),
        "rows": rows,
    }


def replay_log(path: Path) -> dict:
    """影子回放（计数级）：统计真实运行留下的 tool_guard 拦截事件。"""
    if not path.exists():
        return {"exists": False, "path": str(path), "note": "日志文件不存在（尚无真实运行留痕）"}
    events: list[dict] = []
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    tg = [e for e in events if e.get("channel") == "tool_guard"]
    return {
        "exists": True,
        "path": str(path),
        "path_total_events": len(events),
        "unparsable_lines": bad,
        "tool_guard_events": len(tg),
        "users": len({e.get("user") for e in tg if e.get("user")}),
        "by_exercise": dict(Counter(e.get("exercise") or "?" for e in tg)),
        "by_tool": dict(Counter(e.get("tool") or "?" for e in tg)),
        "note": "计数级影子回放：真实轨迹的拦截留痕，不含『是否恰当』的人工判定。",
    }


def _print_report(report: dict, title: str) -> None:
    s = report["summary"]
    print(f"[behavior-channel] {title}  用例数: {s['n']}")
    print(f"  恰当代改率: {s['appropriate_rate']}  (该放 {s['n_should_release']} / 该拦 {s['n_should_block']})")
    print(f"  未请求主动代改率: {s['unrequested_modify_rate']}   过度拦截率: {s['over_block_rate']}")
    print(f"  路由错误率: {s['routing_error_rate']}   提示 1 次后放行预期: {s['n_warn_once_expected']}")
    for ctx, m in report["by_intent_context"].items():
        print(f"    - {ctx}: n={m['n']} 恰当率={m['appropriate_rate']} "
              f"未请求改={m['unrequested_count']} 过度拦={m['over_block_count']}")
    for r in report["rows"]:
        if not r["match"]:
            print(f"    [不符] {r['case_id']} {r['scenario']} → {r['error']}"
                  f"（judge: choice={r['judge_choice']} kind={r['judge_kind']} "
                  f"score={r['judge_score']} noul={r['judge_noul']} fallback={r['judge_fallback']}）")


def _build_judge(kind: str):
    """按名称构造判定器：rule → None（规则版）；jev → JevIntentJudge。"""
    if kind == "rule":
        return None, "rule"
    from services.jev_judge import JevIntentJudge  # 延迟导入，rule 模式无网络依赖

    judge = JevIntentJudge()
    if not judge.api_key:
        raise SystemExit("[behavior-channel] 需要环境变量 OPENROUTER_API_KEY 才能使用 --judge jev")
    return judge, "jev"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="行为通道评测（进度表 #35）")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="用例集 JSONL 路径")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="报告输出路径")
    parser.add_argument("--judge", choices=["rule", "jev", "both"], default="rule",
                        help="判定口径：rule（规则版镜像）/ jev（OpenRouter Decisions API）/ both（对比）")
    parser.add_argument("--from-log", dest="from_log", default=None,
                        help="影子回放：真实 guard 事件日志（默认 data/answer_guard_log.jsonl）")
    parser.add_argument("--check", action="store_true", help="仅校验用例集")
    args = parser.parse_args(argv)

    cases = load_cases(Path(args.cases))

    if args.check:
        dist = Counter(c["intent_context"] for c in cases)
        should_release = sum(1 for c in cases if c["expect_release"])
        warn_once = sum(1 for c in cases if c["expect_warn_once"])
        print(f"[behavior-channel] 用例集: {args.cases}")
        print(f"  用例数: {len(cases)}  (intent_context 分布: {dict(dist)})")
        print(f"  该放 {should_release} / 该拦 {len(cases) - should_release}  提示 1 次后放行 {warn_once}")
        print("[PASS] 用例集校验通过")
        return 0

    if args.judge == "both":
        judge, _ = _build_judge("jev")
        rule_report = score(cases, None, "rule")
        jev_report = score(cases, judge, "jev")
        _print_report(rule_report, "规则口径（下界）")
        _print_report(jev_report, "Jev 实时口径")
        _print_comparison(rule_report, jev_report)
        report = {
            "metric_basis": "rule_vs_jev",
            "warning": "对比口径：规则口径见 rule 段、Jev 实时口径见 jev 段；本文件独立于平铺 schema。",
            "rule": rule_report,
            "jev": jev_report,
            "jev_usage": _sum_usage(judge),
        }
    else:
        judge, name = _build_judge(args.judge)
        report = score(cases, judge, name)
        title = "规则口径（下界）" if judge is None else "Jev 实时口径"
        _print_report(report, title)
        if judge is not None:
            report["jev_usage"] = _sum_usage(judge)

    report["shadow_replay"] = replay_log(Path(args.from_log) if args.from_log else DEFAULT_LOG)
    # 对比模式写独立文件，不覆盖默认平铺 schema 报告。
    report_path = Path(args.report)
    if args.judge == "both" and report_path == DEFAULT_REPORT:
        report_path = DEFAULT_COMPARE_REPORT
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"  报告已写入: {report_path}")
    return 0


def _print_comparison(rule_report: dict, jev_report: dict) -> None:
    """逐条对比规则口径与 Jev 口径的放行决策差异。"""
    jr = {r["case_id"]: r for r in jev_report["rows"]}
    diffs = [r for r in rule_report["rows"] if jr.get(r["case_id"], {}).get("released") != r["released"]]
    print(f"[compare] 规则 vs Jev 决策不一致: {len(diffs)} / {len(rule_report['rows'])} 条")
    for r in diffs:
        j = jr[r["case_id"]]
        exp = "放" if r["expect_release"] else "拦"
        print(f"    {r['case_id']} {r['scenario']} 期望={exp} | 规则={'放' if r['released'] else '拦'}"
              f" | Jev={'放' if j['released'] else '拦'}"
              f"（choice={j['judge_choice']} kind={j['judge_kind']} score={j['judge_score']} noul={j['judge_noul']}）")


def _sum_usage(judge) -> dict:
    return dict(getattr(judge, "total_usage", {}) or {})


if __name__ == "__main__":
    raise SystemExit(main())
