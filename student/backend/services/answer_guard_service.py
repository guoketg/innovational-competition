"""防泄题护栏（Answer Guard）——量化并拦截导师回答里的“直接抄参考答案”。

判定规则（块级 + 篇级）：
- R1 参考答案行重叠：代码块有效行对参考答案有效行的 recall ≥ 0.6 且重叠 ≥ 5 行
  → severity=full，该块被拦截（替换为引导追问）。
- R2 长代码块：单个围栏块 ≥ 15 行且全篇代码 ≥ 25 行
  → severity=partial，放行但记录（疑似完整实现，评测统计用）。
- 两者都不命中 → severity=ok。

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
    "请先自己写出关键步骤（哪怕不完整），把你写的版本发给我，我再逐段给你提示。"
)


# ── 参考答案加载（进程内缓存） ──

_reference_cache: dict[str, str] | None = None


def _load_reference_solutions() -> dict[str, str]:
    global _reference_cache
    if _reference_cache is not None:
        return _reference_cache
    solutions: dict[str, str] = {}
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_lab_content.py"
    try:
        spec = importlib.util.spec_from_file_location("_guard_ref_solutions", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        solutions.update(getattr(module, "REFERENCE_SOLUTIONS", {}) or {})
        solutions.update(getattr(module, "VARIANT_REFERENCE_SOLUTIONS", {}) or {})
    except Exception:
        solutions = {}
    _reference_cache = solutions
    return solutions


def load_reference_solution(exercise_id: str) -> str:
    """取本关参考答案源码；没有则返回空串（护栏退化为只记录不拦截）。"""
    if not exercise_id:
        return ""
    return str(_load_reference_solutions().get(str(exercise_id), "") or "")


# ── 文本分析 ──

def extract_code_blocks(text: str) -> list[dict]:
    """返回 [{"lang", "code", "start", "end"}]，start/end 为在原文中的字符下标。"""
    return [
        {"lang": (match.group(1) or "").strip(), "code": match.group(2),
         "start": match.start(), "end": match.end()}
        for match in _FENCE_RE.finditer(text or "")
    ]


def _significant_lines(text: str) -> set[str]:
    """有效代码行：去空白、忽略空行/纯注释行/过短行。"""
    lines: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if len(line) < _MIN_SIGNIFICANT_LEN:
            continue
        if line.startswith(("#", "//", "/*", "*", "--")):
            continue
        lines.add(line)
    return lines


def _block_overlap(block_code: str, ref_lines: set[str]) -> tuple[int, float]:
    """代码块对参考答案的 (重叠行数, recall)。无参考时 recall=0。"""
    if not ref_lines:
        return 0, 0.0
    block_lines = _significant_lines(block_code)
    overlap = len(block_lines & ref_lines)
    return overlap, overlap / len(ref_lines)


# ── 判定 ──

@dataclass
class GuardVerdict:
    blocked: bool = False
    severity: str = "ok"                      # ok | partial | full
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _block_is_leak(block_code: str, ref_lines: set[str]) -> tuple[bool, int, float]:
    overlap, recall = _block_overlap(block_code, ref_lines)
    hit = bool(ref_lines) and recall >= R1_RECALL_THRESHOLD and overlap >= R1_MIN_OVERLAP_LINES
    return hit, overlap, recall


def evaluate(answer: str, reference_solution: str = "") -> GuardVerdict:
    """对整篇回答做护栏判定（不修改文本）。"""
    verdict = GuardVerdict()
    blocks = extract_code_blocks(answer)
    ref_lines = _significant_lines(reference_solution)

    total_code_lines = sum(
        len([ln for ln in block["code"].splitlines() if ln.strip()])
        for block in blocks
    )
    max_block_lines = max(
        (len([ln for ln in block["code"].splitlines() if ln.strip()]) for block in blocks),
        default=0,
    )
    max_recall, max_overlap = 0.0, 0
    leak_blocks = 0
    for block in blocks:
        hit, overlap, recall = _block_is_leak(block["code"], ref_lines)
        if hit:
            leak_blocks += 1
        max_recall = max(max_recall, recall)
        max_overlap = max(max_overlap, overlap)

    verdict.metrics = {
        "ref_lines": len(ref_lines),
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


def apply_guard(answer: str, reference_solution: str = "") -> tuple[str, GuardVerdict]:
    """非流式：拦截命中 R1 的代码块，替换为引导追问，返回 (新文本, 判定)。"""
    verdict = evaluate(answer, reference_solution)
    if not verdict.blocked:
        return answer, verdict

    ref_lines = _significant_lines(reference_solution)
    parts: list[str] = []
    cursor = 0
    for block in extract_code_blocks(answer):
        hit, _, _ = _block_is_leak(block["code"], ref_lines)
        parts.append(answer[cursor:block["start"]])
        if hit:
            parts.append(_BLOCK_MESSAGE)
        else:
            parts.append(answer[block["start"]:block["end"]])
        cursor = block["end"]
    parts.append(answer[cursor:])
    return "".join(parts), verdict


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

    def __init__(self, reference_solution: str = "", enabled: bool = True):
        self.ref_lines = _significant_lines(reference_solution)
        self.enabled = bool(enabled and self.ref_lines)
        self.blocked_count = 0
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
            log_guard_event(verdict, {"channel": "stream_r2"})
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

        if not self.ref_lines:
            return [("text", block + closing)]

        hit, overlap, recall = _block_is_leak(code, self.ref_lines)
        if not hit:
            return [("text", block + closing)]

        self.blocked_count += 1
        verdict = GuardVerdict(
            blocked=True,
            severity="full",
            reasons=[f"R1参考答案重叠：recall {recall:.0%}（重叠 {overlap} 行）"],
            metrics={
                "ref_lines": len(self.ref_lines),
                "max_recall": round(recall, 3),
                "max_overlap_lines": overlap,
                "unterminated": unterminated,
            },
        )
        log_guard_event(verdict, {"channel": "stream"})
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
