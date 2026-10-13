"""防泄题护栏（Answer Guard）——量化并拦截导师回答里的“直接抄参考答案”。

判定规则（块级 + 篇级）：
- R1 参考答案行重叠：代码块有效行对参考答案有效行的 recall ≥ 0.6 且重叠 ≥ 5 行
  → severity=full，该块被拦截（替换为引导追问）。
- R2 长代码块：单个围栏块 ≥ 15 行且全篇代码 ≥ 25 行
  → severity=partial，放行但记录（疑似完整实现，评测统计用）。
- 两者都不命中 → severity=ok。

时机释放阀（release valve）：护栏不是“永远不给答案”，而是“学生给出自己的
尝试之前不给完整参考实现”（generation first，再给 worked example）。满足
任一条件时 R1 不拦截，改为放行“参考实现 + 对照讲解”，severity=released：
- student_attempt：学生本轮消息里已贴出自己的代码（≥3 行有效代码）；
- blocked_rounds：同一用户同一关卡累计被拦截 ≥ RELEASE_MIN_BLOCKED_ROUNDS 轮，
  说明确实卡住，继续只追问会把学生逼死；
- mastery：该用户该关卡的掌握度估计 ≥ RELEASE_MIN_MASTERY，学生已达标，
  参考实现不再构成“过早直给”（掌握度取工作区阶段状态与 knowledge_mastery
  表两个证据源的较高者，无证据按 0 处理 → 不释放）。
不传 release 参数即维持原拦截行为（评测脚本默认不受影响）。

每次判定都会追加一行 JSONL 到 data/answer_guard_log.jsonl，供“模型有多少次
还直接改代码/贴答案”的量化评测直接统计。
"""

from __future__ import annotations

import importlib.util
import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# 围栏代码块：```lang\n ... ```
_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)

# 块级 R1 命中阈值
R1_RECALL_THRESHOLD = 0.6
R1_MIN_OVERLAP_LINES = 5
# 篇级 R2 命中阈值
R2_MIN_BLOCK_LINES = 15
R2_MIN_TOTAL_CODE_LINES = 25
# 有效行最短长度：短行（return、}、);）不参与重叠统计
_MIN_SIGNIFICANT_LEN = 5

_LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "answer_guard_log.jsonl"

_BLOCK_MESSAGE = (
    "【防泄题护栏】上面这段代码与本关参考答案高度重合，已拦截。"
    "请先自己写出关键步骤（哪怕不完整），把你写的版本发给我——"
    "我看到你的尝试后，会把参考实现和你的写法对照着讲给你看。"
)

# ── 时机释放阀：释放条件与放行话术 ──
RELEASE_MIN_STUDENT_CODE_LINES = 3   # 学生本轮贴出的有效代码行数达到该值 → 释放
RELEASE_MIN_BLOCKED_ROUNDS = 2       # 同用户同关卡累计被拦次数达到该值 → 释放
RELEASE_MIN_MASTERY = 0.7            # 该关卡掌握度估计达到该值 → 释放（0.7 档与
                                     # teaching_policy_service.mastery_hint_level 的
                                     # “掌握度高→提示保守”阈值一致，同一参数框架）

_RELEASE_NOTE = {
    "student_attempt": (
        "【护栏已释放】看到你已经写出自己的版本了——先自己对照下面的参考实现找差异，"
        "再看讲解，这样记得最牢：\n\n"
    ),
    "blocked_rounds": (
        "【护栏已释放】你已经试了好几轮，现在给你本关的完整参考实现与对照讲解，"
        "重点看它和你思路的差别：\n\n"
    ),
    "mastery": (
        "【护栏已释放】你在这关的掌握度已经达到标准，参考实现可以直接看——"
        "重点对照它检验自己的写法是否还有遗漏的边界情况：\n\n"
    ),
}


# ── 参考答案加载（进程内缓存） ──
# 注意：REFERENCE_SOLUTIONS（正课）与 VARIANT_REFERENCE_SOLUTIONS（变式）
# 共用 "1-1"~"4-3" 键，绝不能互相 update 覆盖——护栏必须两份都能比对。

_reference_cache: dict[str, dict[str, str]] | None = None


def _load_reference_maps() -> dict[str, dict[str, str]]:
    """返回 {"main": 正课参考解, "variant": 变式参考解}（按关卡 ID 索引）。"""
    global _reference_cache
    if _reference_cache is not None:
        return _reference_cache
    main: dict[str, str] = {}
    variant: dict[str, str] = {}
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_lab_content.py"
    try:
        spec = importlib.util.spec_from_file_location("_guard_ref_solutions", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        main.update(getattr(module, "REFERENCE_SOLUTIONS", {}) or {})
        variant.update(getattr(module, "VARIANT_REFERENCE_SOLUTIONS", {}) or {})
    except Exception:
        main, variant = {}, {}
    _reference_cache = {"main": main, "variant": variant}
    return _reference_cache


def load_reference_solution(exercise_id: str) -> str:
    """取本关**正课**参考答案源码；没有则返回空串。"""
    if not exercise_id:
        return ""
    return str(_load_reference_maps()["main"].get(str(exercise_id), "") or "")


def load_variant_reference_solution(exercise_id: str) -> str:
    """取本关**变式**参考答案源码；没有则返回空串。"""
    if not exercise_id:
        return ""
    return str(_load_reference_maps()["variant"].get(str(exercise_id), "") or "")


def load_guard_references(exercise_id: str) -> list[str]:
    """护栏比对用参考解集合：正课 + 变式（命中任一即拦截）。"""
    if not exercise_id:
        return []
    maps = _load_reference_maps()
    key = str(exercise_id)
    return [s for s in (maps["main"].get(key, ""), maps["variant"].get(key, "")) if s]


# ── 输入侧关卡识别（问题文本 → exercise_id）──
# 只认「指向本平台关卡」的问题：命中关卡才启用护栏；通用编程问题
# （如「归并排序的原理是什么」）不触发，避免误伤合理求码场景。
# 注意：即使误触发，R1 仍要求回答与参考答案行重合 ≥60% 才拦截，
# 所以识别偏宽松的代价只是多一次 evaluate，而不是误拦。

# 强标识：平台自定义函数名，出现在问题里基本就是关卡题面/关卡代码。
_STRONG_LAB_SIGNALS: dict[str, tuple[str, ...]] = {
    "1-1": ("array_insert",),
    "1-2": ("reverse_list",),
    "1-3": ("eval_rpn",),
    "2-1": ("bst_insert", "bst_search"),
    "2-2": ("bst_inorder", "bst_level_order"),
    "2-3": ("heap_shift_up", "heap_shift_down"),
    "3-1": ("build_adjacency", "dfs_order"),
    "3-2": ("uf_find_root", "uf_compress"),
    "3-3": ("bfs_shortest_path",),
    "4-1": ("toolbox_call", "describe_toolbox"),
    "4-3": ("lru_simulate",),
}

# 变式关卡强标识：target 函数名单一来源是 agent_lab_variants.ADDITIONAL_VARIANT_SPECS，
# 懒加载避免 import 期开销；加载失败则退化为只认正课标识。
_VARIANT_SIGNALS: dict[str, tuple[str, ...]] | None = None


def _variant_strong_signals() -> dict[str, tuple[str, ...]]:
    global _VARIANT_SIGNALS
    if _VARIANT_SIGNALS is None:
        signals: dict[str, tuple[str, ...]] = {}
        try:
            path = Path(__file__).resolve().parent / "agent_lab_variants.py"
            spec = importlib.util.spec_from_file_location("_guard_variant_specs", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            specs = getattr(module, "ADDITIONAL_VARIANT_SPECS", {}) or {}
            for exercise_id, cfg in specs.items():
                target = str((cfg or {}).get("target") or "").strip().lower()
                if target:
                    signals[str(exercise_id)] = (target,)
        except Exception:
            signals = {}
        _VARIANT_SIGNALS = signals
    return _VARIANT_SIGNALS

# 主题词：必须搭配「关卡语境」或「关卡编号」才算关卡问题。
_EXERCISE_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "1-1": ("数组插入", "插入元素", "下标越界", "越界索引"),
    "1-2": ("反转链表", "链表反转", "单链表反转", "逆转链表"),
    "1-3": ("逆波兰", "后缀表达式"),
    "2-1": ("二叉搜索树插入", "二叉排序树", "BST插入"),
    "2-2": ("中序遍历", "先序遍历", "后序遍历", "层序遍历", "二叉树遍历"),
    "2-3": ("堆上浮", "上浮下沉"),
    "2-4": ("堆排序",),
    "3-1": ("邻接表", "深度优先遍历", "DFS遍历"),
    "3-2": ("并查集", "路径压缩", "union find", "union-find"),
    "3-3": ("最短路径", "广度优先遍历"),
    "4-1": ("算法工具箱",),
    "4-2": ("归并排序",),
    "4-3": ("LRU", "缓存淘汰", "两数之和"),
}

# 关卡语境词：出现这些词且命中主题词时，视为关卡问题。
_LAB_CONTEXT_RE = re.compile(
    r"关卡|本关|闯关|过关|实验题|作业|考核|题面|参考答案|题解|判题|隐藏用例"
)
# 关卡编号（1-1 ~ 4-3）
_EXERCISE_ID_RE = re.compile(r"\b[1-4]-[1-3]\b")


def detect_exercise(question: str) -> str:
    """问题文本 → 关卡 ID；不是关卡问题返回空串。

    两级判定：
    1. 强标识（平台自定义函数名）→ 直接命中；
    2. 关卡语境词或关卡编号 + 主题词 → 命中。
    """
    text = str(question or "")
    if not text.strip():
        return ""
    lowered = text.lower()

    for exercise_id, signals in _STRONG_LAB_SIGNALS.items():
        if any(signal in lowered for signal in signals):
            return exercise_id
    for exercise_id, signals in _variant_strong_signals().items():
        if any(signal in lowered for signal in signals):
            return exercise_id

    has_context = bool(_LAB_CONTEXT_RE.search(text))
    matched_id = _EXERCISE_ID_RE.search(text)
    if not (has_context or matched_id):
        return ""
    # 关卡编号 + 关卡语境 → 直接按编号定位（题面未重复主题词也能识别）
    if matched_id and has_context:
        exercise_id = matched_id.group(0)
        if exercise_id in _EXERCISE_TOPIC_KEYWORDS or exercise_id in _STRONG_LAB_SIGNALS:
            return exercise_id
    for exercise_id, keywords in _EXERCISE_TOPIC_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return exercise_id
    return ""


# ── 文本分析 ──

def extract_code_blocks(text: str) -> list[dict]:
    """返回 [{"lang", "code", "start", "end"}]，start/end 为在原文中的字符下标。"""
    return [
        {"lang": (match.group(1) or "").strip(), "code": match.group(2),
         "start": match.start(), "end": match.end()}
        for match in _FENCE_RE.finditer(text or "")
    ]


def _significant_line_list(text: str) -> list[str]:
    """有效代码行（有序、不去重）：忽略空行/纯注释行/过短行。"""
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if len(line) < _MIN_SIGNIFICANT_LEN:
            continue
        if line.startswith(("#", "//", "/*", "*", "--")):
            continue
        lines.append(line)
    return lines


def _significant_lines(text: str) -> set[str]:
    """有效代码行集合（重叠比对用）。"""
    return set(_significant_line_list(text))


def _ref_line_sets(reference_solution) -> list[set[str]]:
    """参考解（字符串或字符串序列）→ 有效行集合列表；空参考被剔除。"""
    if isinstance(reference_solution, str):
        refs = [reference_solution]
    else:
        refs = [str(item or "") for item in (reference_solution or ())]
    return [lines for ref in refs if (lines := _significant_lines(ref))]


# ── 时机释放阀：判定本轮该不该放行完整参考讲解 ──

def count_student_code_lines(question: str) -> int:
    """学生消息里围栏代码块的有效代码行数（判断“是否已动手尝试”，不去重）。"""
    return sum(
        len(_significant_line_list(block["code"]))
        for block in extract_code_blocks(str(question or ""))
    )


def count_blocked_rounds(user_id, exercise_id) -> int:
    """日志里同一用户、同一关卡的累计拦截次数（兼容 user_id/user 两种键）。"""
    if not user_id or not exercise_id:
        return 0
    try:
        raw_lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    count = 0
    for raw in raw_lines:
        try:
            entry = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not entry.get("blocked"):
            continue
        entry_user = entry.get("user_id", entry.get("user"))
        entry_exercise = entry.get("exercise_id", entry.get("exercise"))
        if str(entry_user) == str(user_id) and str(entry_exercise) == str(exercise_id):
            count += 1
    return count


def evaluate_mastery(user_id, exercise_id) -> float:
    """该用户该关卡的掌握度估计，0..1。

    两个证据源取较高者（任一异常/缺失按 0 处理 → 不释放，向后兼容）：
    - 工作区阶段状态：.lab-state.json + stage_mastery（练习专属，最直接）；
    - knowledge_mastery 表：能力验证 defense/repair/variant 评分写入的掌握度
      （按知识模块标签或 source_exercise_id 匹配）。
    """
    if not user_id or not exercise_id:
        return 0.0
    return max(
        _mastery_from_workspace(user_id, exercise_id),
        _mastery_from_db(user_id, exercise_id),
    )


def _mastery_from_workspace(user_id, exercise_id) -> float:
    """关卡工作区的阶段掌握度（无工作区/无状态按 0 计）。"""
    try:
        from services import lab_workspace_service as lab
        from services.teaching_policy_service import stage_mastery
        if exercise_id not in lab.SPECS:
            return 0.0
        root = lab.WORKSPACE_ROOT / f"user-{int(user_id)}" / lab._safe_part(exercise_id)
        if not (root / ".lab-state.json").is_file():
            return 0.0
        state = lab._read_state(root)
        course = lab._course(exercise_id)
        stage = lab._next_course_stage(course, state.get("completed_stages", []))
        return float(stage_mastery(state, stage["id"]))
    except Exception:
        return 0.0


def _mastery_from_db(user_id, exercise_id) -> float:
    """knowledge_mastery 表里的掌握度（按关卡或其知识模块取最高）。"""
    try:
        from database import get_db
        from services.judge_service import get_flagship_exercise
        exercise = get_flagship_exercise(exercise_id) or {}
        tag = str(exercise.get("module") or "")
        conn = get_db()
        try:
            if tag:
                row = conn.execute(
                    "SELECT MAX(mastery_score) FROM knowledge_mastery "
                    "WHERE user_id = ? AND (knowledge_tag = ? OR source_exercise_id = ?)",
                    (user_id, tag, exercise_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT MAX(mastery_score) FROM knowledge_mastery "
                    "WHERE user_id = ? AND source_exercise_id = ?",
                    (user_id, exercise_id),
                ).fetchone()
        finally:
            conn.close()
        return float(row[0] or 0.0) if row else 0.0
    except Exception:
        return 0.0


def evaluate_release(user_id, exercise_id, question: str) -> tuple[bool, str]:
    """返回 (是否释放护栏, 释放原因)；原因 ∈ {"student_attempt", "blocked_rounds", "mastery", ""}。"""
    if not exercise_id:
        return False, ""
    # 前两个条件只做内存/日志统计，便宜；mastery 要读工作区与数据库，放最后
    if count_student_code_lines(question) >= RELEASE_MIN_STUDENT_CODE_LINES:
        return True, "student_attempt"
    if count_blocked_rounds(user_id, exercise_id) >= RELEASE_MIN_BLOCKED_ROUNDS:
        return True, "blocked_rounds"
    if evaluate_mastery(user_id, exercise_id) >= RELEASE_MIN_MASTERY:
        return True, "mastery"
    return False, ""


def release_note(release_reason: str) -> str:
    """释放时拼在参考讲解前的引导语（说明这次为什么放行）。"""
    return _RELEASE_NOTE.get(release_reason) or _RELEASE_NOTE["blocked_rounds"]


# ── 判定 ──

@dataclass
class GuardVerdict:
    blocked: bool = False
    severity: str = "ok"                      # ok | partial | full
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _block_is_leak(block_code: str, ref_sets: list[set[str]]) -> tuple[bool, int, float, int]:
    """对每份参考解求 (重叠, recall)，返回 (命中任一?, 最优重叠, 最优recall, 对应参考解行数)。"""
    if not ref_sets:
        return False, 0, 0.0, 0
    block_lines = _significant_lines(block_code)
    best = (False, 0, 0.0, len(ref_sets[0]))
    for ref in ref_sets:
        overlap = len(block_lines & ref)
        recall = overlap / len(ref)
        if recall >= R1_RECALL_THRESHOLD and overlap >= R1_MIN_OVERLAP_LINES:
            return True, overlap, recall, len(ref)
        if recall > best[2]:
            best = (False, overlap, recall, len(ref))
    return best


def evaluate(answer: str, reference_solution="") -> GuardVerdict:
    """对整篇回答做护栏判定（不修改文本）。

    reference_solution 可为单个参考解字符串，或参考解序列
    （如 load_guard_references() 返回的正课+变式两份）——命中任一即拦。
    """
    verdict = GuardVerdict()
    blocks = extract_code_blocks(answer)
    ref_sets = _ref_line_sets(reference_solution)

    total_code_lines = sum(
        len([ln for ln in block["code"].splitlines() if ln.strip()])
        for block in blocks
    )
    max_block_lines = max(
        (len([ln for ln in block["code"].splitlines() if ln.strip()]) for block in blocks),
        default=0,
    )
    max_recall, max_overlap = 0.0, 0
    ref_line_count = len(ref_sets[0]) if ref_sets else 0
    leak_blocks = 0
    for block in blocks:
        hit, overlap, recall, matched_ref_lines = _block_is_leak(block["code"], ref_sets)
        if hit:
            leak_blocks += 1
        if recall > max_recall:
            max_recall, ref_line_count = recall, matched_ref_lines
        max_overlap = max(max_overlap, overlap)

    verdict.metrics = {
        "ref_lines": ref_line_count,
        "ref_variants": len(ref_sets),
        "code_blocks": len(blocks),
        "total_code_lines": total_code_lines,
        "max_block_lines": max_block_lines,
        "leak_blocks": leak_blocks,
        "max_recall": round(max_recall, 3),
        "max_overlap_lines": max_overlap,
    }

    if leak_blocks:
        verdict.severity = "full"
        verdict.blocked = True
        verdict.reasons.append(
            f"R1参考答案重叠：{leak_blocks} 个代码块 recall≥{R1_RECALL_THRESHOLD}"
            f"（最高 {max_recall:.0%}，重叠 {max_overlap} 行）"
        )
    elif max_block_lines >= R2_MIN_BLOCK_LINES and total_code_lines >= R2_MIN_TOTAL_CODE_LINES:
        verdict.severity = "partial"
        verdict.reasons.append(
            f"R2疑似完整实现：单块 {max_block_lines} 行、全篇 {total_code_lines} 行"
        )
    return verdict


def apply_guard(answer: str, reference_solution="", *, release: bool = False) -> tuple[str, GuardVerdict]:
    """非流式：拦截命中 R1 的代码块，替换为引导追问，返回 (新文本, 判定)。

    release=True（时机释放阀）：即使命中 R1 也不拦截，severity 记为
    "released"（blocked=False，调用方因此不会触发重生成）。
    """
    verdict = evaluate(answer, reference_solution)
    if not verdict.blocked:
        return answer, verdict
    if release:
        verdict.blocked = False
        verdict.severity = "released"
        verdict.reasons.append("R1命中但按时机释放阀放行（学生已有尝试/多轮被拦/掌握度达标）")
        return answer, verdict

    ref_sets = _ref_line_sets(reference_solution)
    parts: list[str] = []
    cursor = 0
    for block in extract_code_blocks(answer):
        hit, _, _, _ = _block_is_leak(block["code"], ref_sets)
        parts.append(answer[cursor:block["start"]])
        if hit:
            parts.append(_BLOCK_MESSAGE)
        else:
            parts.append(answer[block["start"]:block["end"]])
        cursor = block["end"]
    parts.append(answer[cursor:])
    return "".join(parts), verdict


# ── 重生成再检（regenerate-and-recheck） ──

REGEN_FEEDBACK = (
    "【系统提示·护栏重生成】你的上一版回答与本关参考答案高度重合，已被拦截。"
    "请重新回答：只给定位思路和一个引导性提问；不要输出与参考答案重合的完整修复代码；"
    "如需示例最多 3 行且不得包含关键修复行。"
)
# 释放阀打开时不注入 REGEN_FEEDBACK（此时学生已经有过尝试/多轮被拦，
# 完整参考讲解正是该给的，无需再让模型“憋着不给代码”）。


async def regenerate_and_recheck(
    first_answer: str,
    generate_retry,
    exercise_id: str,
    *,
    max_attempts: int = 1,
    log_context: dict | None = None,
    release: bool = False,
    release_reason: str = "",
) -> tuple[str, GuardVerdict, int]:
    """对首版答案做护栏判定；被拦时带纠正反馈重新生成并复检（有界重试）。

    - 首版通过 → 原样返回，attempts=0。
    - 被拦 → await generate_retry(REGEN_FEEDBACK) 重生成，复检通过则返回重生成答案。
    - 重试用尽仍被拦 → 返回首版的拦截替换文本。
    - release=True 且命中 R1 → 时机释放：不拦截也不重生成，返回
      引导语 + 完整参考讲解，attempts=0，日志 channel=released。
    - 首版被拦时，最终结果（无论重生成是否成功）都会记一条日志，
      channel 分别为 regen_passed / regen_failed，供评测统计闭环有效性。
    """
    reference = load_guard_references(exercise_id)
    first_text, first_verdict = apply_guard(first_answer, reference, release=release)
    if first_verdict.severity == "released":
        log_guard_event(first_verdict, {
            **(log_context or {}), "channel": "released",
            "release_reason": release_reason,
        })
        return release_note(release_reason) + first_text, first_verdict, 0
    if not first_verdict.blocked:
        # 未拦截但命中 R2（partial）时仍记一条，保持原调用方日志口径
        if first_verdict.severity != "ok":
            log_guard_event(first_verdict, log_context)
        return first_text, first_verdict, 0

    verdict = first_verdict
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        try:
            retry_answer = await generate_retry(REGEN_FEEDBACK)
        except Exception:
            break
        retry_text, retry_verdict = apply_guard(str(retry_answer or ""), reference)
        if not retry_verdict.blocked:
            log_guard_event(retry_verdict, {
                **(log_context or {}), "channel": "regen_passed", "attempts": attempts,
            })
            return retry_text, retry_verdict, attempts
        verdict = retry_verdict

    log_guard_event(verdict, {
        **(log_context or {}), "channel": "regen_failed", "attempts": attempts,
    })
    return first_text, verdict, attempts


# ── 评测日志 ──

def log_guard_event(verdict: GuardVerdict, context: dict | None = None) -> None:
    """追加一条判定记录到 JSONL（失败静默，不影响主流程）。"""
    try:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            **(context or {}),
            **verdict.to_dict(),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ── 流式围栏过滤器 ──

class GuardedStreamFilter:
    """流式场景的围栏缓冲过滤器。

    - 围栏外：直接透传，但尾部最多缓存 2 个反引号字符，防止 ``` 被 chunk 拆开
      时误判为普通文本。
    - 围栏内：整块缓冲，闭合时对参考答案评估；命中 R1 则下发占位引导文本，
      否则原样下发。
    - 每次拦截产生 {"type": "guard"} 事件，由调用方在 SSE 流里 yield。

    feed()/close() 返回 [(kind, payload)]，kind ∈ {"text", "event"}。
    """

    def __init__(self, reference_solution="", enabled: bool = True, *,
                 release: bool = False, release_reason: str = "",
                 log_context: dict | None = None):
        # reference_solution 可为字符串或参考解序列（正课+变式），命中任一即拦
        self.ref_sets = _ref_line_sets(reference_solution)
        self.enabled = bool(enabled and self.ref_sets)
        self.release = bool(release)
        self.release_reason = release_reason
        self.log_context = dict(log_context or {})
        self.blocked_count = 0
        self.released_count = 0
        self._release_note_sent = False
        self._outside = ""      # 围栏外已确认的文本
        self._fence: str | None = None  # None=围栏外；str=围栏内累积缓冲
        self._r2_code_lines = 0
        self._r2_max_block = 0

    # -- 公共接口 --

    def feed(self, chunk: str) -> list[tuple[str, object]]:
        if not chunk:
            return []
        if not self.enabled:
            self._count_lines(chunk)
            return [("text", chunk)]

        out: list[tuple[str, object]] = []
        buf = self._outside + chunk
        self._outside = ""

        while buf:
            if self._fence is None:
                idx = buf.find("```")
                if idx == -1:
                    # 可能是被拆开的 ``` 开头：尾部 1~2 个反引号先缓存等下一 chunk
                    tail = len(buf) - len(buf.rstrip("`"))
                    keep = min(tail, 2)
                    emit, hold = buf[: len(buf) - keep], buf[len(buf) - keep :]
                    if emit:
                        out.append(("text", emit))
                        self._count_lines(emit)
                    self._outside = hold
                    break
                if idx:
                    out.append(("text", buf[:idx]))
                    self._count_lines(buf[:idx])
                # 消费开始围栏：```lang\n（保留 ```，闭合时原样拼回）
                nl = buf.find("\n", idx + 3)
                if nl == -1:
                    # 开始围栏尚未收全（还没有换行符），先缓存
                    self._outside = buf[idx:]
                    break
                self._fence = buf[idx: nl + 1]  # ``` + 语言声明 + 换行
                buf = buf[nl + 1:]
            else:
                # 在 fence+chunk 合并缓冲上找闭合，避免 ``` 被 chunk 拆开漏检
                merged = self._fence + buf
                close_idx = self._find_fence_close(merged)
                if close_idx is None:
                    # 尾部可能正在形成 ```，整体缓存等下一 chunk
                    self._fence = merged
                    break
                rest = merged[close_idx:]
                nl = rest.find("\n")
                if nl == -1:
                    # 闭合行尚未收全换行，等下一 chunk
                    self._fence = merged
                    break
                self._fence = None
                out.extend(self._emit_block(merged[:close_idx], closing=rest[: nl + 1]))
                buf = rest[nl + 1:]
        return out

    def end_round(self) -> list[tuple[str, object]]:
        """轮次边界（Function Calling 每轮结束）：结算未闭合围栏与尾部缓存，可继续 feed。"""
        out: list[tuple[str, object]] = []
        if self._fence is not None:
            out.extend(self._emit_block(self._fence, unterminated=True))
            self._fence = None
        if self._outside:
            out.append(("text", self._outside))
            self._count_lines(self._outside)
            self._outside = ""
        return out

    def close(self) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        if self._outside:
            out.append(("text", self._outside))
            self._count_lines(self._outside)
            self._outside = ""
        if self._fence is not None:
            out.extend(self._emit_block(self._fence, unterminated=True))
            self._fence = None
        verdict = self._r2_verdict()
        if verdict.severity != "ok":
            log_guard_event(verdict, {**self.log_context, "channel": "stream_r2"})
            out.append(("event", {"type": "guard", **verdict.to_dict()}))
        return out

    # -- 内部 --

    @staticmethod
    def _find_fence_close(buf: str) -> int | None:
        """跳过首行（开始围栏），查找独占一行的闭合 ```，返回其在 buf 中的下标。"""
        first_nl = buf.find("\n")
        start = first_nl + 1 if first_nl != -1 else len(buf)
        match = re.search(r"(?m)^[ \t]*```", buf[start:])
        if match is None:
            # 尾部可能是正在形成的 ```，留给下一次 feed 判断
            return None
        return start + match.start()

    def _emit_block(
        self, block: str, unterminated: bool = False, closing: str = ""
    ) -> list[tuple[str, object]]:
        """评估一个围栏块，返回要下发的 text/event 序列。closing 为闭合围栏行。"""
        nl = block.find("\n")
        header_len = nl + 1 if nl != -1 else len(block)
        code = block[header_len:]
        self._count_lines(code)

        if not self.ref_sets:
            return [("text", block + closing)]

        hit, overlap, recall, matched_ref_lines = _block_is_leak(code, self.ref_sets)
        if not hit:
            return [("text", block + closing)]

        metrics = {
            "ref_lines": matched_ref_lines,
            "ref_variants": len(self.ref_sets),
            "max_recall": round(recall, 3),
            "max_overlap_lines": overlap,
            "unterminated": unterminated,
        }

        # 时机释放阀：学生已有多轮尝试 → 原样放行完整参考实现，只补一句引导语
        if self.release:
            self.released_count += 1
            verdict = GuardVerdict(
                blocked=False,
                severity="released",
                reasons=[f"R1命中但按时机释放阀放行（{self.release_reason or 'blocked_rounds'}）"],
                metrics=metrics,
            )
            log_guard_event(verdict, {
                **self.log_context, "channel": "stream_released",
                "release_reason": self.release_reason,
            })
            out: list[tuple[str, object]] = []
            if not self._release_note_sent:
                self._release_note_sent = True
                out.append(("text", release_note(self.release_reason)))
            out.append(("text", block + closing))
            out.append(("event", {"type": "guard", **verdict.to_dict()}))
            return out

        self.blocked_count += 1
        verdict = GuardVerdict(
            blocked=True,
            severity="full",
            reasons=[f"R1参考答案重叠：recall {recall:.0%}（重叠 {overlap} 行）"],
            metrics=metrics,
        )
        log_guard_event(verdict, {**self.log_context, "channel": "stream"})
        return [
            ("text", _BLOCK_MESSAGE),
            ("event", {"type": "guard", **verdict.to_dict()}),
        ]

    def _count_lines(self, text: str) -> None:
        lines = [ln for ln in (text or "").splitlines() if ln.strip()]
        self._r2_code_lines += len(lines)
        self._r2_max_block = max(self._r2_max_block, len(lines))

    def _r2_verdict(self) -> GuardVerdict:
        verdict = GuardVerdict()
        verdict.metrics = {
            "total_code_lines": self._r2_code_lines,
            "max_block_lines": self._r2_max_block,
            "blocked_blocks": self.blocked_count,
        }
        if self.blocked_count:
            verdict.severity = "full"
            verdict.blocked = True
            verdict.reasons.append(f"流式拦截 {self.blocked_count} 个泄漏代码块")
        elif self._r2_max_block >= R2_MIN_BLOCK_LINES and self._r2_code_lines >= R2_MIN_TOTAL_CODE_LINES:
            verdict.severity = "partial"
            verdict.reasons.append(
                f"R2疑似完整实现：单块 {self._r2_max_block} 行、全篇 {self._r2_code_lines} 行"
            )
        return verdict
