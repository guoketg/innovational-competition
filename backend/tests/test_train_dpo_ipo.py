# -*- coding: utf-8 -*-
"""train_dpo_ipo_qwen3_8b.py 的单元测试。

覆盖：方法映射（DPO→sigmoid / IPO→ipo）、偏好对 JSONL 校验、环境自检报告结构。
训练本体依赖 GPU 与服务器 .venv，不在单测范围；本文件用 importlib 按路径加载
脚本（scripts/ 不是包），保证脚本顶层只依赖标准库即可导入。
"""
import importlib.util
import os
import unittest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_BACKEND_DIR, "scripts", "train_dpo_ipo_qwen3_8b.py")

_spec = importlib.util.spec_from_file_location("train_dpo_ipo_qwen3_8b", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class MethodConfigTests(unittest.TestCase):
    def test_dpo_maps_to_sigmoid(self):
        cfg = mod.method_config("dpo")
        self.assertEqual(cfg["loss_type"], "sigmoid")
        self.assertEqual(cfg["label"], "DPO")
        self.assertTrue(cfg["output_dir"].endswith("alignment-8B-dpo"))

    def test_ipo_maps_to_ipo(self):
        cfg = mod.method_config("IPO")  # 大小写不敏感
        self.assertEqual(cfg["loss_type"], "ipo")
        self.assertEqual(cfg["label"], "IPO")
        self.assertTrue(cfg["output_dir"].endswith("alignment-8B-ipo"))

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            mod.method_config("dpop")
        with self.assertRaises(ValueError):
            mod.method_config("")


class ValidatePairFileTests(unittest.TestCase):
    def test_missing_file(self):
        v = mod.validate_pair_file(os.path.join(_BACKEND_DIR, "data", "dpo", "nope.jsonl"))
        self.assertFalse(v["exists"])
        self.assertFalse(v["ok"])
        self.assertEqual(v["count"], 0)

    def test_repo_train_and_eval_files_valid(self):
        for path in (mod.DEFAULT_TRAIN_FILE, mod.DEFAULT_EVAL_FILE):
            v = mod.validate_pair_file(path)
            self.assertTrue(v["exists"], f"{path} 应存在（随仓库提交）")
            self.assertGreater(v["count"], 0, f"{path} 应含样本")
            self.assertTrue(v["ok"], f"{path} 校验失败: {v['errors']}")

    def test_rejects_bad_jsonl(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8") as f:
            f.write('{"prompt": [], "chosen": "a", "rejected": "b"}\n')  # 合法
            f.write("not-json\n")                                          # 非法
            f.write('{"prompt": [], "chosen": "a"}\n')                     # 缺 rejected
            path = f.name
        try:
            v = mod.validate_pair_file(path)
            self.assertEqual(v["count"], 3)
            self.assertFalse(v["ok"])
            self.assertEqual(len(v["errors"]), 2)
        finally:
            os.unlink(path)


class CheckEnvironmentTests(unittest.TestCase):
    def test_report_structure_and_data_items_pass(self):
        report = mod.check_environment(mod.DEFAULT_TRAIN_FILE, mod.DEFAULT_EVAL_FILE,
                                       os.path.join(_BACKEND_DIR, "outputs", "x"))
        names = [it["name"] for it in report["items"]]
        # 必检项齐全：python、两个数据文件、7 个训练依赖、输出目录
        self.assertIn("python", names)
        self.assertIn("train_file", names)
        self.assertIn("eval_file", names)
        self.assertEqual(sum(1 for n in names if n.startswith("dep:")), 7)
        self.assertIn("output_dir", names)
        by_name = {it["name"]: it for it in report["items"]}
        self.assertTrue(by_name["python"]["ok"])
        self.assertTrue(by_name["train_file"]["ok"])
        self.assertTrue(by_name["eval_file"]["ok"])
        # ok 必须是所有项的合取（训练依赖缺失时整体不通过）
        self.assertEqual(report["ok"], all(it["ok"] for it in report["items"]))


if __name__ == "__main__":
    unittest.main()
