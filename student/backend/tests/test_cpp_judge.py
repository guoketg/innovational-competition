"""C++ 判题执行路径的单测。

用一份合成 spec 覆盖机制本身，不依赖 1-1 的关卡内容——关卡内容由
test_judge_service.py 覆盖。这样判题器改坏了能立刻定位到是机制还是内容。
"""

import json
import unittest

import services.cpp_judge as cpp_judge
from services.cpp_judge import (
    CppContractError,
    _parse_case_lines,
    compile_cpp_only,
    run_cpp_judge,
)


SAMPLE_SPEC = {
    "language": "cpp",
    "target": "double_all",
    "cpp": {
        "signature": "std::vector<int> double_all(std::vector<int> items)",
        "includes": ["<vector>", "<stdexcept>"],
        "exception_map": {"out_of_range": "std::out_of_range"},
    },
    "cases": [
        {"description": "每个元素翻倍", "args": [[1, 2, 3]], "expected": [2, 4, 6]},
        {"description": "空容器", "args": [[]], "expected": []},
        {"description": "不得改动入参", "args": [[1, 2]], "expected": [2, 4], "immutable": True},
        {"description": "元素过多时拒绝", "args": [[1, 2, 3, 4]], "exception": "out_of_range"},
    ],
}

CORRECT = """
#include <vector>
#include <stdexcept>

std::vector<int> double_all(std::vector<int> items) {
  if (items.size() > 3) throw std::out_of_range("太长");
  std::vector<int> out;
  for (int item : items) out.push_back(item * 2);
  return out;
}
"""


def _run(code, total=4, timeout=6):
    return run_cpp_judge(code, SAMPLE_SPEC, total, timeout)


class CppJudgeTest(unittest.TestCase):
    def test_correct_solution_passes_every_case(self):
        result = _run(CORRECT)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["passed_count"], 4)
        self.assertIsNone(result["compile_error"])
        self.assertEqual([item["case_index"] for item in result["results"]], [1, 2, 3, 4])
        # 评测面板会在用例行尾显示「{duration_ms}ms」、`_persistable_stage_result`
        # 也会把它存进通过快照，所以 C++ 路径必须与 Python runner 一样逐条给时间。
        for item in result["results"]:
            self.assertIsInstance(item["duration_ms"], float)

    def test_wrong_value_reports_input_expected_and_actual(self):
        code = CORRECT.replace("item * 2", "item * 3")
        result = _run(code)
        self.assertFalse(result["passed"])
        first = result["results"][0]
        self.assertFalse(first["passed"])
        # 三段式报错是 student 面板「实际」列的取数来源，格式不能变
        self.assertIn("输入: [[1, 2, 3]]", first["error"])
        self.assertIn("期望: [2, 4, 6]", first["error"])
        self.assertIn("实际: [3, 6, 9]", first["error"])

    def test_wrong_exception_type_fails_the_boundary_case(self):
        code = CORRECT.replace("std::out_of_range", "std::logic_error")
        result = _run(code)
        self.assertFalse(result["passed"])
        boundary = result["results"][3]
        self.assertFalse(boundary["passed"])
        self.assertIn("必须抛出 out_of_range", boundary["error"])

    def test_syntax_error_returns_a_readable_compile_error(self):
        result = _run("std::vector<int> double_all(std::vector<int> items) { return ; }")
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"], [])
        self.assertIn("solution.cpp", result["compile_error"])

    def test_changing_the_declared_signature_fails_at_link_time(self):
        code = CORRECT.replace(
            "std::vector<int> double_all(std::vector<int> items)",
            "std::vector<int> double_all(std::vector<int>& items)",
        )
        result = _run(code)
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"], [])
        self.assertIn("undefined reference", result["compile_error"])

    def test_infinite_loop_hits_the_timeout(self):
        # 替换的是「整条循环语句」，不是循环头：只换头会把 out.push_back(item * 2);
        # 留在循环外，item 出作用域 → 编译错（'item' was not declared in this scope），
        # 根本跑不到超时。死循环必须是 for 的唯一循环体，且仍能编译。
        code = CORRECT.replace(
            "for (int item : items) out.push_back(item * 2);",
            "for (int item : items) while (true) {}",
        )
        result = _run(code, timeout=2)
        self.assertFalse(result["passed"])
        self.assertIn("超时", result["compile_error"])

    def test_undeclared_exception_token_is_a_server_side_error(self):
        broken = dict(SAMPLE_SPEC)
        broken["cases"] = [{"description": "越界", "args": [[1]], "exception": "value_error"}]
        with self.assertRaises(CppContractError):
            run_cpp_judge(CORRECT, broken, 1, 6)

    def test_banned_call_is_rejected_before_compiling(self):
        for source in (
            'int main() { return system("ls"); }',
            # 进程自杀类，与 Python 侧禁 exit/quit/SystemExit 对齐。少了它们，
            # 「打印伪造的 __CASE__ 行 + exit(0)」能让整份判题全绿。
            '#include <cstdlib>\nint f() { std::exit(0); return 0; }',
            '#include <cstdlib>\nint f() { std::atexit(nullptr); return 0; }',
            # terminate( 是第二轮审查复现的绕法：它把「早退」换成非零返回码。
            '#include <exception>\nint f() { std::terminate(); return 0; }',
            '#include <cstdlib>\nint f() { std::_Exit(0); return 0; }',
            # syscall( / dlsym( 是第三轮审查复现的绕法：绕开上面所有名字，直接发
            # 退出系统调用。它们是**正常**退出（returncode 0），结构性门管不着，
            # 所以只能靠这张名单。名单不是防线（见 cpp_policy_error 上面的注释），
            # 这两条挡的是「照着审查报告复现」的那类人，不是「下决心绕」的那类人。
            '#include <sys/syscall.h>\n#include <unistd.h>\nint f() { syscall(SYS_exit, 0); return 0; }',
            '#include <dlfcn.h>\nint f() { dlsym(RTLD_DEFAULT, "_exit"); return 0; }',
        ):
            with self.subTest(source=source):
                result = _run(source)
                self.assertFalse(result["passed"])
                self.assertIn("安全检查未通过", result["compile_error"])

    def test_the_reported_token_is_the_one_the_student_wrote(self):
        """子串匹配会先撞上短 token：`atexit(` 里含 `exit(`。

        拒绝了是对的，但文案点名 `exit` 会让学生在自己的代码里找不到那处调用。
        取命中项里最长的那个，报出来的就是他真写的名字。
        """
        self.assertIn("atexit", cpp_judge.cpp_policy_error("std::atexit(nullptr);"))
        self.assertIn("quick_exit", cpp_judge.cpp_policy_error("std::quick_exit(0);"))
        self.assertIn("terminate", cpp_judge.cpp_policy_error("std::terminate();"))

    def test_faking_results_by_exiting_early_cannot_pass(self):
        """审查复现过的作弊路径：自己打印一批 __CASE__ 行，然后 exit(0)。

        进程提前且**正常**退出（returncode 0），判题器自己的结果行一条都没来得及打，
        伪造行于是成了唯一的「事实」；而「没拿到结果就拒绝」那道兜底因为 returncode==0
        也不触发。所以它必须被策略挡在编译之前。

        伪造内容照真实期望写（学生能读到 args，猜出期望值不难），也就是说：**政策一旦
        漏掉 exit，这份伪造会让整关判为通过**——所以这条测试两个方向都能报警。
        """
        forgeries = []
        for index, item in enumerate(SAMPLE_SPEC["cases"], start=1):
            if item.get("exception"):
                body = ',"threw":"std::out_of_range"'
            else:
                body = ',"actual":' + json.dumps(item["expected"])
            forgeries.append(
                f'    std::cout << "__CASE__{{\\"i\\":{index}{body}}}" << std::endl;'
            )
        code = (
            "#include <iostream>\n#include <cstdlib>\n"
            "struct Forge { Forge() {\n"
            + "\n".join(forgeries)
            + "\n    std::exit(0); } };\nForge forge;\n"
        )
        result = _run(code)
        self.assertFalse(result["passed"])
        self.assertIn("安全检查未通过", result["compile_error"])

    def test_a_run_that_died_cannot_be_passed_off_as_a_finished_run(self):
        """第二轮审查复现的绕法：伪造**全部**结果行，然后让进程非正常退出。

        每条 index 恰好一行 ⇒ 「重复即伪造」不触发；它在 main 的用例循环开始前就死了
        ⇒ 真结果行一条都不存在；伪造行于是被逐条采信，整关判为通过（实测
        `passed=True, 4/4`，而学生的函数零次调用）。

        这条测试**故意用 `std::raise(SIGABRT)` 而不是 `std::terminate()`**：
        terminate 现在也在黑名单里，用它测就只测到黑名单，测不到门。而黑名单是会被
        漏掉的（这一轮就是），真正兜住的是结构性那条——脚手架每条用例都包在
        `catch (const <映射类型>&)` / `catch (const std::exception&)` / `catch (...)` 里，
        学生函数抛任何异常都不会让进程死，所以非零返回码只可能来自「进程被杀」，
        此时 stdout 上的任何内容都不构成证据。

        伪造内容照真实期望写；下面那个哑定义的 double_all 只为过链接（除了被 main
        调用一次以外什么都不做），好让进程真的死在构造函数里而不是链接期。
        """
        forgeries = []
        for index, item in enumerate(SAMPLE_SPEC["cases"], start=1):
            if item.get("exception"):
                body = ',\\"threw\\":\\"std::out_of_range\\"'
            else:
                body = ',\\"actual\\":' + json.dumps(item["expected"])
            forgeries.append(
                f'    std::cout << "__CASE__{{\\"i\\":{index}{body}}}" << std::endl;'
            )
        code = (
            "#include <iostream>\n#include <vector>\n#include <stdexcept>\n"
            "#include <csignal>\n"
            "struct Forge { Forge() {\n"
            + "\n".join(forgeries)
            + "\n    std::raise(SIGABRT); } };\nForge forge;\n"
            "std::vector<int> double_all(std::vector<int> items) { return items; }\n"
        )
        result = _run(code)
        self.assertFalse(result["passed"])
        self.assertEqual(result["passed_count"], 0)
        # 报的必须是「这一趟根本没跑完」而不是「某条用例答错了」——
        # 后者会让学生以为自己的函数被调用过、只是结果不对。
        self.assertIn("异常退出", result["compile_error"])
        self.assertEqual(result["results"], [])

    def test_case_lines_take_the_last_one_and_flag_duplicates(self):
        """解析器契约，两个不变量都钉在这里（这是它们唯一能被隔离观察的地方）。

        为什么要下沉到这一层：一旦注入判题行，那条用例必然出现两行，于是走的是
        「重复即判失败」那条路径——「取最后一条」在端到端层面已经观察不到了。
        取最后一条仍然不能改成取第一条：那是第二层，防的是「重复判定」将来被放宽。
        """
        stdout = (
            '__CASE__{"i":1,"actual":[1]}\n'
            "学生的调试输出，混在里面\n"
            '__CASE__{"i":1,"actual":[2]}\n'
            '__CASE__{"i":2,"actual":[3]}\n'
        )
        payloads, duplicated = _parse_case_lines(stdout)
        self.assertEqual(payloads[1]["actual"], [2])
        self.assertEqual(duplicated, {1})
        self.assertEqual(payloads[2]["actual"], [3])

    def test_a_repeated_forged_payload_fails_the_case(self):
        """重复伪造：在后续用例的调用里给已判完的用例补一行，必须判该用例失败。

        实测过这条路径真的能翻盘——伪造行硬编码 `i:1` 又写在函数体里，4 个用例各调用
        一次也就打 4 次，最后一次落在 case 1 真结果行之后，「取最后一条」就会选中它，
        case 1 被误判通过。脚手架每条用例只打一行，所以「重复」本身就是伪造的证据。

        （为了把这条与「取最后一条」那层分开：注入了判题行 ⇒ 该用例必然重复 ⇒ 失败。
        所以端到端这一层测的是「重复被抓住」，不是「取最后一条」。）
        """
        code = (
            "#include <iostream>\n#include <vector>\n#include <stdexcept>\n"
            "std::vector<int> double_all(std::vector<int> items) {\n"
            '  std::cout << "\\n__CASE__{\\"i\\":1,\\"actual\\":[2, 4, 6]}" << std::endl;\n'
            "  return std::vector<int>{0};\n"
            "}\n"
        )
        result = _run(code)
        self.assertFalse(result["passed"])
        self.assertFalse(result["results"][0]["passed"])
        self.assertIn("多次", result["results"][0]["error"])

    def test_compile_timeout_is_reported_as_a_compile_timeout(self):
        """编译阶段的超时不能被报成「运行超时（>6 秒）」——阶段指错了，秒数也是错的。

        把 COMPILE_TIMEOUT 临时调成 0.001 让编译必然超时，比真去构造一个病态模板
        （要耗 20 秒）可靠得多。
        """
        original = cpp_judge.COMPILE_TIMEOUT
        cpp_judge.COMPILE_TIMEOUT = 0.001
        try:
            result = _run(CORRECT)
        finally:
            cpp_judge.COMPILE_TIMEOUT = original
        self.assertFalse(result["passed"])
        self.assertIn("编译超时", result["compile_error"])
        self.assertNotIn("运行超时", result["compile_error"])

    def test_compile_cpp_only_accepts_a_syntax_clean_file(self):
        self.assertTrue(compile_cpp_only("int f() { return 1; }")["ok"])

    def test_compile_cpp_only_rejects_a_syntax_error_without_linking(self):
        # 只做到「能编译」，不链接：被调用的函数**有声明、没定义**时必须判为通过——
        # 那要链接才会失败，而这一步不做链接。
        result = compile_cpp_only("int g(); int f() { return 1; } int main() { return g(); }")
        self.assertTrue(result["ok"], result)
        self.assertFalse(compile_cpp_only("int f( { return 1; }")["ok"])
        # 但 `-fsyntax-only` 仍做完整的名字解析，未声明的调用是错误（C++ 没有隐式函数声明）。
        # 这是想要的行为：它判的就是 solution.cpp 这一个编译单元，与判题器真正编译它时一致。
        self.assertFalse(compile_cpp_only("int f() { return g(); }")["ok"])


if __name__ == "__main__":
    unittest.main()
