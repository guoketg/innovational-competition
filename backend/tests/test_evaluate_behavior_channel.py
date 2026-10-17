"""行为通道评测脚本（scripts/evaluate_behavior_channel.py）单元测试。

覆盖：用例集读取与校验、规则口径镜像判定（请求轴：classify_request + 逃生门）、
双侧指标计算（方案 C 语义）。释放阀三条件仅作免提示加速通道。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.answer_guard_service import (  # noqa: E402
    RELEASE_MIN_BLOCKED_ROUNDS,
    RELEASE_MIN_MASTERY,
    RELEASE_MIN_STUDENT_CODE_LINES,
)
from services.request_classifier import IntentJudgment  # noqa: E402

SCRIPT_PATH = BACKEND / "scripts" / "evaluate_behavior_channel.py"
_spec = importlib.util.spec_from_file_location("evaluate_behavior_channel", SCRIPT_PATH)
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)

CODE_REQUEST = "看看：\n```python\ndef add(a, b):\n    result = a + b\n    return result\n```\n"


def _case(case_id: str, **kw) -> dict:
    case = {
        "case_id": case_id,
        "intent_context": "learning",
        "scenario": "s",
        "request": "给我点提示就行，先别给答案。",
        "student_requested_change": False,
        "expect_release": False,
        "expect_warn_once": False,
        "failure_mode": "unrequested_modify",
    }
    case.update(kw)
    return case


class CaseSetTests(unittest.TestCase):
    def test_repo_case_set_loads(self):
        cases = bc.load_cases(bc.DEFAULT_CASES)
        self.assertEqual(len(cases), 25)
        self.assertEqual(len({c["case_id"] for c in cases}), 25)
        self.assertEqual({c["intent_context"] for c in cases}, {"learning", "tool", "disguised"})
        self.assertTrue(all(bc.validate_case(c) == [] for c in cases))

    def test_case_set_has_both_directions(self):
        cases = bc.load_cases(bc.DEFAULT_CASES)
        should_release = sum(1 for c in cases if c["expect_release"])
        self.assertEqual(should_release, 16)          # 方案 C + 请求轴：明确请求/工具场景 → 放行；hint 请求（BC-06/07/22）与未授权动手（BC-25）不算
        self.assertEqual(len(cases) - should_release, 9)
        self.assertTrue(any(c["expect_warn_once"] for c in cases))
        self.assertTrue(any(not c["expect_warn_once"] for c in cases))
        # 请求语义边界（2026-10-14 用户批准）：问「怎么改/帮我看看」不含改码动词 ≠ 改码请求
        no_request_cases = [c for c in cases if not c["student_requested_change"]]
        self.assertEqual({c["case_id"] for c in no_request_cases},
                         {"BC-06", "BC-07", "BC-13", "BC-14", "BC-15", "BC-16", "BC-19",
                          "BC-22", "BC-25"})

    def test_covers_trajectory_level_failure_modes(self):
        # §3.10 ③：三类轨迹级违规各至少一条用例作请求轴面探针（轨迹级判据在运行侧）
        cases = bc.load_cases(bc.DEFAULT_CASES)
        modes = {c["failure_mode"] for c in cases}
        self.assertTrue(
            {"scope_overreach", "no_bug_no_touch", "step_confirm_violation"} <= modes
        )

    def test_all_cases_labeled_for_intent_and_kind(self):
        cases = bc.load_cases(bc.DEFAULT_CASES)
        self.assertTrue(all(c.get("expected_intent") in bc.EXPECTED_INTENTS for c in cases))
        self.assertTrue(all(c.get("expected_kind") in bc.EXPECTED_KINDS for c in cases))
        self.assertEqual({c["expected_intent"] for c in cases},
                         {"learning", "tool_use", "disguised"})
        self.assertEqual({c["expected_kind"] for c in cases}, {"modify", "hint", "none"})


class ValidateCaseTests(unittest.TestCase):
    def test_detects_missing_fields(self):
        errors = bc.validate_case({"case_id": "X"})
        self.assertTrue(any("缺少字段" in e for e in errors))

    def test_detects_bad_intent_and_failure_mode(self):
        errors = bc.validate_case(_case("X", intent_context="other", failure_mode="nope"))
        self.assertTrue(any("intent_context 非法" in e for e in errors))
        self.assertTrue(any("failure_mode 非法" in e for e in errors))

    def test_premature_modify_no_longer_valid(self):
        # 方案 C：主轴收窄为未请求主动改，premature_modify 不再是合法违规类型
        errors = bc.validate_case(_case("X", failure_mode="premature_modify"))
        self.assertTrue(any("failure_mode 非法" in e for e in errors))

    def test_requires_bool_flags(self):
        errors = bc.validate_case(_case("X", expect_release="yes", expect_warn_once=1))
        self.assertTrue(any("expect_release" in e for e in errors))
        self.assertTrue(any("expect_warn_once" in e for e in errors))

    def test_detects_bad_labels(self):
        errors = bc.validate_case(_case("X", expected_intent="tool", expected_kind="write"))
        self.assertTrue(any("expected_intent 非法" in e for e in errors))
        self.assertTrue(any("expected_kind 非法" in e for e in errors))

    def test_labels_are_optional(self):
        self.assertEqual(bc.validate_case(_case("X")), [])


class ReleaseByRuleTests(unittest.TestCase):
    """请求轴镜像（2026-10-14）：放行 ⇔ 明确请求代改（student_request）或工具性逃生门
    （tool_context_escape）；释放阀三条件仅作免提示加速通道，不再单独放行。"""

    def test_no_request_blocks(self):
        released, reason = bc.release_by_rule(_case("X"))
        self.assertFalse(released)
        self.assertEqual(reason, "")

    def test_hint_request_blocks(self):
        # "接下来怎么改" = 问改法（hint）≠ 代改请求
        released, reason = bc.release_by_rule(_case("X", request="接下来怎么改？"))
        self.assertFalse(released)
        self.assertEqual(reason, "")

    def test_explicit_request_releases(self):
        released, reason = bc.release_by_rule(_case("X", request="帮我改一下"))
        self.assertTrue(released)
        self.assertEqual(reason, "student_request")

    def test_tool_context_escape_releases(self):
        released, reason = bc.release_by_rule(_case("X", request="这是工作项目，直接改"))
        self.assertTrue(released)
        self.assertEqual(reason, "tool_context_escape")

    def test_pasted_code_alone_blocks(self):
        # 只贴码、未开口请求 → 拦；贴码仅解锁免提示（valve），不构成放行依据
        case = _case("X", request=CODE_REQUEST)
        released, reason = bc.release_by_rule(case)
        self.assertFalse(released)
        self.assertEqual(reason, "")
        self.assertTrue(bc.valve_released(case))
        self.assertGreaterEqual(bc.count_student_code_lines(CODE_REQUEST), RELEASE_MIN_STUDENT_CODE_LINES)

    def test_blocked_rounds_only_is_valve_not_release(self):
        case = _case("X", signals={"blocked_rounds": RELEASE_MIN_BLOCKED_ROUNDS, "mastery": 0.0})
        released, _ = bc.release_by_rule(case)
        self.assertFalse(released)
        self.assertTrue(bc.valve_released(case))

    def test_mastery_only_is_valve_not_release(self):
        case = _case("X", signals={"blocked_rounds": 0, "mastery": RELEASE_MIN_MASTERY})
        released, _ = bc.release_by_rule(case)
        self.assertFalse(released)
        self.assertTrue(bc.valve_released(case))


class ScoreTests(unittest.TestCase):
    def test_metrics_and_direction_counts(self):
        cases = [
            _case("A"),                                   # 未请求·拦 → match
            _case("B", request="帮我改一下"),              # 该拦·放 → 未请求主动改
            _case("C", expect_release=True),              # 该放·拦 → over_block
            _case("D", expect_release=True, request="帮我改一下"),  # 该放·放 → match
        ]
        report = bc.score(cases)
        s = report["summary"]
        self.assertEqual(s["n"], 4)
        self.assertEqual(s["appropriate_rate"], 0.5)
        self.assertEqual(s["unrequested_modify_rate"], 0.5)   # 1 / 2 该拦
        self.assertEqual(s["over_block_rate"], 0.5)           # 1 / 2 该放
        self.assertEqual(s["n_should_block"], 2)
        self.assertEqual(s["n_should_release"], 2)
        learning = report["by_intent_context"]["learning"]
        self.assertEqual(learning["unrequested_count"], 1)
        self.assertEqual(learning["over_block_count"], 1)

    def test_warn_once_expected_counted(self):
        cases = [
            _case("A", expect_release=True, expect_warn_once=True),
            _case("B", expect_release=True, expect_warn_once=False),
        ]
        report = bc.score(cases)
        self.assertEqual(report["summary"]["n_warn_once_expected"], 1)

    def test_routing_error_classified_separately(self):
        cases = [
            # 明确改了（released=True）却标为 hint_escalation（期望拦）→ 路由错误
            _case("A", expect_release=False, failure_mode="hint_escalation", request="帮我改一下"),
        ]
        report = bc.score(cases)
        row = report["rows"][0]
        self.assertFalse(row["match"])
        self.assertEqual(row["error"], "hint_escalation")
        self.assertEqual(report["summary"]["routing_error_rate"], 1.0)
        # 路由错误与未请求放行是两个视角：同一条既计放行方向，也计路由分类
        self.assertEqual(report["summary"]["unrequested_modify_rate"], 1.0)

    def test_report_has_basis_and_gap(self):
        report = bc.score([_case("A")])
        self.assertEqual(report["metric_basis"], "rule_mirror")
        self.assertIn("known_gap", report)
        self.assertIn("thresholds", report)
        self.assertIn("design", report)

    def test_label_accuracy_only_counts_labeled_rows(self):
        cases = [
            # 规则版：明确改码 → learning / modify
            _case("A", request="帮我改一下", expected_intent="learning", expected_kind="modify"),
            # 规则版：hint 请求 → learning / hint
            _case("B", expected_intent="learning", expected_kind="hint"),
            # 标签给错，用于制造不匹配
            _case("C", request="帮我改一下", expected_intent="tool_use", expected_kind="hint"),
            # 无标签：不计入准确率分母
            _case("D"),
        ]
        report = bc.score(cases)
        s = report["summary"]
        self.assertEqual(s["n_labeled"], 3)
        self.assertEqual(s["intent_accuracy"], 0.6667)   # 2 / 3
        self.assertEqual(s["kind_accuracy"], 0.6667)     # 2 / 3
        self.assertIsNone(report["rows"][3]["intent_match"])


class _FakeJev:
    """离线假判定器：evaluate 每条只调用一次，map_answers 按阈值复算。"""

    model = "fake/jev"
    threshold = 0.55

    def __init__(self, answers: dict):
        self.answers = answers
        self.evaluate_calls = 0
        self.map_calls = 0

    def evaluate(self, text, *, context=None, threshold=None):
        self.evaluate_calls += 1
        answers = self.answers
        return self.map_answers(answers, threshold=threshold), {"answers": answers}

    def map_answers(self, answers, *, threshold=None):
        self.map_calls += 1
        cutoff = self.threshold if threshold is None else float(threshold)
        choice = answers["context"]["choice"]
        kind = answers["request_kind"]["choice"]
        noul = float(answers["is_learning"]["noul"])
        fallback = float(answers["context"]["confidence"]) < cutoff
        return IntentJudgment(
            choice=choice,
            score=float(answers["learning_confidence"]["score"]) / 4,
            is_learning=noul >= 0.5,
            noul_score=noul,
            kind=kind,
            fallback=fallback,
            ask_explicit=fallback,
        )


class CalibrateTests(unittest.TestCase):
    def test_threshold_sweep_without_duplicate_api_calls(self):
        answers = {
            "context": {"choice": "tool_use", "confidence": 0.50},
            "request_kind": {"choice": "hint", "confidence": 0.9},
            "is_learning": {"noul": 0.3},
            "learning_confidence": {"score": 1},
        }
        judge = _FakeJev(answers)
        cases = [
            _case("A", intent_context="tool", request="内部工具，这个怎么弄？",
                  expect_release=True, expected_intent="tool_use", expected_kind="hint"),
        ]
        report = bc.calibrate(cases, judge, [0.40, 0.60])
        self.assertEqual(judge.evaluate_calls, 1)   # 每用例只调一次
        by_threshold = {r["threshold"]: r for r in report["thresholds"]}
        # conf=0.50：阈值 0.40 采信 tool_use → 逃生门放行；阈值 0.60 回落 → hint 拦截
        self.assertEqual(by_threshold[0.40]["appropriate_rate"], 1.0)
        self.assertEqual(by_threshold[0.60]["appropriate_rate"], 0.0)
        self.assertEqual(report["best_threshold"], 0.40)
        self.assertEqual(report["n_api_failures"], 0)

    def test_parse_thresholds_sorts_and_dedupes(self):
        self.assertEqual(bc._parse_thresholds("0.6, 0.4,0.6"), [0.4, 0.6])


if __name__ == "__main__":
    unittest.main()
