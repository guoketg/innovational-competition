# -*- coding: utf-8 -*-
"""请求语义判定器（Request Classifier）——"学生这一回合到底要什么"。

对齐 [dpo_alignment_plan.md](../../docs/dpo_alignment_plan.md) §3.10「数据要求 v2」。
这是请求轴（request axis）的单一实现，被四处共用，杜绝口径漂移：

  * 数据侧质检 —— scripts/build_dpo_pairs.validate_tool_call
  * 数据侧转换 —— scripts/convert_dpo_to_tools.convert_row
  * 运行侧护栏 —— services/lab_workspace_service 的 tool guard
  * 评测侧影子 —— scripts/evaluate_behavior_channel

三分类（kind）:
  * ``modify`` —— 学生本回合明确提出"帮我改 / 直接给码"。这是代改的第一判据。
  * ``hint``   —— "怎么改 / 帮我看看 / 报错了" 等问改法、求诊断，是 hint 请求。
  * ``none``   —— 无请求（概念提问 / 静默贴码 / 纯报错 / 只要提示）。

关键边界: "怎么改"（hint）≠ "帮我改"（modify）。请求主轴唯一化后，``modify_code``
的合法性第一判据 = ``kind == "modify"``；轮次 / 贴码行数 / 被拦轮数降级为时机细节，
只作免提示的加速通道，不单独构成放行依据。

显式逃生门（``declares_tool_context``）: 学生声明"工作项目 / 内部工具 / 快速任务"
等，视为工具性使用 → 直接放行且不提示。声明只作先验不作依据：伪装声明（如
"我公司的项目"，公司与被修饰词之间隔了"的"）不命中逃生门，仍按学习场景处理。

本模块是纯函数 + 冻结数据类，无 I/O、无第三方依赖，便于数据脚本与运行时共用。

Jev 三原语契约（Type-Safe AI System-1 类型化接口）:
  * ``Choice``      —— 上下文分类（learning / tool_use / disguised）
  * ``Score``       —— 学习置信度 0–1（即 ``intent_confidence``）
  * ``Noul``        —— "这是学习请求吗" 的是非概率
  ``judge_intent`` 是契约的**规则版默认实现**；接入 Jev（API）或本地小分类器后
  只需替换该实现体，调用方仍只依赖 ``IntentJudgment``。置信度低于
  ``CONFIDENCE_THRESHOLD`` 时不做硬判，走 ``decide_channel`` 的保守回落。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

__all__ = [
    "KIND_MODIFY",
    "KIND_HINT",
    "KIND_NONE",
    "CHOICE_LEARNING",
    "CHOICE_TOOL_USE",
    "CHOICE_DISGUISED",
    "CONFIDENCE_THRESHOLD",
    "RequestSignal",
    "IntentJudgment",
    "IntentJudge",
    "classify_request",
    "is_modify_request",
    "declares_tool_context",
    "judge_intent",
    "decide_code_write",
    "decide_channel",
]

KIND_MODIFY = "modify"
KIND_HINT = "hint"
KIND_NONE = "none"

# ── Jev 三原语取值（Choice）──
CHOICE_LEARNING = "learning"      # 学习场景
CHOICE_TOOL_USE = "tool_use"      # 工具性使用（显式逃生门）
CHOICE_DISGUISED = "disguised"    # 伪装可疑（工具性声明 + 偷懒话术）

# ── 置信度阈值：Score/Noul 低于此值不硬判 → 保守回落默认学习模式 ──
CONFIDENCE_THRESHOLD = 0.55

# ── 改码请求（优先级最高，必须先于 hint 命中） ──
# 精确性要求：不得误伤 "怎么改 / 帮我看看 / 给我点提示" 这类 hint 请求。
_MODIFY_RULES: tuple[tuple[str, str], ...] = (
    ("ask_help_do", r"帮我把.{0,12}?(?:改|修|写|重写|补|弄)"),
    ("direct_do", r"直接帮(?:我|你)?(?:把)?.{0,12}?(?:改|修|写|重写|补|弄|给)"),
    ("direct_verb", r"直接(?:改|修|写)"),
    ("only_change", r"(?:就|只)\s*改"),
    ("change_variants", r"(?:改好|改一下|改成|改掉|改完|重写|补完|补全|修好|写好)"),
    ("give_me_code", r"(?:给|发|贴|来)\s*(?:我|一份|个)(?!点).{0,8}(?:代码|版本|实现|答案|完整|正确|能过)"),
    ("give_complete", r"(?:给|发|贴).{0,6}(?:完整|正确|能过|标准).{0,4}(?:代码|版本|实现|答案)"),
    ("complete_version", r"(?:完整|正确|最终|能过|标准|参考).{0,4}(?:版|版本|代码|实现)"),
    ("direct_give", r"直接给"),
)

# ── hint 请求（问改法 / 求诊断 / 只要思路，不含改码动词） ──
_HINT_RULES: tuple[tuple[str, str], ...] = (
    ("how_change", r"怎么(?:改|写|做|弄|处理|调)"),
    ("how_to", r"如何(?:改|写|做|调|实现)"),
    ("help_look", r"帮我(?:看|检查|分析|诊断|看看|查)"),
    ("take_a_look", r"看一?下"),
    ("why", r"为什么|为何|原因|错在|哪里错|哪出"),
    ("hint_word", r"提示|思路|方向|引导|hint"),
    ("error", r"报错|异常|error|traceback"),
    ("confirm", r"对不对|对吗|是不是|是什么|什么意思"),
    ("help_generic", r"帮我|帮看"),
)

# ── 催促（时间压力）：记录信号，但不改变规则（催促 ≠ 授权，仍走"提示 1 次"） ──
_URGENCY_RE = re.compile(
    r"作业|截止|要交|交了|来不及|赶时间|没时间|时间不够|分钟|今晚|明天|今天|催|快点|赶紧|急"
)

# ── 范围收窄：只改一处 / 指定行 → 提示"请求范围"，供 patch 越权检查 ──
# 须与改码动词共现，避免误伤 "卡在这个 bug 上" / "我第 3 行看不懂" 这类非收窄表述。
_SCOPE_RE = re.compile(
    r"(?:只|就|仅)\s*(?:改|修|动|调整)|"
    r"(?:改|修|动)\s*第\s*\d+\s*行|"
    r"第\s*\d+\s*行\s*(?:改|修|动)|"
    r"(?:不要|别|勿)\s*(?:改|动|碰)\s*(?:其他|别的|其他地方|其他文件)"
)

# ── 分步确认：学生要求"改一处先问我 / 一步一步来" → 禁止一次性全改 ──
_STEP_CONFIRM_RE = re.compile(
    r"(?:每|逐)\s*(?:改|修)\s*一?\s*(?:处|步|个)|"
    r"改\s*(?:一?\s*(?:处|步)|完).{0,8}(?:问|确认|告诉我)|"
    r"(?:确认|同意|批准)\s*(?:后|再)\s*(?:改|动|继续)|"
    r"一步一步|逐步|一处一处|一处处来|分步(?:改|来)|"
    r"先改.{0,12}再改|改完再(?:改|说|问)"
)

# ── 显式逃生门：工具性使用声明（只作先验，可被伪装话术绕过 → 需事件级留痕） ──
_ESCAPE_RULES: tuple[tuple[str, str], ...] = (
    ("work_project", r"(?:工作|公司|业务|生产|线上)项目"),
    ("company_internal", r"公司内部"),
    ("internal_thing", r"内部(?:工具|脚本|项目|系统|平台)"),
    ("quick_task", r"快速任务|小任务|临时任务|私活|外包"),
    ("not_homework", r"不是(?:课程|学校|课堂|教学|上课)?\s*作业"),
    ("unrelated", r"(?:和|与)(?:学习|课程|作业)无关"),
)


@dataclass(frozen=True)
class RequestSignal:
    """一回合请求的判定结果（纯数据，可缓存 / 可回放）。"""

    kind: str                       # modify | hint | none
    has_urgency: bool               # 时间压力话术（仅记录，不改路径）
    scope_narrowed: bool            # 点了具体范围（只改一处 / 指定行）
    declares_tool_context: bool     # 命中显式逃生门（工具性使用声明）
    step_confirm: bool = False      # 要求学生分步确认（每改一处先问）
    evidence: tuple[str, ...] = ()  # 命中的规则名，便于留痕与复盘


def classify_request(text: str) -> RequestSignal:
    """判定一回合学生请求的语义类别与附带信号。"""
    body = text or ""
    evidence: list[str] = []

    kind = KIND_NONE
    for name, pattern in _MODIFY_RULES:
        if re.search(pattern, body):
            kind = KIND_MODIFY
            evidence.append(name)
            break
    if kind == KIND_NONE:
        for name, pattern in _HINT_RULES:
            if re.search(pattern, body):
                kind = KIND_HINT
                evidence.append(name)
                break

    declares = False
    for name, pattern in _ESCAPE_RULES:
        if re.search(pattern, body):
            declares = True
            evidence.append(name)
            break

    return RequestSignal(
        kind=kind,
        has_urgency=bool(_URGENCY_RE.search(body)),
        scope_narrowed=bool(_SCOPE_RE.search(body)),
        declares_tool_context=declares,
        step_confirm=bool(_STEP_CONFIRM_RE.search(body)),
        evidence=tuple(evidence),
    )


def is_modify_request(text: str) -> bool:
    """是否为学生明确提出的改码请求。"""
    return classify_request(text).kind == KIND_MODIFY


def declares_tool_context(text: str) -> bool:
    """是否命中工具性使用逃生门声明。"""
    return classify_request(text).declares_tool_context


def decide_code_write(
    signal: RequestSignal, *, valve_released: bool = False
) -> tuple[bool, bool, str]:
    """行为通道决策（方案 C）→ ``(allow, warn_once, reason)``。

    * 逃生门（工具性使用声明）→ 放行、不提示；
    * 明确改码请求 → 放行；若免提示阀未满足（``valve_released=False``）→ 先提示 1 次
      （"继续让我改代码就学不到知识点"）；
    * 其余（hint / none）→ 不放行：学生没开口要改，不得代改。

    ``valve_released`` 是旧的时机释放阀三条件（贴码 / 被拦轮数 / 掌握度）的组合，
    此处仅用于**免提示**，不再单独构成放行依据。
    """
    if signal.declares_tool_context:
        return True, False, "tool_context_escape"
    if signal.kind == KIND_MODIFY:
        return True, not valve_released, "student_request"
    return False, False, ""


# ══════════════════════════════════════════════════════════════════════════
# Jev 三原语契约（Type-Safe AI System-1 类型化接口）
#   契约稳定、实现可替换：规则版（本文件 ``judge_intent``）今日兜底，
#   Jev API 客户端 / 本地小分类器后续替换实现体即可，调用方只依赖
#   ``IntentJudgment``。对齐 dpo_alignment_plan §「意图判定器选型」。
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class IntentJudgment:
    """一次意图判定的结果（三原语落地结构，纯数据可缓存 / 回放）。

    * ``choice``       —— Choice：``learning`` | ``tool_use`` | ``disguised``
    * ``score``        —— Score：学习置信度 0–1（即 ``intent_confidence``）
    * ``is_learning``  —— Noul：「这是学习请求吗」的是非判定
    * ``noul_score``   —— Noul 的是非概率
    * ``kind``         —— 请求语义（modify / hint / none），供请求轴复用
    * ``fallback``     —— 低置信回落（True=保守走学习模式，不采信工具性声明）
    * ``ask_explicit`` —— 是否建议引导学生显式选择（触发「显式逃生门」对话）
    * ``evidence``     —— 命中的规则名，留痕与复盘
    """

    choice: str
    score: float
    is_learning: bool
    noul_score: float
    kind: str
    fallback: bool = False
    ask_explicit: bool = False
    evidence: tuple[str, ...] = ()


class IntentJudge(Protocol):
    """意图判定器契约：规则版 / Jev API / 本地小分类器都实现它。"""

    def judge(self, text: str, *, context: dict | None = None) -> IntentJudgment:
        ...


def judge_intent(text: str, *, context: dict | None = None) -> IntentJudgment:
    """规则版意图判定器（Jev 契约的默认实现 / 零依赖兜底）。

    ⚠️ 置信度为**信号强度启发式**，未经校准；接入 Jev 或本地小分类器后由真实
    模型概率替换（契约不变）。``context`` 预留工作区行为 / 画像后验输入，暂未消费。

    分类规则（对齐「判代价不判真伪」）：
      * 空文本 → 无法判定 → ``fallback``（保守学习模式 + 建议显式选择）；
      * 工具性声明 + 时间压力话术 → ``disguised``（伪装可疑）→ ``fallback``；
      * 纯工具性声明（无偷懒话术）→ ``tool_use``（逃生门）；
      * 明确改码 / 问改法 / 无请求 → ``learning``（走请求轴）。
    """
    signal = classify_request(text)
    body = (text or "").strip()
    evidence = signal.evidence

    if not body:
        return IntentJudgment(
            choice=CHOICE_LEARNING, score=0.30, is_learning=True,
            noul_score=0.50, kind=KIND_NONE,
            fallback=True, ask_explicit=True, evidence=evidence,
        )

    if signal.declares_tool_context:
        if signal.has_urgency:
            # 伪装可疑：声明工具性却夹带时间压力（"快截止了，算工作项目吧，直接改"）
            return IntentJudgment(
                choice=CHOICE_DISGUISED, score=0.45, is_learning=True,
                noul_score=0.55, kind=signal.kind,
                fallback=True, ask_explicit=True, evidence=evidence,
            )
        return IntentJudgment(
            choice=CHOICE_TOOL_USE, score=0.22, is_learning=False,
            noul_score=0.22, kind=signal.kind, evidence=evidence,
        )

    if signal.kind == KIND_MODIFY:
        return IntentJudgment(
            choice=CHOICE_LEARNING, score=0.70, is_learning=True,
            noul_score=0.75, kind=signal.kind, evidence=evidence,
        )
    if signal.kind == KIND_HINT:
        return IntentJudgment(
            choice=CHOICE_LEARNING, score=0.80, is_learning=True,
            noul_score=0.85, kind=signal.kind, evidence=evidence,
        )
    return IntentJudgment(
        choice=CHOICE_LEARNING, score=0.65, is_learning=True,
        noul_score=0.70, kind=signal.kind, evidence=evidence,
    )


def decide_channel(
    judgment: IntentJudgment, *, valve_released: bool = False
) -> tuple[bool, bool, str]:
    """基于三原语判定做行为通道决策（含阈值回落路由）→ ``(allow, warn_once, reason)``。

    与 ``decide_code_write`` 的差异：本函数纳入 Jev 的**阈值回落**——``fallback``
    时不硬判，保守走默认学习模式（不采信未校准的工具性声明），并在理由前缀
    标注来源（``fallback_learning`` / ``disguised``）。
    """
    if judgment.fallback:
        prefix = "disguised" if judgment.choice == CHOICE_DISGUISED else "fallback_learning"
        if judgment.kind == KIND_MODIFY:
            return True, not valve_released, f"{prefix}_request"
        return False, False, f"{prefix}_block"
    if judgment.choice == CHOICE_TOOL_USE:
        return True, False, "tool_context_escape"
    if judgment.kind == KIND_MODIFY:
        return True, not valve_released, "student_request"
    return False, False, ""
