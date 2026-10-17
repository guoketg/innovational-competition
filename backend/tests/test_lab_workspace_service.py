import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk

from services import lab_workspace_service as service
from services.judge_service import SPECS, load_flagship_exercises, public_cases
from services.agent_lab_specs import lab_repair_file, lab_solution_file


def _load_reference_solutions() -> dict:
    """复用 scripts/verify_lab_content.py 的参考答案，避免两处各写一份。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_lab_content.py"
    spec = importlib.util.spec_from_file_location("verify_lab_content", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.REFERENCE_SOLUTIONS


REFERENCE_SOLUTIONS = _load_reference_solutions()

ALL_EXERCISE_IDS = [item["id"] for item in load_flagship_exercises()]
CORRECT_ARRAY_INSERT = REFERENCE_SOLUTIONS["1-1"]
# 1-1 已经改成 C++：文件名不再写死，测试也跟着关卡声明走，
# 否则「1-1 改语言」这件事会在测试里留下一串需要手工同步的字面量。
SOLUTION = lab_solution_file("1-1")

WRONG_APPEND = '''
#include <vector>
#include <stdexcept>

// 编译得过，但把 value 一律追加到末尾：中间/头部插入全错。
std::vector<int> array_insert(std::vector<int> items, int index, int value) {
  std::vector<int> result = items;
  result.push_back(value);
  return result;
}
'''


class LabWorkspaceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(service, "WORKSPACE_ROOT", Path(self.temp.name))
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def test_streamed_tool_arguments_are_reconstructed_before_execution(self):
        first = AIMessageChunk(
            content="",
            tool_call_chunks=[{
                "name": "read_project_file",
                "args": '{"path":"sol',
                "id": "call-read-1",
                "index": 0,
            }],
        )
        second = AIMessageChunk(
            content="",
            tool_call_chunks=[{
                "name": None,
                "args": 'ution.py"}',
                "id": None,
                "index": 0,
            }],
        )

        calls = service._normalized_lab_tool_calls(first + second)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "read_project_file")
        self.assertEqual(calls[0]["args"], {"path": "solution.py"})
        self.assertEqual(calls[0]["id"], "call-read-1")

    def test_workspace_starts_as_a_single_file_project(self):
        workspace = service.get_workspace(7, "1-1")
        self.assertEqual(workspace["project_name"], "dsa-lab-1-1")
        # PTA 形态：一个 README 加一个带骨架的 solution.cpp，没有终端、没有 .venv。
        self.assertEqual(
            {item["path"] for item in workspace["files"]},
            {"README.md", SOLUTION},
        )

    def test_workspace_ships_a_runnable_skeleton(self):
        workspace = service.get_workspace(7, "1-1")
        files = {item["path"]: item["content"] for item in workspace["files"]}

        # structure / first_llm_call 两个阶段都假定「打开 solution.cpp 就能看到
        # 返回值契约」，骨架缺失会让这两处判定同时失去依据。
        self.assertIn("std::vector<int> array_insert", files[SOLUTION])
        self.assertIn("std::logic_error", files[SOLUTION])

    def test_all_labs_share_one_single_file_stage_table(self):
        # 13 关全部 framework=Python 标准库、packages=[]，因此建虚拟环境 /
        # 声明依赖 / 接回可运行应用三个阶段全是空转，不分轨道统一删除。
        for exercise_id in ALL_EXERCISE_IDS:
            with self.subTest(exercise_id=exercise_id):
                course = service._course(exercise_id)
                self.assertEqual(course["project_files"], [lab_solution_file(exercise_id)])
                stage_ids = [item["id"] for item in course["stages"]]
                for removed in ("environment", "dependencies", "integration"):
                    self.assertNotIn(removed, stage_ids)
                self.assertEqual(stage_ids[:2], ["doc_intro", "structure"])
                self.assertEqual(stage_ids[-1], "acceptance")

    def test_no_stage_asks_the_student_to_use_a_terminal(self):
        for exercise_id in ALL_EXERCISE_IDS:
            with self.subTest(exercise_id=exercise_id):
                course = service._course(exercise_id)
                for stage in course["stages"]:
                    text = " ".join([
                        str(stage.get("id", "")),
                        str(stage.get("instruction", "")),
                        str(stage.get("command", "")),
                        " ".join(str(item) for item in stage.get("checks", [])),
                        " ".join(str(hint.get("text", "")) for hint in stage.get("hints", [])),
                    ])
                    for banned in ("终端", "terminal", "pip install", ".venv", "requirements.txt"):
                        self.assertNotIn(banned, text, f"{exercise_id}/{stage['id']} 仍提到 {banned}")

    def test_workspace_exposes_guided_learning_contract(self):
        course = service.get_workspace(7, "1-1")["course"]

        self.assertIn("示例输入", course["input_output"])
        self.assertIn("原容器保持不变", course["acceptance"])
        self.assertIn("顺序表", course["skills"])
        self.assertTrue(course["prerequisites"])
        implementation = next(item for item in course["stages"] if item["id"] == "implementation")
        self.assertEqual(implementation["target_file"], SOLUTION)
        self.assertGreaterEqual(len(implementation["micro_steps"]), 3)
        self.assertEqual(implementation["hints"][0]["level"], 1)
        self.assertGreaterEqual(len(implementation["hints"]), 3)

    def test_course_exposes_public_samples_but_not_private_cases(self):
        course = service._course("1-1")
        samples = course["samples"]

        self.assertEqual(len(samples), len(public_cases("1-1")))
        self.assertGreaterEqual(len(samples), 2)
        for sample in samples:
            self.assertEqual(set(sample), {"description", "input", "expected"})
            # 期望结果要展示，否则学生无法照着题面自测
            self.assertTrue(sample["expected"])

    def test_public_samples_never_cover_every_private_case(self):
        # 公开样例只是题面里的示例。任何一关若把全部考点都标成公开，
        # 自测就等于提前交卷，隐藏用例必须始终存在。
        for exercise_id in ALL_EXERCISE_IDS:
            with self.subTest(exercise_id=exercise_id):
                total = len(SPECS[exercise_id].get("cases") or [])
                hidden = total - len(public_cases(exercise_id))
                self.assertGreater(hidden, 0, f"{exercise_id} 没有隐藏用例")
                self.assertGreaterEqual(total, 4)

    def test_run_samples_executes_only_the_public_cases(self):
        service.get_workspace(7, "1-1")
        service.save_file(7, "1-1", SOLUTION, CORRECT_ARRAY_INSERT)

        result = service.run_samples(7, "1-1")

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["judge_mode"], "public_samples")
        self.assertEqual(result["total"], len(public_cases("1-1")))
        self.assertLess(result["total"], len(SPECS["1-1"]["cases"]))
        self.assertEqual(
            set(result["cases"][0]),
            {
                "description", "input", "expected", "actual", "passed",
                "detail", "category", "next_action", "duration_ms",
            },
        )

    def test_submit_judge_returns_the_same_case_shape_as_self_test(self):
        # 评测面板只有一套表格渲染代码，两种模式的行结构必须一致，
        # 否则「提交评测」后表格会突然少列或多列。
        service.get_workspace(7, "1-1")
        service.save_file(7, "1-1", SOLUTION, CORRECT_ARRAY_INSERT)

        samples = service.run_samples(7, "1-1")
        judged = service.submit_judge(7, "1-1")

        self.assertEqual(set(judged["cases"][0]), set(samples["cases"][0]))
        self.assertEqual(judged["judge_mode"], "server_private_cases")
        # 正式判题要覆盖自测没有的那批隐藏用例
        self.assertGreater(judged["total"], samples["total"])
        self.assertTrue(judged["passed"], judged)

    def test_submit_judge_upgrades_a_failure_into_an_actionable_row(self):
        service.get_workspace(7, "1-1")
        service.save_file(
            7, "1-1", SOLUTION,
            WRONG_APPEND,
        )

        judged = service.submit_judge(7, "1-1")
        failed = [item for item in judged["cases"] if not item["passed"]]

        self.assertFalse(judged["passed"])
        self.assertTrue(failed)
        row = failed[0]
        self.assertTrue(row["expected"] and row["actual"])
        self.assertNotEqual(row["expected"], row["actual"])
        self.assertTrue(row["category"])
        self.assertTrue(row["next_action"])

    def test_run_samples_reports_expected_and_actual_side_by_side(self):
        service.get_workspace(7, "1-1")
        service.save_file(
            7, "1-1", SOLUTION,
            WRONG_APPEND,
        )

        result = service.run_samples(7, "1-1")

        self.assertFalse(result["passed"])
        failed = [item for item in result["cases"] if not item["passed"]]
        self.assertTrue(failed)
        # 失败用例必须同时给出期望与实际，否则学生看不到差在哪
        self.assertTrue(failed[0]["expected"])
        self.assertTrue(failed[0]["actual"])
        self.assertNotEqual(failed[0]["expected"], failed[0]["actual"])

    def test_run_samples_refuses_when_solution_is_missing(self):
        service.get_workspace(7, "1-1")
        service.delete_file(7, "1-1", SOLUTION)

        with self.assertRaises(ValueError) as ctx:
            service.run_samples(7, "1-1")

        self.assertIn(SOLUTION, str(ctx.exception))

    def test_run_samples_records_the_run_for_the_warmup_stage(self):
        service.get_workspace(7, "1-1")
        service.save_file(7, "1-1", SOLUTION, CORRECT_ARRAY_INSERT)

        before = service.check_stage(7, "1-1", "first_llm_call")
        ran = next(item for item in before["checks"] if item["label"] == "已运行过一次自测")
        self.assertFalse(ran["passed"])

        service.run_samples(7, "1-1")

        after = service.check_stage(7, "1-1", "first_llm_call")
        ran = next(item for item in after["checks"] if item["label"] == "已运行过一次自测")
        self.assertTrue(ran["passed"], after)

    def test_first_llm_call_stage_accepts_a_rough_warmup_implementation(self):
        service.get_workspace(7, "1-1")
        # 热身阶段只要求「动过骨架 + 跑过一次自测」，不要求真的做对
        service.save_file(
            7, "1-1", SOLUTION,
            WRONG_APPEND,
        )
        service.run_samples(7, "1-1")

        result = service.check_stage(7, "1-1", "first_llm_call")

        self.assertTrue(result["passed"], result)
        self.assertIn("first_llm_call", result["completed_stages"])

    def test_failed_case_feedback_contains_learning_next_action(self):
        feedback = service._judge_case_feedback({
            "compile_error": None,
            "results": [
                {
                    "case_index": 1,
                    "description": "拒绝空系统提示",
                    "passed": False,
                    "error": "该非法输入必须抛出 ValueError",
                }
            ],
        })

        self.assertEqual(feedback[0]["category"], "输入边界")
        self.assertIn("检查", feedback[0]["next_action"])

    def test_checker_reports_a_link_error_when_the_target_is_missing(self):
        service.get_workspace(7, "1-1")
        # 编译单元检查能过（语法没问题），但目标函数没定义 → 链接失败。
        service.save_file(7, "1-1", SOLUTION, "int something_else() { return 1; }\n")
        result = service.check_stage(7, "1-1", "implementation")
        self.assertFalse(result["passed"])
        link = next(item for item in result["checks"] if item["label"] == "编译与链接")
        self.assertFalse(link["passed"])
        self.assertIn("array_insert", link["detail"])

    def test_implementation_stage_rejects_a_function_with_no_behavior(self):
        service.get_workspace(7, "1-1")
        for body in (
            '  throw std::logic_error("请实现");',
            "  return {};",
        ):
            with self.subTest(body=body):
                service.save_file(
                    7, "1-1", SOLUTION,
                    "#include <vector>\n#include <stdexcept>\n#include <string>\n\n"
                    "std::vector<int> array_insert(std::vector<int> items, int index, int value) {\n"
                    f"{body}\n}}\n",
                )

                result = service.check_stage(7, "1-1", "implementation")

                self.assertFalse(result["passed"])
                behavior = next(item for item in result["checks"] if item["label"] == "核心函数行为")
                self.assertFalse(behavior["passed"])
                self.assertNotIn("implementation", result["completed_stages"])

    def test_implementation_stage_requires_all_business_scenarios(self):
        service.get_workspace(7, "1-1")
        service.save_file(7, "1-1", SOLUTION, CORRECT_ARRAY_INSERT)

        result = service.check_stage(7, "1-1", "implementation")

        self.assertTrue(result["passed"], result)
        behavior = next(item for item in result["checks"] if item["label"] == "核心函数行为")
        self.assertRegex(behavior["detail"], r"通过 \d+/\d+ 个业务场景")
        self.assertGreaterEqual(len(behavior["cases"]), 9)
        self.assertIn("implementation", result["completed_stages"])

    def test_agent_mode_tools_read_files_and_sample_results(self):
        service.get_workspace(7, "1-1")
        tool_names = {
            item["function"]["name"]
            for item in service._lab_tool_schemas(allow_writes=True)
        }
        self.assertIn("write_project_file", tool_names)
        self.assertIn("get_sample_run_result", tool_names)
        # 没有终端了，助手不该再拿到任何执行命令的工具
        self.assertNotIn("run_terminal_command", tool_names)

        written = service._execute_lab_tool(
            "write_project_file",
            {"path": "src/agent_created.py", "content": "print('agent-created')\n"},
            7,
            "1-1",
        )
        observed = service._execute_lab_tool("get_sample_run_result", {}, 7, "1-1")

        self.assertIn("已写入", written)
        self.assertIn("公开样例自测", observed)
        self.assertIn("在中间插入元素", observed)

    def test_sample_result_tool_reports_failing_cases_without_leaking_private_cases(self):
        service.get_workspace(7, "1-1")
        service.save_file(7, "1-1", SOLUTION, CORRECT_ARRAY_INSERT)

        observed = service._execute_lab_tool("get_sample_run_result", {}, 7, "1-1")

        public_labels = {item["description"] for item in public_cases("1-1")}
        private_labels = {
            str(item.get("description"))
            for item in SPECS["1-1"]["cases"]
            if str(item.get("description")) not in public_labels
        }
        for label in private_labels:
            self.assertNotIn(label, observed)

    def test_explorer_can_rename_duplicate_and_delete_entries(self):
        service.get_workspace(7, "1-1")
        service.save_file(7, "1-1", "src/tool.py", "print('ok')\n")
        moved = service.move_entry(7, "1-1", "src/tool.py", "src/main.py")
        self.assertTrue(moved["moved"])
        copied = service.duplicate_entry(7, "1-1", "src/main.py", "src/main-copy.py")
        self.assertTrue(copied["duplicated"])
        deleted = service.delete_entry(7, "1-1", "src/main-copy.py")
        self.assertTrue(deleted["deleted"])
        self.assertFalse(service._root(7, "1-1").joinpath("src/main-copy.py").exists())

    def test_progress_overview_uses_the_same_stage_state_as_workspace(self):
        service.get_workspace(7, "1-1")
        root = service._root(7, "1-1")
        service._write_state(root, {"completed_stages": ["structure", "environment"], "commands": []})
        overview = service.get_progress_overview(7)
        # environment 已不属于任何一关（13 关统一去掉了工程化阶段）。
        # 读取路径必须按当前课程过滤，否则前端会显示 8/5 这种超过总数的进度。
        self.assertEqual(overview["1-1"]["completed_stages"], ["structure"])
        self.assertEqual(overview["1-1"]["total_stages"], len(service._course("1-1")["stages"]))
        self.assertEqual(overview["1-1"]["total_stages"], 5)
        self.assertNotIn("virtual_env", overview["1-1"])

    def test_passed_state_restores_project_and_each_stage_result(self):
        service.get_workspace(7, "1-1")
        service.save_file(7, "1-1", SOLUTION, CORRECT_ARRAY_INSERT)
        service.save_file(7, "1-1", ".env", "DEEPSEEK_API_KEY=keep-local-secret\n")
        root = service._root(7, "1-1")
        course = service._course("1-1")
        passed_results = service._legacy_passed_stage_results(course)
        state = service._read_state(root)
        state.update({
            "acceptance_ever_passed": True,
            "passed_solution_code": CORRECT_ARRAY_INSERT,
            "passed_project_files": service._passed_project_snapshot(root),
            "passed_stage_results": passed_results,
        })
        service._write_state(root, state)

        service.save_file(7, "1-1", SOLUTION, '#include <vector>\n#include <stdexcept>\n#include <string>\n\nstd::vector<int> array_insert(std::vector<int> items, int index, int value) { throw std::logic_error("未实现"); }\n')
        service.save_file(7, "1-1", "VARIANT_TASK.md", "old variant\n")
        service.save_file(7, "1-1", "scratch.txt", "temporary\n")

        restored = service.apply_project_state(
            7,
            "1-1",
            "passed",
            solution_code=CORRECT_ARRAY_INSERT,
        )
        files = {item["path"]: item["content"] for item in restored["files"]}

        self.assertEqual(files[SOLUTION], CORRECT_ARRAY_INSERT)
        self.assertNotIn("VARIANT_TASK.md", files)
        self.assertEqual(files["scratch.txt"], "temporary\n")
        self.assertIn("DEEPSEEK_API_KEY=keep-local-secret", files[".env"])
        self.assertEqual(
            set(restored["completed_stages"]),
            {item["id"] for item in course["stages"]},
        )
        self.assertEqual(set(restored["stage_results"]), set(restored["completed_stages"]))
        self.assertTrue(all(item["passed"] for item in restored["stage_results"].values()))
        implementation = restored["stage_results"]["implementation"]
        business_check = next(
            item for item in implementation["checks"]
            if "业务测试点" in item["label"] or item["label"] == "核心函数行为"
        )
        self.assertGreaterEqual(len(business_check["cases"]), 9)
        self.assertTrue(all(item["passed"] for item in business_check["cases"]))

    def test_legacy_pass_record_is_upgraded_to_a_single_file_project(self):
        service.get_workspace(7, "1-1")
        root = service._root(7, "1-1")
        state = service._read_state(root)
        state.update({
            "acceptance_ever_passed": True,
            "passed_solution_code": CORRECT_ARRAY_INSERT,
            # 旧快照里可能只有 README；单文件模式下不再补 app.py / requirements.txt
            "passed_project_files": {"README.md": "# old snapshot\n"},
            "passed_stage_results": service._legacy_passed_stage_results(
                service._course("1-1"),
            ),
        })
        service._write_state(root, state)

        restored = service.apply_project_state(
            7,
            "1-1",
            "passed",
            solution_code=CORRECT_ARRAY_INSERT,
        )
        files = {item["path"]: item["content"] for item in restored["files"]}

        self.assertEqual(files[SOLUTION], CORRECT_ARRAY_INSERT)
        self.assertNotIn("app.py", files)
        self.assertNotIn("requirements.txt", files)
        self.assertNotIn(".gitignore", files)

        implementation = restored["stage_results"]["implementation"]
        business_check = next(
            item for item in implementation["checks"]
            if "业务测试点" in item["label"] or item["label"] == "核心函数行为"
        )
        self.assertGreaterEqual(len(business_check["cases"]), 9)

    def test_reset_keeps_local_env_and_drops_legacy_project_files(self):
        service.get_workspace(7, "1-1")
        root = service._root(7, "1-1")
        service.save_file(7, "1-1", ".env", "LLM_API_KEY=local-only\n")
        # 旧课程遗留物：虚拟环境与 app.py 在单文件模式下都已无意义
        (root / ".venv").mkdir(parents=True, exist_ok=True)
        (root / ".venv" / "pyvenv.cfg").write_text("version = 3.11\n", encoding="utf-8")
        service.save_file(7, "1-1", "app.py", "print('legacy')\n")
        service.save_file(7, "1-1", "scratch.py", "print('remove me')\n")

        reset = service.get_workspace(7, "1-1", reset=True)
        files = {item["path"]: item["content"] for item in reset["files"]}

        self.assertIn(".env", files)
        self.assertIn("README.md", files)
        self.assertIn(SOLUTION, files)
        self.assertNotIn("scratch.py", files)
        self.assertNotIn("app.py", files)
        self.assertFalse((root / ".venv").exists())

    def test_tutor_code_snippets_follow_the_lab_language(self):
        # C++ 关卡：导师能看到 solution.cpp，看不到非文本的 notes.bin。
        cpp_snippets = service._tutor_code_snippets(
            [
                {"path": "solution.cpp", "content": "std::vector<int> array_insert() {}\n"},
                {"path": "README.md", "content": "# 1-1\n"},
                {"path": "notes.bin", "content": "\x00\x01"},
            ],
            "solution.cpp", "agent", "",
        )
        joined_cpp = "\n".join(cpp_snippets)
        self.assertIn("solution.cpp", joined_cpp)
        self.assertNotIn("notes.bin", joined_cpp)

        # Python 关卡：行为逐字节不变——含 solution.py 与 README.md，不含 data.json。
        py_snippets = service._tutor_code_snippets(
            [
                {"path": "solution.py", "content": "def array_insert():\n    return []\n"},
                {"path": "README.md", "content": "# 1-1\n"},
                {"path": "data.json", "content": "{}"},
            ],
            "solution.py", "agent", "",
        )
        joined_py = "\n".join(py_snippets)
        self.assertIn("solution.py", joined_py)
        self.assertIn("README.md", joined_py)
        self.assertNotIn("data.json", joined_py)


if __name__ == "__main__":
    unittest.main()
