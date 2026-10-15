"""build_dpo_pairs 工具决策质检（validate_tool_call 查表 v2）单元测试。

覆盖：no_bug_no_touch（plan §3.10 ⑤ 无 bug 检查：贴码与参考解逐字等价时
chosen 不得为 modify_code）与 scope_overreach / 未请求主动改 等存量查表项回归。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

SCRIPT_PATH = BACKEND / "scripts" / "build_dpo_pairs.py"
_spec = importlib.util.spec_from_file_location("build_dpo_pairs", SCRIPT_PATH)
bdp = importlib.util.module_from_spec(_spec)
# dataclass（PairDraft）在 py3.10 解析注解时会查 sys.modules[cls.__module__]，必须先注册
sys.modules["build_dpo_pairs"] = bdp
_spec.loader.exec_module(bdp)

from verify_lab_content import REFERENCE_SOLUTIONS  # noqa: E402


def _ctx(**kw) -> dict:
    """validate_tool_call 的基底上下文（默认：r1 明确请求改码、非窄范围、无逃生门）。"""
    ctx = {
        "round": 1,
        "requested": True,
        "tool_context": False,
        "release_expected": False,
        "request_scope": "full",
        "prompt_code_clean": False,
    }
    ctx.update(kw)
    return ctx


def _modify(patch: str = "x = 1", why: str = "修复越界") -> dict:
    return bdp.parse_tool_call(bdp.make_tool_call("modify_code", {"patch": patch, "why": why}))


def _hint(text: str = "先打印一下 a、b 的中间值试试。", level: int = 2) -> dict:
    return bdp.parse_tool_call(bdp.make_tool_call("give_hint", {"level": level, "text": text}))


class NoBugCheckTests(unittest.TestCase):
    """无 bug 检查（plan §3.10 ⑤）：确证无缺陷 → modify_code 违规；无法确证不触发。"""

    def test_no_bug_flagged_when_clean(self):
        bad = bdp.validate_tool_call(_modify(), _ctx(prompt_code_clean=True))
        self.assertTrue(any("no_bug_no_touch" in v for v in bad), bad)

    def test_no_bug_exempt_tool_context(self):
        # 逃生门豁免：工具性使用允许按需改动（T1 对型，含正确代码的重构请求）
        bad = bdp.validate_tool_call(_modify(), _ctx(prompt_code_clean=True, tool_context=True))
        self.assertEqual(bad, [])

    def test_no_bug_silent_when_unconfirmed(self):
        # 变异体 / 自由代码 / 无贴码 → 无法确证 → 宁可漏检不误杀，不触发
        self.assertEqual(bdp.validate_tool_call(_modify(), _ctx(prompt_code_clean=False)), [])

    def test_no_bug_silent_for_hint(self):
        # 学生贴正确代码只求引导时，give_hint 的违规是"过度拦截"，不是 no_bug
        bad = bdp.validate_tool_call(_hint(), _ctx(prompt_code_clean=True))
        self.assertTrue(any("过度拦截" in v for v in bad), bad)
        self.assertFalse(any("no_bug_no_touch" in v for v in bad), bad)


class ExistingCheckRegressionTests(unittest.TestCase):
    """存量查表项回归：scope_overreach 与 未请求主动改。"""

    def test_scope_overreach_flagged(self):
        patch = "\n".join(f"line_{i} = {i}" for i in range(13))  # 13 行非空 > 12
        bad = bdp.validate_tool_call(_modify(patch=patch), _ctx(request_scope="narrow"))
        self.assertTrue(any("scope_overreach" in v for v in bad), bad)

    def test_unrequested_modify_regression(self):
        bad = bdp.validate_tool_call(_modify(), _ctx(requested=False))
        self.assertTrue(any("未请求主动改" in v for v in bad), bad)


class PromptCodeCleanTests(unittest.TestCase):
    """prompt_code_is_clean：贴码与 verify_lab_content 参考解逐字等价（忽略空白）。"""

    @classmethod
    def setUpClass(cls):
        cls.ref = next(iter(REFERENCE_SOLUTIONS.values()))

    def _fenced(self, code: str) -> str:
        return f"帮我改一下：\n```python\n{code}\n```"

    def test_real_reference_is_clean(self):
        self.assertTrue(bdp.prompt_code_is_clean(self._fenced(self.ref)))

    def test_whitespace_only_variant_is_clean(self):
        # 中间加空行 / 行尾空白 → 规范化后仍等价
        padded = "\n\n".join(f"{ln}  " for ln in self.ref.splitlines())
        self.assertTrue(bdp.prompt_code_is_clean(self._fenced(padded)))

    def test_mutated_is_not_clean(self):
        # 首行插入标记行 → 肯定不等价于任何参考解（宁漏勿杀口径下不算 clean）
        mutated = "mutated_marker = 1\n" + self.ref
        self.assertFalse(bdp.prompt_code_is_clean(self._fenced(mutated)))

    def test_no_code_text_is_not_clean(self):
        self.assertFalse(bdp.prompt_code_is_clean("老师我第 3 行老是报错怎么办？"))


class BuildToolContextIntegrationTests(unittest.TestCase):
    """build_tool_context → validate_tool_call 端到端接线验证。"""

    @classmethod
    def setUpClass(cls):
        cls.ref = next(iter(REFERENCE_SOLUTIONS.values()))

    def test_single_turn_clean_code_hits_no_bug(self):
        prompt = [{"role": "user", "content": f"帮我改一下：\n```python\n{self.ref}\n```"}]
        ctx = bdp.build_tool_context(prompt, round_no=1, release_expected=False)
        self.assertTrue(ctx["requested"])          # "帮我改一下" 命中 modify
        self.assertTrue(ctx["prompt_code_clean"])
        bad = bdp.validate_tool_call(_modify(), ctx)
        self.assertTrue(any("no_bug_no_touch" in v for v in bad), bad)

    def test_multiturn_code_in_r1_request_in_r2(self):
        # 升级后多轮轨迹形态：代码贴在 r1、本轮请求在 r2（upgrade_multiturn_trajectory）
        prompt = [
            {"role": "user", "content": f"这是我的代码：\n```python\n{self.ref}\n```"},
            {"role": "assistant", "content": "你发现了什么问题？"},
            {"role": "user", "content": "直接帮我改成能跑的版本吧。"},
        ]
        self.assertEqual(bdp.last_user_text(prompt), "直接帮我改成能跑的版本吧。")
        # extract_code_blocks 的 code 保留尾随换行，比较须与 clean 判据同口径（规范化空白）
        self.assertEqual(
            bdp.last_student_code(prompt).strip(), self.ref.strip()
        )
        ctx = bdp.build_tool_context(prompt, round_no=2, release_expected=True)
        self.assertTrue(ctx["requested"])
        self.assertTrue(ctx["prompt_code_clean"])
        bad = bdp.validate_tool_call(_modify(), ctx)
        self.assertTrue(any("no_bug_no_touch" in v for v in bad), bad)


if __name__ == "__main__":
    unittest.main()
