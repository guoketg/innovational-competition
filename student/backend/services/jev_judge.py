# -*- coding: utf-8 -*-
"""Jev 意图判定器（TypeSafe System-1，经 OpenRouter Decisions API）。

实现 ``services.request_classifier.IntentJudge`` 契约：输入学生本回合文本
（+ 可选上下文），返回 ``IntentJudgment``（Choice/Score/Noul 三原语 + kind）。

要点:
  * 端点 ``POST https://openrouter.ai/api/alpha/decisions``——Jev 是决策模型
    （System One），**不能**走 ``chat/completions``（会返回 400 JSON parsing failed）。
  * 模型 ``typesafe/jev-1.13``；密钥仅从环境变量 ``OPENROUTER_API_KEY`` 读取，
    绝不写入受版本控制的文件。
  * **失败即回落**：无密钥 / 网络超时 / HTTP 非 200 / 解析失败 → 退回规则版
    ``judge_intent``，并在 ``evidence`` 记 ``jev_fallback:<reason>``，调用方无需感知。
  * ``last_usage`` / ``last_latency_ms`` 记录最近一次调用的成本与时延（离线评测用）。

政策口径（2026-10-14 定）: 「偷懒式直接要答案」（无工具性声明、纯索要结果）归
**learning/modify**——学生自己开口要改，提示 1 次后放行；``disguised`` 仅指
**可疑的工具性声明**（借时间压力 / 软化话术施压、声明不可采信）。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from services.request_classifier import (
    CONFIDENCE_THRESHOLD,
    IntentJudgment,
    judge_intent,
)

__all__ = ["JevIntentJudge", "DEFAULT_ENDPOINT", "DEFAULT_MODEL"]

DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
DEFAULT_TIMEOUT = 30.0

# Score 的 5 级 rubric：索引 0–4 → 归一化 /4 得学习置信度（与 Score 契约的 0–1 对齐）。
_SCORE_LEVELS = ["几乎纯工具性", "偏工具性", "中性/不确定", "偏学习", "明确的强学习意图"]

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
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")).strip()
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.last_usage: dict = {}
        self.last_latency_ms: int = 0
        self.total_usage: dict = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}

    # ── IntentJudge 契约 ──
    def judge(self, text: str, *, context: dict | None = None) -> IntentJudgment:
        body = (text or "").strip()
        if not self.api_key:
            return self._fallback(body, context, "no_api_key")
        state: dict = {"student_message": body}
        if context:
            state["context"] = context
        payload = {"model": self.model, "state": state, "questions": _QUESTIONS}

        started = time.monotonic()
        try:
            raw = self._post(payload)
        except Exception as exc:  # noqa: BLE001 —— 任何失败都回落，不阻断主流程
            reason = f"http_{getattr(exc, 'code', '')}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
            return self._fallback(body, context, reason)
        finally:
            self.last_latency_ms = int((time.monotonic() - started) * 1000)

        self.last_usage = raw.get("usage") or {}
        if self.last_usage:
            self.total_usage["calls"] += 1
            self.total_usage["input_tokens"] += int(self.last_usage.get("input_tokens", 0))
            self.total_usage["output_tokens"] += int(self.last_usage.get("output_tokens", 0))
            self.total_usage["cost"] += float(self.last_usage.get("cost", 0.0))
        try:
            return self._map(raw.get("answers") or {}, body)
        except Exception as exc:  # noqa: BLE001 —— 响应形状异常同样回落
            return self._fallback(body, context, f"parse_{type(exc).__name__}")

    # ── 内部 ──
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

    def _map(self, answers: dict, text: str) -> IntentJudgment:
        ctx = answers["context"]
        req = answers["request_kind"]
        noul = float(answers["is_learning"]["noul"])
        score_raw = float(answers["learning_confidence"]["score"])
        choice = str(ctx["choice"])
        kind = str(req["choice"])
        ctx_conf = float(ctx.get("confidence", 0.0))
        score = max(0.0, min(1.0, score_raw / (len(_SCORE_LEVELS) - 1)))
        fallback = ctx_conf < CONFIDENCE_THRESHOLD
        evidence = (
            f"jev:{choice}",
            f"kind:{kind}",
            f"ctx_conf:{ctx_conf:.2f}",
            f"score:{score:.2f}",
            f"noul:{noul:.2f}",
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
