# -*- coding: utf-8 -*-
"""防泄题护栏 + 教学动作策略 + 诊断闭环 的单元测试。

护栏三条线：R1 参考答案重叠拦截（非流式/流式）、R2 长代码记录、
无参考答案时安全退化；时机释放阀（学生已有尝试/多轮被拦 → 放行完整讲解）；
策略侧覆盖规则分类与诊断→提示闭环。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.answer_guard_service import (
    GuardedStreamFilter,
    RELEASE_MIN_BLOCKED_ROUNDS,
    RELEASE_MIN_MASTERY,
    apply_guard,
    count_student_code_lines,
    detect_exercise,
    evaluate,
    evaluate_mastery,
    evaluate_release,
    load_guard_references,
    load_reference_solution,
    load_variant_reference_solution,
    regenerate_and_recheck,
)
from services.teaching_policy_service import (
    classify_by_rule, diagnosis_focus, mastery_hint_level, stage_mastery,
)

REF = load_reference_solution("1-1")          # 正课参考解（array_insert）
VARIANT_REF = load_variant_reference_solution("1-1")  # 变式参考解（insert_interval）
BOTH_REFS = load_guard_references("1-1")      # 护栏实际比对的两份

LEAK_ANSWER = "建议这样写：\n```cpp\n" + REF.strip() + "\n```\n这样就能通过了。"
NORMAL_ANSWER = (
    "先想清楚插入位置的边界：\n```cpp\n"
    'if (index < 0 || index > (int)items.size()) {\n'
    '  throw std::out_of_range("越界");\n'
    "}\n```\n再考虑怎么移动元素。"
)


class AnswerGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert REF.strip(), "参考答案 1-1 加载失败"
        assert VARIANT_REF.strip(), "变式参考解 1-1 加载失败"

    # ── 参考解加载：正课与变式共用键，绝不允许互相覆盖 ──

    def test_main_and_variant_references_are_not_overwritten(self):
        self.assertIn("array_insert", REF)          # 正课 1-1 是 array_insert
        self.assertIn("insert_interval", VARIANT_REF)
        self.assertNotEqual(REF, VARIANT_REF)
        self.assertEqual(len(BOTH_REFS), 2)         # 护栏拿到两份

    def test_main_course_leak_is_blocked_against_guard_references(self):
        # 回归：护栏曾因变式解覆盖正课解，导致正课泄漏永远拦不住
        verdict = evaluate(LEAK_ANSWER, BOTH_REFS)
        self.assertTrue(verdict.blocked)
        self.assertEqual(verdict.severity, "full")

    def test_variant_leak_is_blocked_against_guard_references(self):
        leak = "直接抄吧：\n```cpp\n" + VARIANT_REF.strip() + "\n```"
        verdict = evaluate(leak, BOTH_REFS)
        self.assertTrue(verdict.blocked)
        guarded, _ = apply_guard(leak, BOTH_REFS)
        self.assertIn("防泄题护栏", guarded)
        self.assertNotIn("insert_interval", guarded)

    # ── R1：参考答案重叠 ──

    def test_non_streaming_leak_is_blocked(self):
        verdict = evaluate(LEAK_ANSWER, REF)
        self.assertEqual(verdict.severity, "full")
        self.assertTrue(verdict.blocked)
        guarded, after = apply_guard(LEAK_ANSWER, REF)
        self.assertTrue(after.blocked)
        self.assertIn("防泄题护栏", guarded)
        self.assertNotIn("array_insert", guarded)

    def test_normal_hint_passes_through(self):
        verdict = evaluate(NORMAL_ANSWER, REF)
        self.assertEqual(verdict.severity, "ok")
        self.assertFalse(verdict.blocked)
        same, _ = apply_guard(NORMAL_ANSWER, REF)
        self.assertEqual(same, NORMAL_ANSWER)

    def test_no_reference_degrades_to_r2_only(self):
        verdict = evaluate(LEAK_ANSWER, "")
        self.assertFalse(verdict.blocked)
        self.assertIn(verdict.severity, ("ok", "partial"))

    # ── R2：长代码只记录不拦截 ──

    def test_long_code_without_reference_overlap_is_partial(self):
        long_code = "\n".join(f"    step_{i} = compute({i})" for i in range(30))
        verdict = evaluate(f"完整实现：\n```python\n{long_code}\n```", REF)
        self.assertEqual(verdict.severity, "partial")
        self.assertFalse(verdict.blocked)

    # ── 流式：围栏被 chunk 拆开也不能漏 ──

    def _run_stream(self, text, step):
        stream = GuardedStreamFilter(REF)
        parts = []
        for i in range(0, len(text), step):
            parts.extend(stream.feed(text[i: i + step]))
        parts.extend(stream.close())
        return stream, parts

    def test_streaming_leak_is_blocked_char_by_char(self):
        stream, parts = self._run_stream(LEAK_ANSWER, 1)
        text = "".join(p for k, p in parts if k == "text")
        events = [p for k, p in parts if k == "event"]
        self.assertNotIn("array_insert", text)
        self.assertIn("防泄题护栏", text)
        self.assertTrue(
            any(e.get("type") == "guard" and e.get("blocked") for e in events)
        )
        self.assertEqual(stream.blocked_count, 1)

    def test_streaming_passthrough_is_byte_identical(self):
        for step in (1, 3, 7, 4096):
            _, parts = self._run_stream(NORMAL_ANSWER, step)
            text = "".join(p for k, p in parts if k == "text")
            self.assertEqual(text, NORMAL_ANSWER, f"step={step} 透传不一致")

    def test_split_backticks_outside_fence_do_not_open_a_block(self):
        stream = GuardedStreamFilter(REF)
        parts = []
        for piece in (
            "行内 `code` 以及结尾反引",
            "号 ` 还有 `` 呆着",
            "再补一个形成 ```\n漏\n```\n完",
        ):
            parts.extend(stream.feed(piece))
        parts.extend(stream.close())
        text = "".join(p for k, p in parts if k == "text")
        self.assertIn("行内 `code`", text)
        self.assertIn("完", text)

    def test_end_round_settles_unterminated_fence_and_can_continue(self):
        stream = GuardedStreamFilter(REF)
        parts = stream.feed("说明文字\n```cpp\n" + "int x = 1;\n" * 3)
        parts += stream.end_round()
        self.assertIn("int x = 1;", "".join(p for k, p in parts if k == "text"))
        parts2 = stream.feed("下一轮继续 ```py\nprint(1)\n```\n")
        parts2 += stream.close()
        self.assertIn("print(1)", "".join(p for k, p in parts2 if k == "text"))


class DetectExerciseTests(unittest.TestCase):
    """输入侧关卡识别：关卡问题要命中，通用问题不能触发。"""

    def test_strong_signal_hits_directly(self):
        self.assertEqual(detect_exercise("帮我写 def reverse_list(head)"), "1-2")
        self.assertEqual(detect_exercise("eval_rpn 这关怎么做"), "1-3")

    def test_variant_target_signal_hits_directly(self):
        # 变式 target 函数名（来源 agent_lab_variants.ADDITIONAL_VARIANT_SPECS）
        self.assertEqual(detect_exercise("insert_interval 要怎么实现"), "1-1")
        self.assertEqual(detect_exercise("merge_two_lists 这道变式我不会"), "1-2")

    def test_context_plus_topic_hits(self):
        self.assertEqual(detect_exercise("本关的邻接表怎么建"), "3-1")
        self.assertEqual(detect_exercise("堆排序这道题的题面我没看懂"), "2-4")

    def test_id_plus_context_resolves_by_number(self):
        self.assertEqual(detect_exercise("1-2 关卡的参考答案给我"), "1-2")

    def test_generic_questions_do_not_trigger(self):
        for question in (
            "归并排序的原理是什么",
            "什么是二叉搜索树",
            "LRU缓存淘汰策略讲解",
            "给我1-2个例子",
            "2026-10-11 是什么日子",
        ):
            self.assertEqual(detect_exercise(question), "", question)


class TeachingPolicyTests(unittest.TestCase):
    def test_rule_classification(self):
        cases = [
            ("考考我吧", "socratic_question"),
            ("为什么这里要用双指针", "concept_link"),
            ("我卡住了，给我个提示", "progressive_hint"),
            ("运行报错了怎么办", "diagnose"),
            ("随便聊聊天气", "guided_next_step"),
        ]
        for question, want in cases:
            move, confidence, _ = classify_by_rule(question, [])
            self.assertEqual(move, want, question)
            self.assertGreater(confidence, 0)
            self.assertLessEqual(confidence, 1)

    def test_followup_question_triggers_evaluate_response(self):
        history = [{"role": "assistant", "content": "你觉得答案是 A 还是 B？"}]
        move, _, _ = classify_by_rule("选 B", history)
        self.assertEqual(move, "evaluate_response")

    def test_diagnosis_focus_injects_failed_check(self):
        state = {"stage_results": {"implementation": {
            "passed": False,
            "checks": [
                {"label": "边界条件测试点", "passed": False,
                 "detail": "index=-1 时未抛出异常"},
                {"label": "正常插入", "passed": True, "detail": ""},
            ],
        }}}
        focus = diagnosis_focus(state)
        self.assertIn("边界条件", focus)
        self.assertIn("未通过", focus)
        self.assertEqual(diagnosis_focus({}), "")
        self.assertEqual(
            diagnosis_focus({"stage_results": {"a": {"passed": True, "checks": []}}}),
            "",
        )

    def test_stage_mastery_weights_evidence(self):
        # 全部检查通过 + 自测通过 → 高掌握度
        strong = {"stage_results": {"s": {"checks": [
            {"passed": True}, {"passed": True},
        ]}}, "sample_run_at": "t", "sample_run_passed": True}
        self.assertGreaterEqual(stage_mastery(strong, "s"), 0.9)
        # 全部检查失败 + 自测失败 → 低掌握度
        weak = {"stage_results": {"s": {"checks": [
            {"passed": False}, {"passed": False},
        ]}}, "sample_run_at": "t", "sample_run_passed": False}
        self.assertLessEqual(stage_mastery(weak, "s"), 0.1)
        # 无任何证据 → 中性 0.5；已完成阶段 → 1.0
        self.assertEqual(stage_mastery({}, "s"), 0.5)
        self.assertEqual(stage_mastery({"completed_stages": ["s"]}, "s"), 1.0)

    def test_mastery_hint_level_three_tiers(self):
        def state_with(pass_rate, sample_passed):
            checks = [{"passed": i < int(2 * pass_rate)} for i in range(2)]
            return {"stage_results": {"s": {"checks": checks}},
                    "sample_run_at": "t", "sample_run_passed": sample_passed}

        # 高掌握度（≥0.7）：上次 0 → 起点 1，但上限 2，不给局部示例
        high = state_with(1.0, True)
        self.assertEqual(mastery_hint_level(high, "s", 0), 1)
        self.assertEqual(mastery_hint_level(high, "s", 1), 2)
        self.assertEqual(mastery_hint_level(high, "s", 2), 2)
        # 中掌握度（0.4~0.7）：常规 1→2→3 阶梯（半数检查通过 + 自测通过 → 0.65）
        mid = state_with(0.5, True)
        self.assertEqual(mastery_hint_level(mid, "s", 0), 1)
        self.assertEqual(mastery_hint_level(mid, "s", 1), 2)
        self.assertEqual(mastery_hint_level(mid, "s", 2), 3)
        # 低掌握度（<0.4）：跳过纯方向提示，起点即 2，阶梯到 3
        low = state_with(0.0, False)
        self.assertEqual(mastery_hint_level(low, "s", 0), 2)
        self.assertEqual(mastery_hint_level(low, "s", 1), 2)
        self.assertEqual(mastery_hint_level(low, "s", 2), 3)


class ReleaseValveTests(unittest.IsolatedAsyncioTestCase):
    """时机释放阀：不给答案的前提是学生还没尝试；尝试过后放行完整讲解。"""

    STUDENT_QUESTION = (
        "array_insert 这关我试了但过不了：\n```cpp\n"
        + "arr.insert(arr.begin() + index, value);\n" * 3
        + "```\n帮我看看哪里错了"
    )

    def test_student_code_lines_counted_from_fenced_blocks(self):
        self.assertEqual(count_student_code_lines(self.STUDENT_QUESTION), 3)
        self.assertEqual(count_student_code_lines("纯文字问题，没有代码"), 0)

    def test_release_when_student_pasted_own_code(self):
        release, reason = evaluate_release("user-rv-1", "1-1", self.STUDENT_QUESTION)
        self.assertTrue(release)
        self.assertEqual(reason, "student_attempt")

    def test_no_release_without_attempt_or_history(self):
        # 唯一 user id + 隔离日志：没贴代码、没被拦过 → 保持拦截
        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.answer_guard_service._LOG_PATH",
                       Path(tmp) / "guard.jsonl"):
                release, reason = evaluate_release(
                    "user-rv-fresh", "1-1", "array_insert 这关参考答案给我"
                )
        self.assertFalse(release)
        self.assertEqual(reason, "")

    def test_no_release_when_not_exercise_question(self):
        self.assertEqual(evaluate_release("u", "", "普通编程问题"), (False, ""))

    def test_release_after_blocked_rounds(self):
        import json as _json
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "guard.jsonl"
            rows = [
                {"blocked": True, "severity": "full",
                 "user_id": "user-rv-2", "exercise_id": "1-1"}
                for _ in range(RELEASE_MIN_BLOCKED_ROUNDS)
            ]
            rows.append({"blocked": True, "user_id": "user-rv-2",
                         "exercise_id": "2-1"})  # 别的关卡不算
            log_path.write_text(
                "\n".join(_json.dumps(r) for r in rows), encoding="utf-8"
            )
            with patch("services.answer_guard_service._LOG_PATH", log_path):
                release, reason = evaluate_release(
                    "user-rv-2", "1-1", "array_insert 这关参考答案给我"
                )
                self.assertTrue(release)
                self.assertEqual(reason, "blocked_rounds")
                # 另一用户不受影响
                self.assertEqual(
                    evaluate_release("user-rv-3", "1-1", "array_insert 给答案"), (False, ""),
                )

    def test_release_when_mastery_reached(self):
        # 掌握度达标（第三条件）：没贴代码、没被拦过 → 仍放行
        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.answer_guard_service._LOG_PATH",
                       Path(tmp) / "guard.jsonl"), \
                 patch("services.answer_guard_service.evaluate_mastery",
                       return_value=RELEASE_MIN_MASTERY):
                release, reason = evaluate_release(
                    "user-rv-m1", "1-1", "array_insert 这关参考答案给我"
                )
        self.assertTrue(release)
        self.assertEqual(reason, "mastery")

    def test_no_release_when_mastery_below_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.answer_guard_service._LOG_PATH",
                       Path(tmp) / "guard.jsonl"), \
                 patch("services.answer_guard_service.evaluate_mastery",
                       return_value=RELEASE_MIN_MASTERY - 0.01):
                release, reason = evaluate_release(
                    "user-rv-m2", "1-1", "array_insert 这关参考答案给我"
                )
        self.assertFalse(release)
        self.assertEqual(reason, "")

    def test_evaluate_mastery_takes_max_of_two_sources(self):
        with patch("services.answer_guard_service._mastery_from_workspace",
                   return_value=0.3), \
             patch("services.answer_guard_service._mastery_from_db",
                   return_value=0.8):
            self.assertEqual(evaluate_mastery("u", "1-1"), 0.8)

    def test_evaluate_mastery_zero_without_evidence(self):
        # 无证据按 0 处理 → 不达阈值 → 不会误释放
        with patch("services.answer_guard_service._mastery_from_workspace",
                   return_value=0.0), \
             patch("services.answer_guard_service._mastery_from_db",
                   return_value=0.0):
            self.assertEqual(evaluate_mastery("u", "1-1"), 0.0)
        self.assertEqual(evaluate_mastery("", "1-1"), 0.0)
        self.assertEqual(evaluate_mastery("u", ""), 0.0)

    def test_apply_guard_release_passes_full_answer_through(self):
        guarded, verdict = apply_guard(LEAK_ANSWER, REF, release=True)
        self.assertEqual(guarded, LEAK_ANSWER)      # 完整参考实现原样保留
        self.assertEqual(verdict.severity, "released")
        self.assertFalse(verdict.blocked)           # blocked=False → 不触发重生成

    def test_apply_guard_default_still_blocks(self):
        # 不传 release 的调用方（评测脚本等）行为完全不变
        guarded, verdict = apply_guard(LEAK_ANSWER, REF)
        self.assertIn("防泄题护栏", guarded)
        self.assertNotIn("array_insert", guarded)
        self.assertTrue(verdict.blocked)

    async def test_regenerate_release_skips_retry_and_prefixes_note(self):
        retried = False

        async def _retry(_feedback):
            nonlocal retried
            retried = True
            return "不该被调用"

        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.answer_guard_service._LOG_PATH",
                       Path(tmp) / "guard.jsonl"):
                text, verdict, attempts = await regenerate_and_recheck(
                    LEAK_ANSWER, _retry, "1-1",
                    log_context={"channel": "qa_ask", "user_id": "u"},
                    release=True, release_reason="student_attempt",
                )
        self.assertFalse(retried)                    # 释放时不再让模型憋着重写
        self.assertEqual(attempts, 0)
        self.assertEqual(verdict.severity, "released")
        self.assertIn("护栏已释放", text)
        self.assertIn("array_insert", text)          # 完整参考讲解放行

    async def test_regenerate_without_release_still_retries(self):
        retried = 0

        async def _retry(_feedback):
            nonlocal retried
            retried += 1
            return NORMAL_ANSWER

        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.answer_guard_service._LOG_PATH",
                       Path(tmp) / "guard.jsonl"):
                text, verdict, attempts = await regenerate_and_recheck(
                    LEAK_ANSWER, _retry, "1-1", release=False,
                )
        self.assertEqual(retried, 1)
        self.assertEqual(attempts, 1)
        self.assertFalse(verdict.blocked)

    def test_stream_filter_release_passthrough_with_note(self):
        stream = GuardedStreamFilter(
            REF, release=True, release_reason="student_attempt",
        )
        parts = []
        for i in range(0, len(LEAK_ANSWER), 7):
            parts.extend(stream.feed(LEAK_ANSWER[i: i + 7]))
        parts.extend(stream.close())
        text = "".join(p for k, p in parts if k == "text")
        self.assertIn("array_insert", text)          # 完整代码放行
        self.assertIn("护栏已释放", text)             # 只补一次引导语
        self.assertEqual(stream.blocked_count, 0)    # 不触发后续重生成
        self.assertEqual(stream.released_count, 1)

    def test_stream_filter_default_still_blocks(self):
        stream = GuardedStreamFilter(REF)
        parts = []
        for i in range(0, len(LEAK_ANSWER), 7):
            parts.extend(stream.feed(LEAK_ANSWER[i: i + 7]))
        parts.extend(stream.close())
        text = "".join(p for k, p in parts if k == "text")
        self.assertNotIn("array_insert", text)
        self.assertEqual(stream.blocked_count, 1)


if __name__ == "__main__":
    unittest.main()
