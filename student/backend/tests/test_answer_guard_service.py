# -*- coding: utf-8 -*-
"""防泄题护栏 + 教学动作策略 + 诊断闭环 的单元测试。

护栏三条线：R1 参考答案重叠拦截（非流式/流式）、R2 长代码记录、
无参考答案时安全退化；策略侧覆盖规则分类与诊断→提示闭环。
"""
import unittest

from services.answer_guard_service import (
    GuardedStreamFilter,
    apply_guard,
    evaluate,
    load_reference_solution,
)
from services.teaching_policy_service import classify_by_rule, diagnosis_focus

REF = load_reference_solution("1-1")

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


if __name__ == "__main__":
    unittest.main()
