"""Regression tests for the redesigned educational transfer stages."""

import importlib.util
import json
import unittest
from pathlib import Path

from services import capability_service
from services.agent_lab_faults import FAULT_PROFILES
from services.agent_lab_specs import FLAGSHIP_IDS
from tests.test_judge_service import CORRECT_SOLUTION


def _load_reference_solutions() -> dict:
    """复用 scripts/verify_lab_content.py 里的变式参考答案，避免两处各写一份。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_lab_content.py"
    spec = importlib.util.spec_from_file_location("verify_lab_content", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.VARIANT_REFERENCE_SOLUTIONS


VARIANT_REFERENCE_SOLUTIONS = _load_reference_solutions()


class VariantLearningContentTest(unittest.TestCase):
    def assert_variant_passes(self, exercise_id: str, code: str) -> None:
        result = capability_service._judge_variant_code(
            code, capability_service._get_variant_spec(exercise_id),
        )
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["passed_count"], result["total"])

    def test_every_flagship_has_a_fault_profile(self):
        self.assertEqual(set(FAULT_PROFILES), set(FLAGSHIP_IDS))

    def test_every_variant_reference_solution_passes(self):
        """2-1 ~ 4-3 这 10 道数据结构变式都要能被真实判题器判为通过。"""
        for exercise_id in sorted(VARIANT_REFERENCE_SOLUTIONS, key=lambda item: (item[0], item[2])):
            with self.subTest(exercise_id=exercise_id):
                self.assert_variant_passes(exercise_id, VARIANT_REFERENCE_SOLUTIONS[exercise_id])

    def test_variants_are_single_target_without_agent_runners(self):
        """纯算法变式只能有一个目标函数，且不得再走 Agent 专用判题分支。"""
        from services.agent_lab_variants import ADDITIONAL_VARIANT_SPECS

        for exercise_id, spec in ADDITIONAL_VARIANT_SPECS.items():
            with self.subTest(exercise_id=exercise_id):
                self.assertIsInstance(spec.get("target"), str)
                self.assertTrue(spec["target"])
                self.assertIsNone(spec.get("runner"))
                # 迁移到 C++ 后，Python 时代的类型校验用例（传字符串/浮点/布尔当索引、
                # 传标量当列表等）在编译期就被挡掉、无法表达，已按设计删除，改用 C++
                # 的真实边界用例（空/单元素/越界/异常）顶上，所以用例数普遍下降
                # （1-2=8 / 1-3=10 / 2-2=11 / 4-1=6）。「够不够厚」不再是有效判据，
                # 业务覆盖由 test_every_variant_reference_solution_passes 兜住。
                self.assertGreaterEqual(len(spec.get("cases", [])), 6)
                self.assertEqual(len(spec.get("hints", [])), 3)

    def test_public_fault_prompt_hides_private_root_cause(self):
        mutated, encoded = capability_service._build_mutation("1-1", CORRECT_SOLUTION)
        self.assertNotEqual(mutated, CORRECT_SOLUTION)
        metadata = json.loads(encoded)
        # 公开提示只给失败现象和考查方向，根因原文必须留在私有字段里。
        self.assertIn("故障现象", metadata["public"])
        root_cause = metadata["root_cause"]
        self.assertTrue(root_cause)
        self.assertNotIn(root_cause, metadata["public"])


if __name__ == "__main__":
    unittest.main()
