# -*- coding: utf-8 -*-
"""convert_dpo_to_tools.convert_row 的 L4 无 bug 索改分支单元测试。

覆盖（plan §3.10 ④）：
  * 命中：学生索改且贴码=参考解（确证无缺陷）→ chosen=give_answer（说明无需修改），
    rejected=modify_code（硬改），tool_decision="answer_vs_modify"；
  * 逃生门豁免：声明工具性使用（工作/公司内部）→ 不走 L4（走 modify_vs_hint）；
  * 非 clean 不触发：贴码非参考解（无法确证无缺陷）→ 不误判为 L4。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

SCRIPT_PATH = BACKEND / "scripts" / "convert_dpo_to_tools.py"
_spec = importlib.util.spec_from_file_location("convert_dpo_to_tools", SCRIPT_PATH)
cdt = importlib.util.module_from_spec(_spec)
sys.modules["convert_dpo_to_tools"] = cdt
_spec.loader.exec_module(cdt)

from verify_lab_content import REFERENCE_SOLUTIONS  # noqa: E402


def _stats() -> dict:
    """与 convert_file 同构的统计初值（含新增 no_bug_confirmation）。"""
    return {"input": 0, "converted": 0, "text_only": 0, "multiturn_upgraded": 0,
            "dropped_chosen_violation": 0, "dropped_rejected_clean": 0,
            "no_bug_confirmation": 0}


class L4NoBugConversionTests(unittest.TestCase):
    """L4 无 bug 索改：贴码=参考解时正解是确认无需修改，而非硬改。"""

    @classmethod
    def setUpClass(cls):
        cls.ref = next(iter(REFERENCE_SOLUTIONS.values()))

    def _row(self, *, last_text: str, code: str) -> dict:
        """round2 样本：代码贴 r1、本轮请求在 r2（与多轮轨迹一致）。"""
        return {
            "prompt": [
                {"role": "user", "content": f"这是我的代码：\n```python\n{code}\n```"},
                {"role": "assistant", "content": "你发现什么问题了吗？"},
                {"role": "user", "content": last_text},
            ],
            "chosen": (f"我核对了一遍，你的实现没有发现问题。\n```python\n{self.ref}\n```\n"
                       "讲解：这份代码的关键判断方向是对的，所有用例都能通过，无需再改。"),
            "rejected": "你先别急，自己再想想：这版真的没有遗漏的边界情况吗？先确认一下好吗？",
            "layer": "P", "source": "codelab", "family": "codelab_x",
            "round": 2, "lang": "zh", "hint_level": 1, "subtype": "",
        }

    def test_clean_request_hits_l4(self):
        stats = _stats()
        out = cdt.convert_row(self._row(last_text="直接帮我改成能跑的版本吧。", code=self.ref), stats)
        self.assertIsNotNone(out)
        self.assertEqual(out["tool_decision"], "answer_vs_modify")
        chosen = json.loads(out["chosen"])
        rejected = json.loads(out["rejected"])
        self.assertEqual(chosen["tool"], "give_answer")
        self.assertIn("没有发现", chosen["args"]["why"])
        # 确认侧不得混入 ref_prose（round2 的"改了什么"修复叙述与"无需修改"矛盾）
        self.assertNotIn("关键判断方向", chosen["args"]["why"])
        self.assertEqual(chosen["args"]["code"], "")
        self.assertEqual(rejected["tool"], "modify_code")
        self.assertEqual(stats["no_bug_confirmation"], 1)

    def test_escape_hatch_exempts_l4(self):
        # 工具性使用声明（公司内部）→ 逃生门放行，允许按需改动正确代码（T1 对型）
        stats = _stats()
        row = self._row(last_text="这是公司内部要用的工具，直接帮我改成能跑的版本吧。",
                        code=self.ref)
        out = cdt.convert_row(row, stats)
        self.assertIsNotNone(out)
        self.assertNotEqual(out["tool_decision"], "answer_vs_modify")
        self.assertEqual(out["tool_decision"], "modify_vs_hint")
        self.assertEqual(stats["no_bug_confirmation"], 0)

    def test_nonclean_code_does_not_hit_l4(self):
        # 贴码为变异体（无法确证无缺陷）→ 宁漏勿杀，不判为 L4
        stats = _stats()
        mutated = "mutated_marker = 1\n" + self.ref
        out = cdt.convert_row(self._row(last_text="直接帮我改成能跑的版本吧。", code=mutated), stats)
        self.assertIsNotNone(out)
        self.assertEqual(out["tool_decision"], "modify_vs_hint")
        self.assertEqual(stats["no_bug_confirmation"], 0)


if __name__ == "__main__":
    unittest.main()
