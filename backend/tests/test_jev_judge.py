# -*- coding: utf-8 -*-
"""Jev 意图判定器（services/jev_judge.py）单元测试。

覆盖：阈值可配置/可覆盖、同文缓存、瞬时故障重试、失败回落规则版、成本累计。
全部离线（不访问 OpenRouter），用 fake ``_post`` 或空密钥。
"""

from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.jev_judge import JevIntentJudge, resolve_api_key  # noqa: E402


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params=None):
        return _FakeCursor(self.row)

    def close(self):
        pass


def _answers(choice="learning", kind="modify", conf=0.90, noul=0.8, score=3) -> dict:
    return {
        "context": {"choice": choice, "confidence": conf},
        "request_kind": {"choice": kind, "confidence": 0.9},
        "is_learning": {"noul": noul},
        "learning_confidence": {"score": score},
    }


def _raw(answers: dict, *, cost: float = 0.001) -> dict:
    return {
        "answers": answers,
        "usage": {"input_tokens": 100, "output_tokens": 20, "cost": cost},
    }


class ApiKeyResolutionTests(unittest.TestCase):
    """用户配置优先、服务端环境变量兜底、未配置返回空串（= 不启用 Jev）。"""

    def test_user_key_takes_priority_over_env(self):
        fake = _FakeConn({"jev_api_key": "sk-or-v1-user"})
        with mock.patch("database.get_db", return_value=fake), \
                mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-v1-server"}):
            self.assertEqual(resolve_api_key(7), "sk-or-v1-user")

    def test_env_is_used_when_user_key_missing(self):
        fake = _FakeConn({"jev_api_key": ""})
        with mock.patch("database.get_db", return_value=fake), \
                mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-v1-server"}):
            self.assertEqual(resolve_api_key(7), "sk-or-v1-server")

    def test_no_config_returns_empty(self):
        fake = _FakeConn(None)
        with mock.patch("database.get_db", return_value=fake), \
                mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
            self.assertEqual(resolve_api_key(7), "")


class ThresholdTests(unittest.TestCase):
    def test_threshold_defaults_to_contract_constant(self):
        judge = JevIntentJudge(api_key="k")
        self.assertAlmostEqual(judge.threshold, 0.55)

    def test_threshold_can_come_from_env(self):
        with mock.patch.dict("os.environ", {"JEV_CONFIDENCE_THRESHOLD": "0.62"}):
            self.assertAlmostEqual(JevIntentJudge(api_key="k").threshold, 0.62)
        self.assertAlmostEqual(JevIntentJudge(api_key="k", threshold=0.48).threshold, 0.48)

    def test_map_answers_threshold_override_flips_fallback(self):
        judge = JevIntentJudge(api_key="k", threshold=0.55)
        answers = _answers(conf=0.52)
        self.assertTrue(judge.map_answers(answers).fallback)
        self.assertFalse(judge.map_answers(answers, threshold=0.50).fallback)
        evidence = judge.map_answers(answers, threshold=0.50).evidence
        self.assertIn("threshold:0.50", evidence)


class CacheAndUsageTests(unittest.TestCase):
    def test_same_text_hits_cache_once(self):
        judge = JevIntentJudge(api_key="k")
        calls = {"n": 0}

        def fake_post(payload):
            calls["n"] += 1
            return _raw(_answers())

        with mock.patch.object(judge, "_post", side_effect=fake_post):
            first = judge.judge_raw("帮我改一下")
            second = judge.judge_raw("帮我改一下")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(judge.cache_hits, 1)
        self.assertEqual(first, second)
        self.assertEqual(judge.total_usage["calls"], 1)

    def test_context_is_part_of_cache_key(self):
        judge = JevIntentJudge(api_key="k")
        calls = {"n": 0}

        def fake_post(payload):
            calls["n"] += 1
            return _raw(_answers(), cost=0.002)

        with mock.patch.object(judge, "_post", side_effect=fake_post):
            judge.judge_raw("帮我改一下", context={"blocked_rounds": 0})
            judge.judge_raw("帮我改一下", context={"blocked_rounds": 2})
        self.assertEqual(calls["n"], 2)
        self.assertEqual(judge.total_usage["calls"], 2)
        self.assertAlmostEqual(judge.total_usage["cost"], 0.004)


class RetryTests(unittest.TestCase):
    def _http_error(self, code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("https://example", code, "err", {}, None)

    def test_retries_transient_5xx_then_succeeds(self):
        judge = JevIntentJudge(api_key="k", retries=2)
        attempts = {"n": 0}

        def fake_post(payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise self._http_error(503)
            return _raw(_answers())

        with mock.patch.object(judge, "_post", side_effect=fake_post), \
                mock.patch("services.jev_judge.time.sleep"):
            raw = judge.judge_raw("帮我改一下")
        self.assertEqual(attempts["n"], 2)
        self.assertIn("answers", raw)

    def test_non_retryable_4xx_not_retried(self):
        judge = JevIntentJudge(api_key="k", retries=3)
        attempts = {"n": 0}

        def fake_post(payload):
            attempts["n"] += 1
            raise self._http_error(400)

        with mock.patch.object(judge, "_post", side_effect=fake_post), \
                mock.patch("services.jev_judge.time.sleep"):
            judgment, raw = judge.evaluate("帮我改一下")
        self.assertEqual(attempts["n"], 1)
        self.assertIsNone(raw)
        self.assertTrue(judgment.fallback)
        self.assertIn("jev_fallback:http_400", judgment.evidence)

    def test_retry_exhausted_falls_back_to_rule(self):
        judge = JevIntentJudge(api_key="k", retries=2)
        attempts = {"n": 0}

        def fake_post(payload):
            attempts["n"] += 1
            raise self._http_error(503)

        with mock.patch.object(judge, "_post", side_effect=fake_post), \
                mock.patch("services.jev_judge.time.sleep"):
            judgment, raw = judge.evaluate("帮我改一下")
        self.assertEqual(attempts["n"], 3)  # 1 次 + 重试 2 次
        self.assertIsNone(raw)
        self.assertTrue(judgment.fallback)
        self.assertEqual(judgment.kind, "modify")  # 规则版判定
        self.assertIn("jev_fallback:http_503", judgment.evidence)


class FallbackTests(unittest.TestCase):
    def test_no_api_key_never_calls_network(self):
        judge = JevIntentJudge(api_key="")
        with mock.patch.object(judge, "_post", side_effect=AssertionError("不应发起请求")):
            self.assertIsNone(judge.judge_raw("帮我改一下"))
            judgment = judge.judge("帮我改一下")
        self.assertTrue(judgment.fallback)
        self.assertIn("jev_fallback:no_api_key", judgment.evidence)

    def test_malformed_answers_fall_back_but_keep_raw(self):
        judge = JevIntentJudge(api_key="k")
        with mock.patch.object(judge, "_post", return_value={"answers": {"context": {}}}):
            judgment, raw = judge.evaluate("给我点提示")
        self.assertIsNotNone(raw)
        self.assertTrue(judgment.fallback)
        self.assertTrue(any(e.startswith("jev_fallback:parse_") for e in judgment.evidence))


if __name__ == "__main__":
    unittest.main()
