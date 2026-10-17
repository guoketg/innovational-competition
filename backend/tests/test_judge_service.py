"""Project-lab private judge regression and bypass tests."""

import unittest

from services.judge_service import get_flagship_exercise, judge_submission


# 1-1「实现顺序表插入」的 C++ 参考答案：值语义 + 下标边界。
CORRECT_SOLUTION = '''
#include <vector>
#include <stdexcept>
#include <string>

std::vector<int> array_insert(std::vector<int> items, int index, int value) {
  if (index < 0 || index > static_cast<int>(items.size())) {
    throw std::out_of_range("index 越界：合法范围是 0..size()");
  }
  std::vector<int> result = items;
  result.insert(result.begin() + index, value);
  return result;
}
'''

# 空骨架：解题时学生打开 solution.cpp 看到的就是它。
STARTER_SOLUTION = get_flagship_exercise("1-1")["starter_code"]

# 1-3「用栈求值逆波兰表达式」的 C++ 参考答案：栈 + 向零截断的整数除法。
CORRECT_RPN_SOLUTION = '''
#include <vector>
#include <string>
#include <stdexcept>

int eval_rpn(std::vector<std::string> tokens) {
  std::vector<int> stack;
  for (const std::string& token : tokens) {
    if (token == "+" || token == "-" || token == "*" || token == "/") {
      if (stack.size() < 2) throw std::invalid_argument("操作数不足");
      int right = stack.back(); stack.pop_back();
      int left = stack.back(); stack.pop_back();
      if (token == "+") stack.push_back(left + right);
      else if (token == "-") stack.push_back(left - right);
      else if (token == "*") stack.push_back(left * right);
      else {
        if (right == 0) throw std::invalid_argument("除数不能为 0");
        stack.push_back(left / right);
      }
    } else {
      std::size_t pos = 0;
      int value;
      try {
        value = std::stoi(token, &pos);
      } catch (const std::exception&) {
        throw std::invalid_argument("非法数字 token");
      }
      if (pos != token.size()) throw std::invalid_argument("非法数字 token");
      stack.push_back(value);
    }
  }
  if (stack.size() != 1) throw std::invalid_argument("表达式非法");
  return stack[0];
}
'''


class ProjectLabJudgeTest(unittest.TestCase):
    def test_correct_solution_passes_every_private_scenario(self):
        result = judge_submission("1-1", CORRECT_SOLUTION)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["passed_count"], 13)
        self.assertEqual(result["total"], 13)
        self.assertEqual(result["judge_mode"], "server_private_cases")

    def test_starter_logic_error_fails_every_scenario(self):
        # 空骨架抛的是 std::logic_error，与任何用例的期望异常都不匹配，
        # 因此稳定 0/13——学生不会一进来就白捡两条通过。
        result = judge_submission("1-1", STARTER_SOLUTION)
        self.assertFalse(result["passed"])
        self.assertEqual(result["passed_count"], 0)
        self.assertEqual(result["total"], 13)
        # 必须证明「0/13 是因为逻辑不对」，而不是「因为骨架压根编译不过」——
        # 后者同样给出 passed=False / 0/13，于是这条测试会在骨架没正确下发时
        # （比如 JSON 没拷进命名卷、还是旧的 Python 骨架）照样变绿。
        # compile_error 非空 = 这次失败是编译/链接期失败，本测试没测到想测的东西。
        self.assertIsNone(result["compile_error"], result)

    def test_rpn_evaluator_passes_every_private_scenario(self):
        result = judge_submission("1-3", CORRECT_RPN_SOLUTION)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["passed_count"], 18)

    def test_a_program_with_its_own_main_cannot_bypass_the_judge(self):
        result = judge_submission(
            "1-1",
            '#include <iostream>\nint main() { std::cout << "[PASS]"; return 0; }\n',
        )
        self.assertFalse(result["passed"])
        self.assertTrue(result["compile_error"])

    def test_banned_calls_are_rejected(self):
        # 三条都要测：上面那张表说黑名单是 system( / popen( / fork( 三条
        # （设计文档第 110 行），只测前两条等于有一条分支没有任何测试走过。
        for source in (
            'int f() { return system("ls"); }',
            'int f() { FILE* p = popen("ls", "r"); return p != 0; }',
            '#include <unistd.h>\nint f() { pid_t pid = fork(); return pid == 0; }',
        ):
            with self.subTest(source=source):
                result = judge_submission("1-1", source)
                self.assertFalse(result["passed"])
                self.assertIn("安全检查未通过", result["compile_error"])

    def test_off_by_one_boundary_rejects_appending_at_the_end(self):
        """把 index > size() 收紧成 >=，末尾追加会被误判为越界。"""
        wrong = CORRECT_SOLUTION.replace(
            "index > static_cast<int>(items.size())",
            "index >= static_cast<int>(items.size())",
        )
        self.assertNotEqual(wrong, CORRECT_SOLUTION)
        result = judge_submission("1-1", wrong)
        self.assertFalse(result["passed"])
        failed = [item["description"] for item in result["results"] if not item["passed"]]
        self.assertIn("在末尾插入元素", failed)

    def test_changing_the_declared_signature_fails_to_link(self):
        """按值签名是判题声明的。学生改成引用后 main.cpp 里那个原型就没有定义，
        链接期就会失败——这是 C++ 下「签名不许改」的真正执行者。"""
        wrong = CORRECT_SOLUTION.replace(
            "std::vector<int> items, int index",
            "std::vector<int>& items, int index",
        )
        self.assertNotEqual(wrong, CORRECT_SOLUTION)
        result = judge_submission("1-1", wrong)
        self.assertFalse(result["passed"])
        self.assertIn("undefined reference", result["compile_error"])

    def test_wrong_exception_type_fails_the_boundary_case(self):
        wrong = CORRECT_SOLUTION.replace("std::out_of_range", "std::runtime_error")
        result = judge_submission("1-1", wrong)
        self.assertFalse(result["passed"])
        failed = [item["description"] for item in result["results"] if not item["passed"]]
        self.assertIn("拒绝越界索引", failed)


if __name__ == "__main__":
    unittest.main()
