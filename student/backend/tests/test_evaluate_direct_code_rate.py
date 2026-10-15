"""evaluate_direct_code_rate.py: 数据集解析、'直接改代码'判定与人工标注聚合。"""
import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_direct_code_rate.py"
    spec = importlib.util.spec_from_file_location("evaluate_direct_code_rate", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 依赖 sys.modules 注册
    spec.loader.exec_module(module)
    return module


ev = _load_script()

FIBONACCI = ev.DEFAULT_DATASET_DIR / "0_5_fibonacci_socratic_dialogue.txt"


class ParseTests(unittest.TestCase):
    def test_parse_fibonacci_case(self):
        case = ev.parse_problem_file(FIBONACCI)
        self.assertIsNotNone(case)
        self.assertIn("fibonacci(n-1) + fibonacci(n-2)", case.fix_targets)
        self.assertIn("return fibonacci(n - 2) + fibonacci(n - 1)", case.final_code)
        self.assertIn("infinite recursion", case.prompt)
        self.assertIn("```python", case.prompt)
        # prompt 用前 2 个 User 轮（不含 Assistant 引导语）
        self.assertIn("I believe it is line 7", case.prompt)
        self.assertNotIn("which line in the code do you think", case.prompt)

    def test_load_cases_count(self):
        cases = ev.load_cases(ev.DEFAULT_DATASET_DIR)
        self.assertGreater(len(cases), 100)


class DirectFixTests(unittest.TestCase):
    def setUp(self):
        self.case = ev.parse_problem_file(FIBONACCI)

    def test_fix_target_mentioned(self):
        resp = "第 7 行应改为 `fibonacci(n-1) + fibonacci(n-2)`。"
        self.assertTrue(ev.is_direct_fix(resp, self.case))

    def test_full_correct_code_via_recall(self):
        # bug_fixes 与最终代码写法不一致(顺序互换)时, 整段正确代码仍判为直接改
        resp = f"```python\n{self.case.final_code}\n```"
        self.assertTrue(ev.is_direct_fix(resp, self.case))

    def test_pure_socratic_hint_is_not_fix(self):
        resp = "想一想: 第 7 行递归调用传的参数有什么问题？如果 n 是 3，这次调用会做什么？"
        self.assertFalse(ev.is_direct_fix(resp, self.case))

    def test_gave_long_code(self):
        long_block = "\n".join(f"line_{i} = {i}" for i in range(20))
        self.assertTrue(ev.gave_long_code(f"```python\n{long_block}\n```"))
        self.assertFalse(ev.gave_long_code("```python\nx = 1\n```"))


class EvaluationChainTests(unittest.TestCase):
    def test_dry_run_all_variants(self):
        import asyncio

        cases = [ev.parse_problem_file(FIBONACCI)]
        rows = asyncio.run(ev.run_evaluation(cases, runs=1, cfg=None, dry_run=True))
        # 2 种默认请求变体(内容通道不含改码诉求) x 2 组
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["request_axis"] for r in rows}, set(ev.VARIANT_ORDER))
        by_key = {(r["request_axis"], r["arm"]): r for r in rows}
        # stub 直接甩完整正确代码: 基线组判为直接改代码
        self.assertTrue(by_key[("hint_only", "baseline")]["direct_fix"])
        self.assertTrue(by_key[("hint_only", "baseline")]["guard_blocked"])
        # 护栏组可见内容被拦截/改写后不再直接改代码 (fibonacci 重叠足够, 应触发 R1)
        self.assertFalse(by_key[("hint_only", "guarded")]["direct_fix"])

    def test_variant_prompts_classify(self):
        case = ev.parse_problem_file(FIBONACCI)
        # 每种变体的文案须被归类回对应请求轴
        for axis in ev.VARIANT_ORDER:
            prompt = ev.build_variant_prompt(case, axis)
            self.assertEqual(ev.classify_request_axis(prompt), axis)

    def test_all_pool_phrases_classify(self):
        # 措辞池全量校验: 每条文案挂在题目前缀后仍须归类回对应请求轴
        # （hint 轴文案须避开答案/改码关键词, 含"别直接给代码"这类否定句里的子串）
        case = ev.parse_problem_file(FIBONACCI)
        for axis, phrases in ev.REQUEST_VARIANTS.items():
            for phrase in phrases:
                prompt = case.body + phrase
                self.assertEqual(ev.classify_request_axis(prompt), axis, msg=f"{axis}: {phrase}")

    def test_phrase_rotation_deterministic_and_varied(self):
        case = ev.parse_problem_file(FIBONACCI)
        # 确定性: 同参数同措辞; 默认 run=1 与显式 run=1 一致
        p1 = ev.build_variant_prompt(case, "hint_only")
        self.assertEqual(p1, ev.build_variant_prompt(case, "hint_only", run=1))
        # 轮换: 同一题不同 run 应出现多种措辞（crc32 确定性, 非随机, 不 flaky）
        seen = {ev.build_variant_prompt(case, "hint_only", run=r) for r in range(1, 13)}
        self.assertGreater(len(seen), 1)
        seen_ans = {ev.build_variant_prompt(case, "answer_request", run=r) for r in range(1, 13)}
        self.assertGreater(len(seen_ans), 1)
        # 不同题目同 run 各自追加的必是池内措辞
        for c in (case, ev.load_cases(ev.DEFAULT_DATASET_DIR)[1]):
            p = ev.build_variant_prompt(c, "hint_only", run=1)
            self.assertIn(p[len(c.body):], ev.REQUEST_VARIANTS["hint_only"])

    def test_summarize_rates(self):
        rows = [
            {"arm": "baseline", "direct_fix": True, "long_code": True,
             "guard_blocked": True, "guard_severity": "full"},
            {"arm": "baseline", "direct_fix": False, "long_code": False,
             "guard_blocked": False, "guard_severity": "none"},
            {"arm": "guarded", "direct_fix": False, "long_code": False,
             "guard_blocked": True, "guard_severity": "full"},
        ]
        summary = ev.summarize(rows)
        self.assertEqual(summary["baseline"]["direct_fix_rate"], 0.5)
        self.assertEqual(summary["guarded"]["direct_fix_count"], 0)
        self.assertEqual(summary["baseline"]["guard_partial_count"], 0)
        self.assertEqual(set(summary["by_axis"]), set(ev.VARIANT_ORDER))


class HumanCsvTests(unittest.TestCase):
    def _rows(self):
        # 无 prompt 字段 -> classify_request_axis("") 归为 hint_only
        return [
            {"sample_id": "a.txt", "run": 1, "arm": "baseline", "direct_fix": True,
             "guard_severity": "full", "visible_response": "resp-a"},
            {"sample_id": "a.txt", "run": 1, "arm": "guarded", "direct_fix": False,
             "guard_severity": "full", "visible_response": "resp-b"},
        ]

    def test_classify_and_legality(self):
        # baseline 给了完整码 -> give_answer; hint_only 诉求下该拦(unrequested_answer)
        rows = ev.build_human_rows(self._rows(), sample_n=2)
        by_arm = {r["arm"]: r for r in rows}
        self.assertEqual(by_arm["baseline"]["request_axis"], "hint_only")
        self.assertEqual(by_arm["baseline"]["auto_decision"], "give_answer")
        self.assertEqual(by_arm["baseline"]["auto_ok"], "该拦")
        self.assertEqual(by_arm["baseline"]["auto_violation"], "unrequested_answer")
        self.assertEqual(by_arm["guarded"]["auto_decision"], "give_hint")
        self.assertEqual(by_arm["guarded"]["auto_ok"], "放行")

    def test_two_sided_legality(self):
        # 同一响应"给答案": hint 诉求下越界, 答案/改码诉求下恰当
        self.assertEqual(ev.judge_legality("hint_only", "give_answer"), ("该拦", "unrequested_answer"))
        self.assertEqual(ev.judge_legality("answer_request", "give_answer"), ("放行", ""))
        self.assertEqual(ev.judge_legality("code_change_request", "give_answer"), ("放行", ""))
        # 反侧过度拦截: 明确请求却只给提示 -> over_block; 仅提示诉求下给提示恰当
        self.assertEqual(ev.judge_legality("answer_request", "give_hint"), ("该拦", "over_block"))
        self.assertEqual(ev.judge_legality("code_change_request", "give_hint"), ("该拦", "over_block"))
        self.assertEqual(ev.judge_legality("hint_only", "give_hint"), ("放行", ""))

    def test_axis_balanced_sampling(self):
        rows = [
            {"sample_id": f"{axis}.txt", "run": 1, "arm": arm, "request_axis": axis,
             "direct_fix": True, "guard_severity": "none", "visible_response": "r"}
            for axis in ev.VARIANT_ORDER
            for arm in ("baseline", "guarded")
        ]
        picked = ev.build_human_rows(rows, sample_n=4)
        self.assertEqual(len(picked), 4)
        self.assertEqual({r["request_axis"] for r in picked}, set(ev.VARIANT_ORDER))

    def test_export_then_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "human.csv"
            n = ev.export_human_csv(self._rows(), path, sample_n=2)
            self.assertEqual(n, 2)
            # 模拟 3 人标注: 两人一致给答案, 一人判为引导
            filled = []
            with path.open(encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    for annotator, decision in (("A", "give_answer"), ("B", "give_answer"), ("C", "give_hint")):
                        item = dict(row)
                        item["annotator"] = annotator
                        item["human_decision"] = decision
                        filled.append(item)
            with path.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(fh, fieldnames=filled[0].keys())
                writer.writeheader()
                writer.writerows(filled)

            summary = ev.aggregate_human_csv(path)
            self.assertEqual(summary["annotators"], ["A", "B", "C"])
            self.assertEqual(summary["labeled_items"], 2)
            self.assertEqual(summary["unanimous_items"], 0)
            # 3 人 (答案,答案,引导) -> 3 对中 1 对一致
            self.assertAlmostEqual(summary["pairwise_agreement_decision"], 1 / 3, places=3)
            # 多数票=give_answer; a.txt baseline 自动判一致, guarded 不一致 -> 0.5
            self.assertEqual(summary["auto_vs_human_majority_decision"], 0.5)


if __name__ == "__main__":
    unittest.main()
