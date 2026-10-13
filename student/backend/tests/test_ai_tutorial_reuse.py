# -*- coding: utf-8 -*-
"""C5：AI 生成教程复用查询的单元测试。

generate_tutorial 调大模型前先走 find_existing_ai_tutorial：
同标签（或同标题）已有该用户的 AI 生成教程 → 直接复用，不重复调用大模型。
这里只测查询函数本身（路由层的接线依赖鉴权与 LLM，不适合单测）。
"""
import sqlite3
import unittest

from services.resource_service import find_existing_ai_tutorial


def _make_conn() -> sqlite3.Connection:
    """最小 tutorial_documents 表结构（与 database.py 初始化一致的关键列）"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE tutorial_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_tag TEXT NOT NULL,
            title TEXT DEFAULT '',
            content TEXT NOT NULL,
            source_type TEXT DEFAULT 'seed',
            user_id INTEGER,
            parent_id INTEGER
        )
    """)
    return conn


class AiTutorialReuseTests(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()

    def tearDown(self):
        self.conn.close()

    def _insert(self, tag, title, content, source_type, user_id):
        cur = self.conn.execute(
            "INSERT INTO tutorial_documents (knowledge_tag, title, content, source_type, user_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (tag, title, content, source_type, user_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def test_same_tag_ai_generated_is_reused(self):
        tid = self._insert("智能体基础", "智能体基础", "# 已生成内容", "ai_generated", 1)
        got = find_existing_ai_tutorial(self.conn, 1, "智能体基础", "智能体基础")
        self.assertIsNotNone(got)
        self.assertEqual(got["tutorial_id"], tid)
        self.assertEqual(got["content"], "# 已生成内容")

    def test_other_users_ai_tutorial_is_not_reused(self):
        self._insert("智能体基础", "智能体基础", "# 别人的", "ai_generated", 2)
        self.assertIsNone(find_existing_ai_tutorial(self.conn, 1, "智能体基础", "智能体基础"))

    def test_seed_and_user_modified_are_not_reused(self):
        # 只有 ai_generated 才算「已生成」：种子文档、用户手改版都要重新走生成
        self._insert("智能体基础", "智能体基础", "# 种子", "seed", None)
        self.assertIsNone(find_existing_ai_tutorial(self.conn, 1, "智能体基础", "智能体基础"))
        self._insert("智能体基础", "智能体基础", "# 手改", "user_modified", 1)
        self.assertIsNone(find_existing_ai_tutorial(self.conn, 1, "智能体基础", "智能体基础"))

    def test_falls_back_to_title_match_when_tag_empty(self):
        tid = self._insert("", "递归入门", "# 按标题命中", "ai_generated", 1)
        got = find_existing_ai_tutorial(self.conn, 1, "", "递归入门")
        self.assertIsNotNone(got)
        self.assertEqual(got["tutorial_id"], tid)

    def test_returns_none_without_tag_and_title(self):
        self._insert("", "无关标题", "# x", "ai_generated", 1)
        self.assertIsNone(find_existing_ai_tutorial(self.conn, 1, "", ""))

    def test_latest_row_wins_when_duplicates_exist(self):
        # 历史数据可能已有重复行：取最新一条（与生成端插入顺序一致）
        self._insert("智能体基础", "智能体基础", "# 旧", "ai_generated", 1)
        tid_new = self._insert("智能体基础", "智能体基础", "# 新", "ai_generated", 1)
        got = find_existing_ai_tutorial(self.conn, 1, "智能体基础", "智能体基础")
        self.assertEqual(got["tutorial_id"], tid_new)
        self.assertEqual(got["content"], "# 新")


if __name__ == "__main__":
    unittest.main()
