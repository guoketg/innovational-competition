"""能力验证闭环的最小集成测试。"""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import database
from services import capability_service
from services import lab_workspace_service
from services.agent_lab_specs import lab_repair_file, lab_solution_file
from tests.test_judge_service import CORRECT_SOLUTION
from tests.test_variant_learning_content import VARIANT_REFERENCE_SOLUTIONS


class CapabilityLoopTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = os.path.join(self.temp_dir.name, "capability-test.db")
        self.original_workspace_root = lab_workspace_service.WORKSPACE_ROOT
        lab_workspace_service.WORKSPACE_ROOT = __import__("pathlib").Path(self.temp_dir.name) / "workspaces"
        database.init_db()
        conn = database.get_db()
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, nickname) VALUES ('capability-test', 'x', '测试学生')"
        )
        self.user_id = cursor.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        lab_workspace_service.WORKSPACE_ROOT = self.original_workspace_root
        self.temp_dir.cleanup()

    def test_progress_uses_latest_session_even_when_it_is_still_coding(self):
        old_session = capability_service.start_session(self.user_id, "1-1")
        conn = database.get_db()
        conn.execute(
            """UPDATE capability_sessions
               SET status = 'verified', verified = 1, total_score = 96,
                   completed_at = '2026-08-01T10:00:00'
               WHERE id = ?""",
            (old_session["id"],),
        )
        conn.commit()
        conn.close()

        latest_session = capability_service.start_session(
            self.user_id, "1-1", force_new=True
        )
        scores = capability_service.get_exercise_scores(self.user_id)

        self.assertEqual(scores["1-1"]["session_id"], latest_session["id"])
        self.assertEqual(scores["1-1"]["status"], "coding")
        self.assertFalse(scores["1-1"]["verified"])
        self.assertEqual(scores["1-1"]["score"], 0)

    @staticmethod
    def correct_code():
        return CORRECT_SOLUTION

    def test_code_defense_repair_report_loop(self):
        session = capability_service.start_session(self.user_id, "1-1")
        capability_service.record_events(self.user_id, session["id"], [
            {"type": "edit", "payload": {"delta": 42, "length": 900}},
            {"type": "run", "payload": {"passed": False, "failed": 1}},
            {"type": "run", "payload": {"passed": True, "failed": 0}},
            {"type": "submit", "payload": {"source": "code"}},
        ])

        passed = capability_service.mark_code_passed(self.user_id, session["id"], self.correct_code())
        self.assertEqual(passed["status"], "defense_pending")
        self.assertEqual(len(passed["defense_questions"]), 3)
        self.assertIn("source", passed["defense_questions"][0])
        self.assertNotEqual(passed["mutation_code"], self.correct_code())
        self.assertIn("故障现象", passed["mutation_description"])
        # 库里的完整载荷含私有根因；返回给学生的只能是公开提示那一段。
        conn = database.get_db()
        stored = json.loads(conn.execute(
            "SELECT mutation_description FROM capability_sessions WHERE id = ?",
            (session["id"],),
        ).fetchone()["mutation_description"])
        conn.close()
        self.assertTrue(stored["root_cause"])
        self.assertNotIn(stored["root_cause"], stored["public"])
        self.assertEqual(passed["mutation_description"], stored["public"])

        answers = [
            {"question_id": "q1", "answer": "array_insert 的输入参数是要插入的列表、下标和值；处理步骤是先校验类型与下标边界，再复制一份列表插入，返回新列表。"},
            {"question_id": "q2", "answer": "if 分支用于拒绝空字符串和错误类型；去掉后非法输入不会失败，私有错误用例会失败。"},
            {"question_id": "q3", "answer": "面对异常或边界输入，我会在入口校验层增加保护，明确修改位置，并补充测试用例验证 ValueError 和返回结构。"},
        ]
        ai_result = {
            "score": 88,
            "hit_points": ["核心流程", "边界条件"],
            "missing_points": [],
            "feedback": "回答结合了代码流程，可以继续补充工程取舍。",
            "reference_answer": "标准答案结合具体函数说明输入校验、处理步骤、返回结果和边界条件。",
        }
        with patch.object(
            capability_service,
            "call_llm",
            new=AsyncMock(return_value=__import__("json").dumps(ai_result, ensure_ascii=False)),
        ):
            defense = asyncio.run(capability_service.submit_defense(
                self.user_id, session["id"], answers, "AI提供了提示"
            ))
            self.assertTrue(defense["defense_passed"])
            self.assertEqual(defense["status"], "repair_pending")
            self.assertEqual(defense["defense_grading_status"], "pending")
            asyncio.run(capability_service.grade_defense_answers(self.user_id, session["id"]))
            defense = capability_service.get_session(self.user_id, session["id"])
            review = asyncio.run(capability_service.get_session_review(self.user_id, session["id"]))
        self.assertEqual(defense["status"], "repair_pending")
        self.assertEqual(defense["defense_grading_status"], "completed")
        self.assertEqual(len(review["review_items"]), 3)
        self.assertTrue(all(item["reference_answer"] for item in review["review_items"]))

        conn = database.get_db()
        persisted_defense = conn.execute(
            "SELECT defense_score, defense_answers_json FROM capability_sessions WHERE id = ?",
            (session["id"],),
        ).fetchone()
        conn.execute(
            """INSERT INTO code_submissions
               (user_id, exercise_id, code, passed, total, score, verified)
               VALUES (?, '1-1', ?, 1, 4, 100, 0)""",
            (self.user_id, self.correct_code()),
        )
        conn.commit()
        conn.close()
        self.assertGreaterEqual(persisted_defense["defense_score"], 60)
        self.assertIn("reference_answer", persisted_defense["defense_answers_json"])

        repaired = capability_service.submit_repair(
            self.user_id,
            session["id"],
            self.correct_code(),
            "array_insert 的边界判断被收紧成了 index >= len(items)，导致「追加到末尾」被误判为越界；我恢复为 index > len(items) 并重新运行全部边界测试。",
        )
        self.assertFalse(repaired["verified"])
        self.assertEqual(repaired["status"], "variant_pending")
        self.assertEqual(repaired["report"]["verdict"], "故障修复通过")
        self.assertGreaterEqual(repaired["report"]["total_score"], 60)

        variant_code = VARIANT_REFERENCE_SOLUTIONS["1-1"]
        variant = capability_service.submit_variant(
            self.user_id, session["id"], variant_code,
        )
        self.assertTrue(variant["variant_passed"])
        self.assertEqual(variant["status"], "verified")
        self.assertEqual(variant["report"]["dimensions"]["变式迁移"], 100)
        self.assertIn("代码正确性", variant["report"]["dimensions"])

        conn = database.get_db()
        row = conn.execute(
            "SELECT verified FROM code_submissions WHERE user_id = ? AND exercise_id = '1-1'",
            (self.user_id,),
        ).fetchone()
        mastery = conn.execute(
            "SELECT explanation_score, transfer_score FROM knowledge_mastery WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        conn.close()
        self.assertEqual(row["verified"], 1)
        self.assertGreaterEqual(mastery["explanation_score"], 60)
        self.assertEqual(mastery["transfer_score"], 100)

    def test_scored_defense_unlocks_repair_even_below_sixty(self):
        session = capability_service.start_session(self.user_id, "1-1")
        capability_service.mark_code_passed(self.user_id, session["id"], self.correct_code())
        answers = [
            {"question_id": "q1", "answer": "我结合输入、处理和输出说明当前函数。"},
            {"question_id": "q2", "answer": "这个分支用于拦截非法输入，删除会使边界用例失败。"},
            {"question_id": "q3", "answer": "list(items) 复制出的是浅拷贝，嵌套元素是共享引用。"},
        ]
        ai_result = {
            "score": 35,
            "hit_points": ["已作答"],
            "missing_points": ["缺少具体代码细节"],
            "feedback": "需要结合函数和变量补充说明。",
            "reference_answer": "应结合当前代码完整解释考察要点。",
        }
        with patch.object(
            capability_service,
            "call_llm",
            new=AsyncMock(return_value=__import__("json").dumps(ai_result, ensure_ascii=False)),
        ):
            result = asyncio.run(capability_service.submit_defense(
                self.user_id, session["id"], answers, "未使用提示",
            ))
            self.assertEqual(result["defense_grading_status"], "pending")
            asyncio.run(capability_service.grade_defense_answers(self.user_id, session["id"]))
            result = capability_service.get_session(self.user_id, session["id"])
            review = asyncio.run(capability_service.get_session_review(self.user_id, session["id"]))

        self.assertEqual(result["defense_score"], 35)
        self.assertEqual(result["status"], "repair_pending")
        self.assertEqual(result["defense_grading_status"], "completed")
        self.assertTrue(all(item["graded_by"] == "ai" for item in review["review_items"]))

    def test_defense_submit_unlocks_repair_when_ai_grading_fails(self):
        session = capability_service.start_session(self.user_id, "1-1")
        capability_service.mark_code_passed(self.user_id, session["id"], self.correct_code())
        answers = [
            {"question_id": "q1", "answer": "输入经过校验和清理后构造成消息列表。"},
            {"question_id": "q2", "answer": "分支用于拒绝非法输入，删除后边界用例会失败。"},
            {"question_id": "q3", "answer": "list(items) 复制出的是浅拷贝，嵌套元素是共享引用。"},
        ]

        result = asyncio.run(capability_service.submit_defense(
            self.user_id, session["id"], answers, "未使用提示",
        ))
        self.assertTrue(result["defense_passed"])
        self.assertEqual(result["status"], "repair_pending")
        self.assertEqual(result["defense_grading_status"], "pending")

        with patch.object(
            capability_service,
            "call_llm",
            new=AsyncMock(side_effect=ValueError("未配置 API Key")),
        ):
            asyncio.run(capability_service.grade_defense_answers(self.user_id, session["id"]))

        retriable = capability_service.get_session(self.user_id, session["id"])
        self.assertEqual(retriable["status"], "repair_pending")
        self.assertEqual(retriable["defense_grading_status"], "pending")

    def test_failed_repair_remains_blocked_until_it_passes(self):
        session = capability_service.start_session(self.user_id, "1-1")
        conn = database.get_db()
        conn.execute(
            """UPDATE capability_sessions
               SET status = 'repair_pending', code_score = 100, defense_score = 35,
                   mutation_description = '测试故障',
                   mutation_code = 'def array_insert(items, index, value):\n    return []\n'
               WHERE id = ?""",
            (session["id"],),
        )
        conn.commit()
        conn.close()

        result = capability_service.submit_repair(
            self.user_id,
            session["id"],
            "def array_insert(items, index, value):\n    return []\n",
            "我检查了插入流程并尝试恢复返回值，但当前提交仍有测试用例没有通过。",
        )

        self.assertFalse(result["repair_passed"])
        self.assertTrue(result["repair_completed"])
        self.assertEqual(result["status"], "repair_pending")
        self.assertFalse(result["verified"])
        self.assertLess(result["repair_score"], 100)
        persisted = capability_service.get_session(self.user_id, session["id"])
        self.assertEqual(persisted["status"], "repair_pending")
        self.assertFalse(persisted["report"]["repair_evidence"]["tests_passed"])

    def test_project_state_switches_refresh_real_workspace_and_keep_pass_permission(self):
        workspace = lab_workspace_service.get_workspace(self.user_id, "1-1")
        lab_workspace_service.save_file(
            self.user_id, "1-1", lab_solution_file("1-1"), self.correct_code(),
        )
        root = lab_workspace_service.WORKSPACE_ROOT / f"user-{self.user_id}" / "1-1"
        state = lab_workspace_service._read_state(root)
        state.update({
            "acceptance_ever_passed": True,
            "passed_solution_code": self.correct_code(),
            "completed_stages": ["acceptance"],
            "project_state": "passed",
        })
        lab_workspace_service._write_state(root, state)

        session = capability_service.start_session(self.user_id, "1-1")
        passed = capability_service.mark_code_passed(
            self.user_id, session["id"], self.correct_code(),
        )
        conn = database.get_db()
        conn.execute(
            "UPDATE capability_sessions SET status = 'repair_pending' WHERE id = ?",
            (session["id"],),
        )
        conn.commit()
        conn.close()

        repair = capability_service.switch_project_state(
            self.user_id, session["id"], "repair",
        )
        repair_files = {item["path"]: item["content"] for item in repair["workspace"]["files"]}
        self.assertEqual(repair["target_state"], "repair")
        self.assertEqual(repair_files[lab_repair_file("1-1")], passed["mutation_code"])
        self.assertEqual(repair_files[lab_solution_file("1-1")], self.correct_code())

        conn = database.get_db()
        conn.execute(
            "UPDATE capability_sessions SET status = 'variant_pending' WHERE id = ?",
            (session["id"],),
        )
        conn.commit()
        conn.close()
        capability_service.generate_variant(self.user_id, session["id"])
        variant = capability_service.switch_project_state(
            self.user_id, session["id"], "variant",
        )
        variant_files = {item["path"]: item["content"] for item in variant["workspace"]["files"]}
        self.assertIn("VARIANT_TASK.md", variant_files)
        self.assertIn(
            "insert_interval",
            variant_files[lab_solution_file("1-1")],
        )
        # 1-1 的变式现在也是 C++：骨架必须是签名，不能再是 def 语句
        self.assertIn("std::vector<std::vector<int>>", variant_files[lab_solution_file("1-1")])
        self.assertNotIn("def insert_interval", variant_files[lab_solution_file("1-1")])
        self.assertIn("日程表场景", variant_files["VARIANT_TASK.md"])

        conn = database.get_db()
        conn.execute(
            "UPDATE capability_sessions SET status = 'verified', verified = 1 WHERE id = ?",
            (session["id"],),
        )
        conn.commit()
        conn.close()
        reopened_repair = capability_service.switch_project_state(
            self.user_id, session["id"], "repair",
        )
        self.assertTrue(reopened_repair["reopened"])
        self.assertEqual(reopened_repair["session"]["status"], "repair_pending")

        conn = database.get_db()
        conn.execute(
            "UPDATE capability_sessions SET status = 'verified', verified = 1 WHERE id = ?",
            (session["id"],),
        )
        conn.commit()
        conn.close()
        reopened_variant = capability_service.switch_project_state(
            self.user_id, session["id"], "variant",
        )
        self.assertTrue(reopened_variant["reopened"])
        self.assertEqual(reopened_variant["session"]["status"], "variant_pending")

        initial = capability_service.switch_project_state(
            self.user_id, session["id"], "initial",
        )
        self.assertEqual(initial["workspace"]["project_state"], "initial")
        self.assertTrue(initial["workspace"]["state_options"]["can_switch_to_passed"])
        restored = capability_service.switch_project_state(
            self.user_id, session["id"], "passed",
        )
        restored_files = {item["path"]: item["content"] for item in restored["workspace"]["files"]}
        self.assertEqual(restored_files[lab_solution_file("1-1")], self.correct_code())
        self.assertEqual(
            set(restored["workspace"]["completed_stages"]),
            {item["id"] for item in restored["workspace"]["course"]["stages"]},
        )
        self.assertTrue(restored["workspace"]["stage_results"])
        self.assertTrue(all(
            item["passed"]
            for item in restored["workspace"]["stage_results"].values()
        ))

    def test_mutation_does_not_corrupt_a_legitimate_ge_zero_comparison(self):
        # 合法写法里 index >= 0 很常见；候选正则若匹配到 ">=" 里的那个 ">"，
        # 会把它毁成 "index >= = 0" —— 一份编译不过的残骸，而且 _build_mutation
        # 会因为「判题不通过」把它当成有效故障收下。
        # 注：简报原夹具只有上界守卫（index >= 0 && index > size），负数索引会走到
        # result.begin() + index 的未定义行为，判题进程直接 double free 崩溃；补一行
        # 下界守卫让夹具本身 13/13 通过、且只在注入边界收紧后失败（见报告 Step 3b）。
        code = (
            '#include <vector>\n#include <stdexcept>\n'
            'std::vector<int> array_insert(std::vector<int> items, int index, int value) {\n'
            '  if (index >= 0 && index > (int)items.size()) throw std::out_of_range("越界");\n'
            '  if (index < 0) throw std::out_of_range("越界");\n'
            '  std::vector<int> result = items;\n'
            '  result.insert(result.begin() + index, value);\n'
            '  return result;\n'
            '}\n'
        )
        mutated, _meta = capability_service._build_mutation("1-1", code)
        result = capability_service._judge_exercise_code("1-1", mutated)
        self.assertIsNone(result.get("compile_error"), f"注入后的代码编译不过：\n{mutated}")
        self.assertFalse(result["passed"])

    def test_reference_solution_rejects_negative_index_without_crashing(self):
        # 1-1 有负数索引的用例。合法解必须**抛异常拦住它**，而不是走到
        # result.begin() + index 的未定义行为（实测会 double free / exit -6，
        # 被 compile_error 字段吞掉，看起来像"编译错误"）。
        result = capability_service._judge_exercise_code("1-1", self.correct_code())
        self.assertIsNone(result.get("compile_error"), f"参考解崩溃或编译失败：{result.get('compile_error')}")
        self.assertTrue(result["passed"], "参考解应 13/13 通过")

    def test_every_flagship_exercise_has_a_variant_scenario(self):
        from services.agent_lab_specs import FLAGSHIP_IDS

        missing = [
            exercise_id
            for exercise_id in sorted(FLAGSHIP_IDS)
            if capability_service._get_variant_spec(exercise_id) is None
        ]
        self.assertEqual(missing, [])

    def test_additional_variant_is_scored_by_private_cases(self):
        spec = capability_service._get_variant_spec("2-1")
        code = """
#include <vector>
#include <stdexcept>

static bool bst_check(const TreeNode* node, const TreeNode*& prev) {
  if (!node) return true;
  if (!bst_check(node->left, prev)) return false;
  if (prev && prev->value >= node->value) return false;
  prev = node;
  return bst_check(node->right, prev);
}

static void range_walk(const TreeNode* node, int low, int high, std::vector<int>& result) {
  if (!node) return;
  if (node->value > low) range_walk(node->left, low, high, result);
  if (low <= node->value && node->value <= high) result.push_back(node->value);
  if (node->value < high) range_walk(node->right, low, high, result);
}

std::vector<int> bst_range_values(TreeNode* tree, int low, int high) {
  if (low > high) throw std::invalid_argument("low 不能大于 high");
  const TreeNode* prev = nullptr;
  if (!bst_check(tree, prev)) throw std::invalid_argument("不满足二分搜索树性质");
  std::vector<int> result;
  range_walk(tree, low, high, result);
  return result;
}
"""
        result = capability_service._judge_variant_code(code, spec)
        self.assertTrue(result["passed"])
        self.assertEqual(result["passed_count"], result["total"])

    def test_variant_failure_reports_the_reason_to_the_student(self):
        # 变式判题走委托路径：`_run_judge` 的**原始行**里失败原因存在 `error` 键，
        # `_with_case_views` 只加一个顶层 `cases` 键、不改 `results`。
        # 若从 `detail` 取值，每个失败用例的 error 恒为 None——
        # 学生只看到「这条没过」看不到为什么，而**没有任何现有测试会变红**。
        good = VARIANT_REFERENCE_SOLUTIONS["1-1"]
        broken = good.replace(
            "interval[0] <= merged.back()[1]", "interval[0] < merged.back()[1]",
        )
        self.assertNotEqual(broken, good, "替换没生效：夹具已经不是原来那份解了")

        from services.agent_lab_variants import ADDITIONAL_VARIANT_SPECS
        outcome = capability_service._judge_variant_code(
            broken, ADDITIONAL_VARIANT_SPECS["1-1"],
        )
        self.assertFalse(outcome["passed"])
        failed = [item for item in outcome["results"] if not item["passed"]]
        self.assertTrue(failed, "这份解本该有用例不通过")
        for item in failed:
            self.assertTrue(
                item["error"],
                f"用例「{item['description']}」判失败了却没带原因：{item!r}",
            )
            self.assertIn("期望", item["error"])

    def test_failed_variant_remains_pending_and_unverified(self):
        session = capability_service.start_session(self.user_id, "1-1")
        conn = database.get_db()
        conn.execute(
            """UPDATE capability_sessions
               SET status = 'variant_pending', code_score = 100, defense_score = 35,
                   repair_score = 100, process_score = 60, report_json = '{}',
                   variant_scenario = '测试变式'
               WHERE id = ?""",
            (session["id"],),
        )
        conn.commit()
        conn.close()

        result = capability_service.submit_variant(
            self.user_id,
            session["id"],
            self.correct_code(),  # 未定义变式目标函数，因此得到低分
        )

        self.assertFalse(result["variant_passed"])
        self.assertFalse(result["variant_completed"])
        self.assertTrue(result["variant_submitted"])
        self.assertEqual(result["variant_score"], 0)
        self.assertEqual(result["status"], "variant_pending")
        self.assertFalse(result["verified"])

    def test_learning_events_are_persisted(self):
        session = capability_service.start_session(self.user_id, "1-1")
        recorded = capability_service.record_events(self.user_id, session["id"], [
            {"type": "edit", "payload": {"length": 120, "source": "solution.py"}},
            {"type": "hint", "payload": {"stage_id": "implementation", "level": 2}},
            {"type": "stage_check", "payload": {
                "stage_id": "implementation", "passed": False, "failed": 2,
            }},
        ])
        self.assertEqual(recorded["recorded"], 3)
        conn = database.get_db()
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM capability_events WHERE session_id = ?",
            (session["id"],),
        ).fetchone()["count"]
        conn.close()
        self.assertEqual(count, 4)


if __name__ == "__main__":
    unittest.main()
