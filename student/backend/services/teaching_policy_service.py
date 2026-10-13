"""教学动作决策策略（Teaching Policy）与诊断→提示闭环。

决策链：规则引擎（带置信度）→ 低置信时 LLM 快速分类（max_tokens≈16）→ 规则兜底。
每次决策落库到 state["teaching_move_log"]（上限 200 条），供“教学动作命中率”
量化评测与赛后统计直接读取。

diagnosis_focus() 把最近一次阶段检查的失败项映射成提示侧重，注入导师 prompt，
形成“诊断 → 下一次提示”的闭环。
"""

from __future__ import annotations

import re
import time

MOVES = (
    "socratic_question",
    "progressive_hint",
    "concept_link",
    "diagnose",
    "evaluate_response",
    "guided_next_step",
)

# 规则命中置信度：显式关键词 0.92，对话语境判断 0.78，兜底 0.5
_CONF_STRONG = 0.92
_CONF_CONTEXT = 0.78
_CONF_FALLBACK = 0.5
# 低于该置信度才走 LLM 快分
_LLM_THRESHOLD = 0.7

_LOG_CAP = 200

_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("自测", "考考我", "提问我", "检查理解"), "socratic_question"),
    (("为什么", "作用", "原理", "是什么意思"), "concept_link"),
    (("提示", "卡住", "不会", "下一步", "怎么写", "帮帮我"), "progressive_hint"),
    (("报错", "错误", "失败", "不通过", "异常", "error"), "diagnose"),
)

_CLASSIFY_PROMPT = """你是教学动作分类器。根据学生问题从以下 6 个动作中选 1 个：
socratic_question=学生要求自测/出题考查
progressive_hint=学生卡住求提示/求下一步
concept_link=学生问为什么/原理/概念
diagnose=学生报告报错/测试失败/异常
evaluate_response=学生在回答导师上一轮的提问
guided_next_step=其他情况（含普通操作请求）
学生问题：{question}
历史末轮：{tail}
只输出动作英文名，不要输出任何其他文字。"""


def classify_by_rule(question: str, history: list[dict]) -> tuple[str, float, str]:
    """纯规则分类，返回 (move, confidence, source)。永不抛错。"""
    text = str(question or "").lower()
    for terms, move in _RULES:
        if any(term in text for term in terms):
            return move, _CONF_STRONG, "rule"
    if history and history[-1].get("role") == "assistant" and "？" in str(history[-1].get("content", "")):
        # 导师上一轮以提问收尾，学生本轮大概率在作答
        return "evaluate_response", _CONF_CONTEXT, "rule"
    return "guided_next_step", _CONF_FALLBACK, "rule"


async def classify_move(user_id: int, question: str, history: list[dict]) -> dict:
    """规则(带置信度) → 低置信 LLM 快分 → 规则兜底。

    返回 {"move", "confidence", "source"}，source ∈ {rule, llm, fallback}。
    任何异常都退化为规则结果，绝不阻塞导师主流程。
    """
    move, confidence, source = classify_by_rule(question, history)
    if confidence >= _LLM_THRESHOLD:
        return {"move": move, "confidence": confidence, "source": source}

    try:
        from services.ai_service import call_llm

        tail = ""
        if history:
            last = history[-1]
            tail = f"{last.get('role', '')}: {str(last.get('content', ''))[:200]}"
        raw = await call_llm(
            user_id,
            [{"role": "user", "content": _CLASSIFY_PROMPT.format(question=str(question)[:400], tail=tail)}],
            temperature=0.0,
            max_tokens=16,
        )
        if isinstance(raw, str) and not raw.startswith("LLM调用异常:"):
            found = re.findall("|".join(MOVES), raw)
            if found:
                # 多个匹配时取第一个出现的动作名
                best = min(found, key=raw.index)
                return {"move": best, "confidence": 0.85, "source": "llm"}
    except Exception:
        pass
    return {"move": move, "confidence": confidence, "source": "fallback"}


def log_decision(state: dict, decision: dict, question: str = "", stage_id: str = "") -> None:
    """把一次教学动作决策写进状态（cap 200 条）。"""
    log = state.setdefault("teaching_move_log", [])
    log.append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "move": str(decision.get("move", "")),
        "confidence": decision.get("confidence"),
        "source": str(decision.get("source", "")),
        "stage": stage_id,
        "q": str(question or "")[:80],
    })
    if len(log) > _LOG_CAP:
        del log[: len(log) - _LOG_CAP]


# ── 诊断 → 提示闭环 ──

_FOCUS_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("边界", "越界", "空输入", "nullptr", "越界"), "边界条件（空输入、越界、极值）"),
    (("时间", "超时", "复杂度", "效率"), "算法复杂度（当前做法会不会超时）"),
    (("输出", "格式", "打印", "不匹配"), "输出格式与题目契约"),
    (("编译", "语法", "compile"), "语法与编译错误"),
    (("样例", "测试", "断言", "用例"), "对照样例逐条手动模拟执行"),
    (("签名", "函数名", "参数", "返回值"), "函数签名与参数契约"),
    (("逻辑", "结果错误", "wrong"), "核心逻辑的执行流程"),
)


def diagnosis_focus(state: dict) -> str:
    """最近一次阶段检查的失败项 → 本次提示应侧重什么。空结果返回空串。"""
    results = state.get("stage_results") or {}
    if not isinstance(results, dict):
        return ""
    failed: list[str] = []
    for stage_id in reversed(list(results.keys())):
        stage = results.get(stage_id) or {}
        if stage.get("passed"):
            continue
        for check in stage.get("checks", []):
            if not check.get("passed"):
                label = str(check.get("label", ""))
                detail = str(check.get("detail", ""))[:120]
                failed.append(f"{label}：{detail}" if detail else label)
        if failed:
            break
    if not failed:
        return ""

    blob = " ".join(failed).lower()
    focuses = [text for keys, text in _FOCUS_RULES if any(k.lower() in blob for k in keys)]
    focus_text = "；".join(dict.fromkeys(focuses)) or "失败检查项对应的实现细节"
    return (
        "【最近诊断（上次阶段检查未通过）】\n"
        + "\n".join(f"- {item}" for item in failed[:4])
        + f"\n本次回答的提示请优先围绕：{focus_text}。"
    )


# ── 掌握度驱动的提示级别 ──

def stage_mastery(state: dict, stage_id: str) -> float:
    """当前阶段掌握度估计，0..1。

    证据 = 0.7×阶段检查通过率 + 0.3×最近自测结果，按实际可用的证据归一；
    没有任何证据时返回中性值 0.5。阶段已完成直接视为 1.0。
    """
    if stage_id in (state.get("completed_stages") or []):
        return 1.0
    score = 0.0
    weight = 0.0
    results = state.get("stage_results") or {}
    stage = results.get(stage_id) if isinstance(results, dict) else None
    if isinstance(stage, dict) and stage.get("checks"):
        checks = stage["checks"]
        passed = sum(1 for item in checks if item.get("passed"))
        score += 0.7 * (passed / len(checks))
        weight += 0.7
    if state.get("sample_run_at"):
        score += 0.3 * (1.0 if state.get("sample_run_passed") else 0.0)
        weight += 0.3
    if weight == 0:
        return 0.5
    return round(score / weight, 3)


def mastery_hint_level(state: dict, stage_id: str, prev_level: int) -> int:
    """掌握度驱动的渐进提示级别（替代固定「上次+1」）。

    - 掌握度高（≥0.7）：提示保守，上限 2 级（结构），不给局部示例；
    - 掌握度中（0.4~0.7）：常规 1→2→3 阶梯；
    - 掌握度低（<0.4）：跳过纯方向提示，起点即 2 级（结构），阶梯到 3。
    """
    mastery = stage_mastery(state, stage_id)
    if mastery >= 0.7:
        start, cap = 1, 2
    elif mastery >= 0.4:
        start, cap = 1, 3
    else:
        start, cap = 2, 3
    return min(max(int(prev_level) + 1, start), cap)
