# -*- coding: utf-8 -*-
"""#31 教程随学习动态演化：内容层/个性化层分离的单元测试。

覆盖三部分：
1. 纯函数——画像指纹（compute_profile_fingerprint）、漂移判定（has_profile_drift）、
   个性化层生成（build_personalization_layer）；
2. 拼接函数——正文层 + 个性化层合成展示文本（compose_tutorial_text）；
3. 演化主流程——evolve_ai_tutorial 只重算个性化层、正文层稳定复用、漂移标志正确。
"""
import sqlite3
import unittest

from services import personalization_service as ps
from services.resource_service import compose_tutorial_text, evolve_ai_tutorial


def _make_conn() -> sqlite3.Connection:
    """最小 tutorial_documents 表结构（含 #31 分层演化新增列）"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE tutorial_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_tag TEXT NOT NULL,
            title TEXT DEFAULT '',
            content TEXT NOT NULL,
            content_layer TEXT DEFAULT '',
            personalization_layer TEXT DEFAULT '',
            profile_fingerprint TEXT DEFAULT '',
            profile_snapshot TEXT DEFAULT '',
            source_type TEXT DEFAULT 'seed',
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


class ProfileFingerprintTests(unittest.TestCase):
    def test_same_semantics_same_fingerprint(self):
        a = {"mastery_level": "中档", "weak_tags": ["递归", "指针"]}
        b = {"mastery_level": "中档", "weak_tags": ["指针", "递归"]}  # 顺序不同，语义相同
        self.assertEqual(ps.compute_profile_fingerprint(a), ps.compute_profile_fingerprint(b))

    def test_level_change_changes_fingerprint(self):
        a = {"mastery_level": "中档", "weak_tags": ["递归"]}
        b = {"mastery_level": "待加强", "weak_tags": ["递归"]}
        self.assertNotEqual(ps.compute_profile_fingerprint(a), ps.compute_profile_fingerprint(b))

    def test_weak_tags_change_changes_fingerprint(self):
        a = {"mastery_level": "中档", "weak_tags": ["递归"]}
        b = {"mastery_level": "中档", "weak_tags": ["递归", "指针"]}
        self.assertNotEqual(ps.compute_profile_fingerprint(a), ps.compute_profile_fingerprint(b))

    def test_overall_mastery_alone_does_not_change_fingerprint(self):
        # 连续值波动不参与指纹，避免无意义的频繁演化
        a = {"mastery_level": "中档", "weak_tags": ["递归"], "overall_mastery": 0.61}
        b = {"mastery_level": "中档", "weak_tags": ["递归"], "overall_mastery": 0.66}
        self.assertEqual(ps.compute_profile_fingerprint(a), ps.compute_profile_fingerprint(b))

    def test_empty_snapshot_returns_blank(self):
        self.assertEqual(ps.compute_profile_fingerprint(None), "")
        self.assertEqual(ps.compute_profile_fingerprint({}), "")


class ProfileDriftTests(unittest.TestCase):
    def test_blank_stored_fingerprint_is_not_drift(self):
        # 历史数据未回填指纹：一律不算漂移，避免误标旧教程过期
        self.assertFalse(ps.has_profile_drift("", {"mastery_level": "中档", "weak_tags": ["递归"]}))

    def test_unchanged_profile_is_not_drift(self):
        snap = {"mastery_level": "中档", "weak_tags": ["递归"]}
        stored = ps.compute_profile_fingerprint(snap)
        self.assertFalse(ps.has_profile_drift(stored, snap))

    def test_changed_profile_is_drift(self):
        stored = ps.compute_profile_fingerprint({"mastery_level": "中档", "weak_tags": ["递归"]})
        self.assertTrue(ps.has_profile_drift(stored, {"mastery_level": "待加强", "weak_tags": ["递归"]}))


class PersonalizationLayerTests(unittest.TestCase):
    def test_layer_contains_level_and_weak_tags(self):
        text = ps.build_personalization_layer({"mastery_level": "待加强", "weak_tags": ["递归", "指针"]})
        self.assertIn("个性化学习提示", text)
        self.assertIn("待加强", text)
        self.assertIn("递归", text)
        self.assertIn("指针", text)

    def test_layer_is_deterministic(self):
        snap = {"mastery_level": "中档", "weak_tags": ["递归"]}
        self.assertEqual(ps.build_personalization_layer(snap), ps.build_personalization_layer(snap))

    def test_layer_without_weak_tags_and_evidence(self):
        text = ps.build_personalization_layer(None)
        self.assertIn("暂无证据", text)
        self.assertIn("暂无薄弱项记录", text)


class ComposeTutorialTextTests(unittest.TestCase):
    def test_compose_appends_layer_with_separator(self):
        got = compose_tutorial_text("# 正文", "## 个性化学习提示\n\n- 提示")
        self.assertTrue(got.startswith("# 正文"))
        self.assertIn("---", got)
        self.assertIn("个性化学习提示", got)

    def test_compose_without_layer_returns_body(self):
        self.assertEqual(compose_tutorial_text("# 正文", ""), "# 正文")

    def test_compose_handles_none(self):
        self.assertEqual(compose_tutorial_text("# 正文", None), "# 正文")


class EvolveAiTutorialTests(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()

    def tearDown(self):
        self.conn.close()

    def _insert(self, tag, title, content, content_layer="", fingerprint="", source_type="ai_generated", user_id=1):
        cur = self.conn.execute(
            "INSERT INTO tutorial_documents"
            " (knowledge_tag, title, content, content_layer, profile_fingerprint, source_type, user_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tag, title, content, content_layer, fingerprint, source_type, user_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def test_evolve_updates_personalization_and_keeps_content_layer(self):
        snap_a = {"mastery_level": "中档", "weak_tags": ["递归"]}
        tid = self._insert(
            "递归", "递归入门", "# 稳定的正文层", content_layer="# 稳定的正文层",
            fingerprint=ps.compute_profile_fingerprint(snap_a),
        )
        snap_b = {"mastery_level": "待加强", "weak_tags": ["递归", "指针"]}
        result = evolve_ai_tutorial(self.conn, 1, "递归", snap_b)

        self.assertEqual(result["tutorial_id"], tid)
        self.assertTrue(result["drifted"])                     # 画像已漂移
        self.assertEqual(result["content_layer"], "# 稳定的正文层")  # 正文层稳定复用
        self.assertIn("待加强", result["content"])
        self.assertIn("指针", result["content"])
        self.assertEqual(result["profile_fingerprint"], ps.compute_profile_fingerprint(snap_b))

        row = self.conn.execute(
            "SELECT content, content_layer, personalization_layer FROM tutorial_documents WHERE id = ?",
            (tid,),
        ).fetchone()
        self.assertEqual(row["content_layer"], "# 稳定的正文层")
        self.assertIn("个性化学习提示", row["personalization_layer"])
        self.assertIn("个性化学习提示", row["content"])

    def test_evolve_again_without_change_reports_no_drift(self):
        snap = {"mastery_level": "中档", "weak_tags": ["递归"]}
        self._insert(
            "递归", "递归入门", "# 正文", content_layer="# 正文",
            fingerprint=ps.compute_profile_fingerprint(snap),
        )
        first = evolve_ai_tutorial(self.conn, 1, "递归", snap)
        self.assertFalse(first["drifted"])
        second = evolve_ai_tutorial(self.conn, 1, "递归", snap)
        self.assertFalse(second["drifted"])

    def test_evolve_legacy_row_uses_content_as_content_layer(self):
        # 历史数据 content_layer 为空：以现存正文兜底作为正文层，且不重复追加
        tid = self._insert("递归", "递归入门", "# 老正文", content_layer="", fingerprint="")
        snap = {"mastery_level": "中档", "weak_tags": []}
        result = evolve_ai_tutorial(self.conn, 1, "递归", snap)
        self.assertEqual(result["content_layer"], "# 老正文")
        self.assertFalse(result["drifted"])  # 原指纹为空，不算漂移
        row = self.conn.execute(
            "SELECT content_layer FROM tutorial_documents WHERE id = ?", (tid,)
        ).fetchone()
        self.assertEqual(row["content_layer"], "# 老正文")

    def test_evolve_returns_none_without_ai_tutorial(self):
        self._insert("递归", "递归入门", "# 种子", source_type="seed", user_id=None)
        self.assertIsNone(evolve_ai_tutorial(self.conn, 1, "递归", {"mastery_level": "中档"}))

    def test_evolve_ignores_other_users_tutorial(self):
        self._insert("递归", "递归入门", "# 别人的", user_id=2)
        self.assertIsNone(evolve_ai_tutorial(self.conn, 1, "递归", {"mastery_level": "中档"}))


if __name__ == "__main__":
    unittest.main()
