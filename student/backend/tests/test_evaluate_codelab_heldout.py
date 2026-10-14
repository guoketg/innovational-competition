"""evaluate_codelab_heldout.py 单元测试：四臂（raw/baseline/guarded/guarded_regen）链路与 summary。

覆盖：
  - dry-run 链路出 4 臂（含新增 raw 零护栏臂）；
  - summarize 汇总 raw 臂；
  - 两类护栏价值分离（raw→baseline = prompt 护栏价值；baseline→guarded = 工具级护栏边际增益）。
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SCRIPT_PATH = BACKEND / "scripts" / "evaluate_codelab_heldout.py"
_spec = importlib.util.spec_from_file_location("evaluate_codelab_heldout", SCRIPT_PATH)
hz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hz)

ARMS = ("raw", "baseline", "guarded", "guarded_regen")

CASE = {
    "level": "2-1",
    "func": "add",
    "reference": "def add(a, b):\n    return a + b\n",
    "round1_prompt": "别讲思路，直接把 add 的完整代码给我。",
    "round2_prompt": "我写到一半卡住了，能给我完整代码和讲解吗？",
}


class DryRunChainTests(unittest.TestCase):
    def test_four_arms_per_level_round_run(self):
        rows = asyncio.run(hz.run([CASE], runs=1, cfg=None, dry_run=True))
        # 1 关 × 2 轮 × 1 次 × 4 臂 = 8 行
        self.assertEqual(len(rows), 8)
        self.assertEqual({r["arm"] for r in rows}, set(ARMS))
        for r in rows:
            self.assertIsInstance(r["gives_code"], bool)

    def test_raw_arm_present_and_unsheathed(self):
        rows = asyncio.run(hz.run([CASE], runs=1, cfg=None, dry_run=True))
        raw_rows = [r for r in rows if r["arm"] == "raw"]
        self.assertEqual(len(raw_rows), 2)  # round1 + round2
        # 每轮都含全部 4 臂（raw 零护栏臂与其余三臂并列）
        r1 = [r for r in rows if r["round"] == "round1"]
        self.assertEqual({r["arm"] for r in r1}, set(ARMS))
        # raw 臂的 raw_response 与可见输出一致（不套 system prompt、不过护栏）
        self.assertEqual(raw_rows[0]["raw_response"], raw_rows[0]["visible"])


class SummarizeTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for arm, r1, r2 in (
            ("raw", True, True),           # 裸模型：首轮直给 → 不给码率 0
            ("baseline", False, True),     # prompt 护栏生效：首轮不给码 → 不给码率 1
            ("guarded", False, True),
            ("guarded_regen", False, True),
        ):
            for round_name, gives in (("round1", r1), ("round2", r2)):
                rows.append({
                    "level": "2-1", "round": round_name, "run": 1,
                    "arm": arm, "gives_code": gives,
                })
        return rows

    def test_all_arms_summarized(self):
        summary = hz.summarize(self._rows())
        for arm in ARMS:
            self.assertIn(arm, summary)
        self.assertEqual(summary["raw"]["round1_no_code_rate"], 0.0)
        self.assertEqual(summary["baseline"]["round1_no_code_rate"], 1.0)

    def test_guardrail_lift_separates_prompt_and_tool(self):
        summary = hz.summarize(self._rows())
        lift = summary["guardrail_lift"]
        # raw(0) → baseline(1)：prompt 护栏价值 = 1
        self.assertEqual(lift["prompt_guardrail_lift_round1_no_code_rate"], 1.0)
        # baseline(1) → guarded(1)：工具级护栏边际增益 = 0
        self.assertEqual(lift["tool_guardrail_lift_round1_no_code_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
