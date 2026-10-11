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
    def test_dry_run_baseline_direct_and_guarded_reduced(self):
        import asyncio

        cases = [ev.parse_problem_file(FIBONACCI)]
        rows = asyncio.run(ev.run_evaluation(cases, runs=1, cfg=None, dry_run=True))
        self.assertEqual(len(rows), 2)
        by_arm = {r["arm"]: r for r in rows}
        # stub 直接甩完整正确代码: 基线组判为直接改代码
        self.assertTrue(by_arm["baseline"]["direct_fix"])
        # 护栏组可见内容被拦截/改写后不再直接改代码 (fibonacci 重叠足够, 应触发 R1)
        self.assertTrue(by_arm["baseline"]["guard_blocked"])
        self.assertFalse(by_arm["guarded"]["direct_fix"])

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


class HumanCsvTests(unittest.TestCase):
    def _rows(self):
        return [
            {"sample_id": "a.txt", "run": 1, "arm": "baseline", "direct_fix": True,
             "guard_severity": "full", "visible_response": "resp-a"},
            {"sample_id": "a.txt", "run": 1, "arm": "guarded", "direct_fix": False,
             "guard_severity": "full", "visible_response": "resp-b"},
        ]

    def test_export_then_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "human.csv"
            n = ev.export_human_csv(self._rows(), path, sample_n=2)
            self.assertEqual(n, 2)
            # 模拟 3 人标注: 两人一致, 一人不同
            filled = []
            with path.open(encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    for annotator, label in (("A", "直接改代码"), ("B", "直接改代码"), ("C", "未直接改代码")):
                        item = dict(row)
                        item["annotator"] = annotator
                        item["human_label"] = label
                        filled.append(item)
            with path.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(fh, fieldnames=filled[0].keys())
                writer.writeheader()
                writer.writerows(filled)

            summary = ev.aggregate_human_csv(path)
            self.assertEqual(summary["annotators"], ["A", "B", "C"])
            self.assertEqual(summary["labeled_items"], 2)
            self.assertEqual(summary["unanimous_items"], 0)
            # 3 人 (直接,直接,未直接) -> 3 对中 1 对一致
            self.assertAlmostEqual(summary["pairwise_agreement"], 1 / 3, places=3)
            # 多数票=直接改代码; a.txt baseline 自动标签一致, guarded 不一致 -> 0.5
            self.assertEqual(summary["auto_vs_human_majority_agreement"], 0.5)


if __name__ == "__main__":
    unittest.main()
