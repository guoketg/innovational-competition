# -*- coding: utf-8 -*-
"""Jev 意图判定器（TypeSafe System-1，经 OpenRouter Decisions API）。

实现 ``services.request_classifier.IntentJudge`` 契约：输入学生本回合文本
（+ 可选上下文），返回 ``IntentJudgment``（Choice/Score/Noul 三原语 + kind）。

要点:
  * 端点 ``POST https://openrouter.ai/api/alpha/decisions``——Jev 是决策模型
    （System One），**不能**走 ``chat/completions``（会返回 400 JSON parsing failed）。
  * 模型 ``typesafe/jev-1.13``；密钥按「用户配置优先、服务端环境变量兜底」解析，
    用户 Key 落库前已加密，任何日志都不输出明文。
  * **没有配置就不启用**：用户未配置且服务端未设置 ``OPENROUTER_API_KEY`` 时，
    ``resolve_api_key`` 返回空串，调用方直接走规则版判定。
  * **失败即回落**：无密钥 / 网络超时 / HTTP 非 200 / 解析失败 → 退回规则版
    ``judge_intent``，并在 ``evidence`` 记 ``jev_fallback:<reason>``，调用方无需感知。
  * ``last_usage`` / ``last_latency_ms`` 记录最近一次调用的成本与时延（离线评测用）。
  * **阈值可校准**：默认 0.55，可用构造参数或环境变量 ``JEV_CONFIDENCE_THRESHOLD``
    覆盖；``judge_raw`` + ``map_answers`` 允许对同一批模型回答做阈值扫描，
    离线校准不必重复花 API 费用。
  * **瞬时故障重试**：超时 / 连接失败 / 429 / 5xx 做指数退避重试（默认 2 次），
    仍失败才回落规则版；无密钥 / 解析失败不重试。
  * **同文缓存**：相同文本 + 上下文只调用一次 API（评测与阈值扫描复用）。

政策口径（2026-10-14 定）: 「偷懒式直接要答案」（无工具性声明、纯索要结果）归
**learning/modify**——学生自己开口要改，提示 1 次后放行；``disguised`` 仅指
**可疑的工具性声明**（借时间压力 / 软化话术施压、声明不可采信）。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from services.request_classifier import (
    CONFIDENCE_THRESHOLD,
    IntentJudgment,
    judge_intent,
)

__all__ = ["JevIntentJudge", "resolve_api_key", "DEFAULT_ENDPOINT", "DEFAULT_MODEL"]

logger = logging.getLogger(__name__)

API_KEY_ENV = "OPENROUTER_API_KEY"

DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_RETRY_BACKOFF = 0.5
THRESHOLD_ENV = "JEV_CONFIDENCE_THRESHOLD"
# 可重试的 HTTP 状态码（其余 4xx 属请求本身有问题，重试无意义）。
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

# Score 的 5 级 rubric：索引 0–4 → 归一化 /4 得学习置信度（与 Score 契约的 0–1 对齐）。
_SCORE_LEVELS = ["几乎纯工具性", "偏工具性", "中性/不确定", "偏学习", "明确的强学习意图"]


def resolve_api_key(user_id=None) -> str:
    """解析当前请求可用的 OpenRouter Key。

    顺序：用户个人配置 > 服务端环境变量；都没有则返回空串（= 不启用 Jev）。
    用户配置读取失败（如表尚未迁移）时静默退回环境变量，不阻断主流程。
    """
    if user_id is not None:
        try:
            from database import get_db
            from services.secret_store import decrypt_secret

            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT jev_api_key FROM user_llm_config WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            finally:
                conn.close()
            if row:
                key = decrypt_secret(dict(row).get("jev_api_key", "")).strip()
                if key:
                    return key
        except Exception as exc:  # noqa: BLE001 —— 配置读取失败不应影响答疑
            logger.debug("读取用户 Jev Key 失败（回退服务端配置）: %s", exc)
    return os.getenv(API_KEY_ENV, "").strip()

_QUESTIONS = {
    "context": {
        "type": "choice",
        "instructions": "这段学生消息属于哪种上下文？",
        "criteria": {
            "learning": "学习／练习语境：学生想学会、求讲解 / 思路 / 诊断；即使是偷懒式"
                        "『直接给答案』，只要仍在课程 / 学习语境，也算 learning。",
            "tool_use": "学生明确声明这不是学习，而是工作项目 / 内部工具 / 快速任务 / "
                        "生产任务，让 AI 直接代劳。",
            "disguised": "声称是工作 / 项目等工具语境，但措辞可疑（借时间压力、软化话术"
                         "施压，或明显为逃避学习而伪装）——此类声明不可采信。",
        },
    },
    "request_kind": {
        "type": "choice",
        "instructions": "学生本回合是否明确提出『帮我改 / 直接给答案』的请求？",
        "criteria": {
            "modify": "明确提出代改 / 给结果：『帮我改好』『直接改一下』『给我完整答案』"
                      "『帮我写完』等。",
            "hint": "要的是改法 / 诊断 / 思路 / 提示 / 查看：『怎么改』『帮我看看』"
                    "『报错了』『给点提示』等——不含代改请求。",
            "none": "无任何请求：纯概念提问、静默粘贴代码、或仅陈述。",
        },
    },
    "is_learning": {
        "type": "noul",
        "instructions": "这是学生想学习的请求吗（而不是把 AI 当成替自己动手的工具）？",
        "criteria": {
            "true": "意图落在学习 / 理解 / 自己动手上。",
            "false": "意图落在让 AI 代替完成、省去自己动手上。",
        },
    },
    "learning_confidence": {
        "type": "score",
        "instructions": "该请求学习意图的强度。",
        "criteria": _SCORE_LEVELS,
    },
}


class JevIntentJudge:
    """OpenRouter Decisions API 上的 Jev 判定器，实现 IntentJudge 契约。"""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT,
        threshold: float | None = None,
        retries: int = DEFAULT_RETRIES,
        use_cache: bool = True,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")).strip()
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.threshold = float(
            threshold if threshold is not None
            else os.getenv(THRESHOLD_ENV, CONFIDENCE_THRESHOLD)
        )
        self.retries = max(0, int(retries))
        self.use_cache = use_cache
        self._cache: dict[tuple[str, str], dict] = {}
        self.cache_hits = 0
        self.last_usage: dict = {}
        self.last_latency_ms: int = 0
        self.total_usage: dict = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}

    # ── IntentJudge 契约 ──
    def judge(self, text: str, *, context: dict | None = None) -> IntentJudgment:
        judgment, _raw = self.evaluate(text, context=context)
        return judgment

    def evaluate(
        self, text: str, *, context: dict | None = None, threshold: float | None = None,
    ) -> tuple[IntentJudgment, dict | None]:
        """判定一次并返回 ``(judgment, raw)``；raw 为 None 表示未调用成功（已回落）。"""
        body = (text or "").strip()
        if not self.api_key:
            return self._fallback(body, context, "no_api_key"), None
        try:
            raw = self.judge_raw(body, context=context)
        except Exception as exc:  # noqa: BLE001 —— 任何失败都回落，不阻断主流程
            reason = f"http_{getattr(exc, 'code', '')}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
            return self._fallback(body, context, reason), None
        if raw is None:
            return self._fallback(body, context, "no_api_key"), None
        try:
            return self.map_answers(raw.get("answers") or {}, threshold=threshold), raw
        except Exception as exc:  # noqa: BLE001 —— 响应形状异常同样回落
            return self._fallback(body, context, f"parse_{type(exc).__name__}"), raw

    def judge_raw(self, text: str, *, context: dict | None = None) -> dict | None:
        """调用 Decisions API 并返回原始响应；同文同上下文命中缓存。

        未配置密钥返回 None（不发起请求）。瞬时故障按 ``retries`` 指数退避重试。
        """
        if not self.api_key:
            return None
        body = (text or "").strip()
        cache_key = (body, json.dumps(context or {}, ensure_ascii=False, sort_keys=True, default=str))
        if self.use_cache and cache_key in self._cache:
            self.cache_hits += 1
            return self._cache[cache_key]

        state: dict = {"student_message": body}
        if context:
            state["context"] = context
        payload = {"model": self.model, "state": state, "questions": _QUESTIONS}

        started = time.monotonic()
        try:
            raw = self._post_with_retry(payload)
        finally:
            self.last_latency_ms = int((time.monotonic() - started) * 1000)

        self.last_usage = raw.get("usage") or {}
        if self.last_usage:
            self.total_usage["calls"] += 1
            self.total_usage["input_tokens"] += int(self.last_usage.get("input_tokens", 0))
            self.total_usage["output_tokens"] += int(self.last_usage.get("output_tokens", 0))
            self.total_usage["cost"] += float(self.last_usage.get("cost", 0.0))
        if self.use_cache:
            self._cache[cache_key] = raw
        return raw

    # ── 内部 ──
    def _post_with_retry(self, payload: dict) -> dict:
        attempt = 0
        while True:
            try:
                return self._post(payload)
            except urllib.error.HTTPError as exc:
                if exc.code not in _RETRYABLE_STATUS or attempt >= self.retries:
                    raise
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt >= self.retries:
                    raise
            time.sleep(DEFAULT_RETRY_BACKOFF * (2 ** attempt))
            attempt += 1

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def map_answers(self, answers: dict, *, threshold: float | None = None) -> IntentJudgment:
        """把 Decisions API 的 answers 映射为 ``IntentJudgment``（可指定阈值，供校准）。"""
        ctx = answers["context"]
        req = answers["request_kind"]
        noul = float(answers["is_learning"]["noul"])
        score_raw = float(answers["learning_confidence"]["score"])
        choice = str(ctx["choice"])
        kind = str(req["choice"])
        ctx_conf = float(ctx.get("confidence", 0.0))
        score = max(0.0, min(1.0, score_raw / (len(_SCORE_LEVELS) - 1)))
        cutoff = self.threshold if threshold is None else float(threshold)
        fallback = ctx_conf < cutoff
        evidence = (
            f"jev:{choice}",
            f"kind:{kind}",
            f"ctx_conf:{ctx_conf:.2f}",
            f"score:{score:.2f}",
            f"noul:{noul:.2f}",
            f"threshold:{cutoff:.2f}",
        )
        return IntentJudgment(
            choice=choice,
            score=score,
            is_learning=noul >= 0.5,
            noul_score=noul,
            kind=kind,
            fallback=fallback,
            ask_explicit=fallback,
            evidence=evidence,
        )

    def _fallback(self, text: str, context: dict | None, reason: str) -> IntentJudgment:
        j = judge_intent(text, context=context)
        return IntentJudgment(
            choice=j.choice,
            score=j.score,
            is_learning=j.is_learning,
            noul_score=j.noul_score,
            kind=j.kind,
            fallback=True,
            ask_explicit=True,
            evidence=tuple(j.evidence) + (f"jev_fallback:{reason}",),
        )
