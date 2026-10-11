# 关卡 1-1 改用 C++ 试点 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把学生端编程实验室的第 1-1 关「实现顺序表插入」从 Python 完整改成 C++（题面、骨架、参考解、13 条判题用例、故障修复、变式迁移、编辑器），并让判题执行契约支持按关声明语言，其余 12 关保持 Python 不受影响。

**Architecture:** 判题器新增一条 C++ 执行路径：Python 侧按关卡声明的签名生成 `main.cpp`，与学生写的 `solution.cpp` 分两个编译单元一起 `g++` 编译；`main.cpp` 逐条用例调用学生函数，把结果打成 `__CASE__{...}` 行回传；**比对、归类、渲染仍然全部由 Python 完成**，复用现有 `_case_views` / `_sample_actual` / `feedback_guidance` 管线。`language` 成为每关在 `agent_lab_specs.py` 里的属性（缺省 `python`），工作区的文件名、阶段检查文案、提示词都从它派生。

**Tech Stack:** Python 3.11 + FastAPI（后端）、g++ / `-std=c++17`（`python:3.11-slim`，当前基于 Debian 13 trixie，g++ 为 14.x）、Vue 3 + CodeMirror 6 + `@codemirror/lang-cpp`（前端）、Docker Compose、Playwright MCP（E2E）。

**Spec:** `student/docs/superpowers/specs/2026-09-19-lab-1-1-cpp-pilot-design.md`

## Global Constraints

- **绝对禁止把任何真实 API Key 写进代码文件**（`.py` / `.js` / `.vue` / `.json` / `.yml` / `.env`），也不许用硬编码默认 Key 兜底；未配置 = 功能不可用 + 明确提示。测试 Key 只能通过浏览器 UI 输入。
- **本仓库不是 git 仓库**（`git rev-parse` 报 `not a git repository`）。因此每个任务用「跑验证 + 记录关键输出」代替提交步骤，不要写 `git commit`。
- **本机（Windows）没有 C++ 编译器**（`g++`/`gcc`/`clang++` 全部 `NOT FOUND`）。所有 C++ 相关的单测与脚本**必须在后端容器里跑**：先 `docker compose up -d --build`，再 `MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest ...`。纯 Python 的单测本机也能跑，但统一在容器里跑更省事。
- `docker compose up -d --build` **必须在仓库根目录 `D:\code\innovational-competition` 执行**；在 `student/` 下跑会建出平行 project 且改动不生效。
- `backend/docker-entrypoint.sh` 必须保持 **LF** 行尾符（本计划不碰它，但 `docker compose up` 后要确认容器起得来）。
- **改关卡内容必须同时部署 `backend/data/flagship_exercises.json`**：只部署代码会让内容校验全过而页面仍是旧内容。
- **非空工作区的 README / 骨架永不刷新**。验证阶段必须重置工作区（`get_workspace(..., reset=True)` 或删掉 `user-<id>/1-1` 让它重新 seed），否则会看到旧文件而误判成改动没生效。
- 判题全链路是 **generic 模式**：`agent_lab_specs.py` 里 `mode=tool_call/tool_plan/checkpoint/sqlalchemy_query` 已废弃，1-1 只用 `expected` / `exception` / `immutable` 三种用例形态。
- **不碰**：`backend/data/dataset/module_0X_*.json`、`exercises_processed.json`、RAG 向量库、`backend/data/tutorial_seed.json`（44 篇 runoob 教程本次不动）。
- 生产环境是 `/opt/edu-ta`，**绝不对线上跑 `docker compose down -v`**（Key 加密文件会丢）。
- `nginx-analysis/rexec.js` 里存着 `47.109.61.211` 的 root 口令，**只能由脚本在运行时从该文件读取**，不得打印、回显或复制到任何其它文件。
- 编辑器与评测面板的既有约定不变：`.judge-tabs button` / `.judge-action` / `.judge-case-list li` / `.judge-log-line` / `.cm-editor`；`submitJudge` 后的主结果不能被日志顶掉（`pushJudge(text, type, { focus: false })`）。

---

## 文件结构总览

| 文件 | 职责 | 动作 |
|---|---|---|
| `backend/services/cpp_judge.py` | **新建**。C++ 判题的完整实现：签名解析 → 生成 `main.cpp` → 编译 → 运行 → 解析 `__CASE__` 行 → 比对成与 Python runner 同构的结果行。以及只编译不链接的 `compile_cpp_only()`。 | 新建 |
| `backend/services/judge_service.py` | 判题入口。`_run_judge` 按 `spec["language"]` 分发到 C++ 路径。 | 改 `_run_judge` |
| `backend/services/agent_lab_specs.py` | 关卡声明之源：`SPECS` 用例 + `language`/`cpp` 契约；新增语言查询助手。 | 改 |
| `backend/services/lab_workspace_service.py` | 工作区：文件名、阶段表、README、检查逻辑、提示词全部按语言派生。 | 改（约 30 处） |
| `backend/services/agent_lab_faults.py` | 1-1 的注入故障改 C++ 正则与文案。 | 改 |
| `backend/services/capability_service.py` | 变式判题改为委派新判题器（删掉第三份 runner）；AST 兜底改写器按语言跳过。 | 改 |
| `backend/services/agent_lab_variants.py` | 1-1 变式 `insert_interval` 改 C++ 契约与用例。 | 改 |
| `backend/scripts/verify_lab_content.py` | `REF_1_1` 改 C++；`run_stage_checks` 的 `project_files` 断言按语言。 | 改 |
| `backend/scripts/verify_lab_faults.py` | 第 52 行的 `ast.parse(mutated)` 对 C++ 恒抛 `SyntaxError`，按语言分流到真正的编译器。**验证脚本，但同 `verify_lab_content.py` 一并部署**（见 Task 9 的 Ruling 55）。 | 改（Task 5，见 Ruling 55） |
| `backend/data/flagship_exercises.json` | 1-1 的题面 / 输入输出 / 骨架 / 步骤 / 验收 / 技能 / 前置。 | 改 1-1 条目 |
| `backend/Dockerfile` | 装 `g++`。 | 改 |
| `backend/tests/test_cpp_judge.py` | **新建**。C++ 判题路径的单测（合成 spec，不依赖关卡内容）。 | 新建 |
| `backend/tests/test_judge_service.py` | 1-1 的判题用例改 C++。 | 改 |
| `backend/tests/test_lab_workspace_service.py` | 1-1 夹具改 C++，注解标签、文件名、错误用例全部对齐。 | 改 |
| `backend/tests/test_capability_service.py` | 1-1 的文件名与变式断言改 C++。 | 改 |
| `backend/services/guidance_context_service.py` | `_project_snapshot` 的文本扩展名白名单要收 C++ 后缀，否则 1-1 的 `solution.cpp` 不进指导上下文。 | 改（Task 4 修复轮，见 Ruling 42） |
| `backend/tests/test_guidance_context_service.py` | 1-1 的文件名改 `solution.cpp`。 | 改 |
| `frontend/package.json` + `package-lock.json` | 新增 `@codemirror/lang-cpp`。 | 改 |
| `frontend/src/views/CodeLab.vue` | C++ 语法与补全；文件名不再写死。 | 改 |
| `frontend/src/components/LabFileTree.vue` | `.cpp` 图标与标签。 | 改 |
| `frontend/src/config/flagshipExercises.js` | 阶段一描述改语言中立。 | 改 |

---

### Task 1: 后端镜像装 g++

**为什么排第一**：本机没有任何 C++ 编译器，后面每个任务的验证命令都是 `docker exec ... g++`。没有这一步，Task 2 的单测根本无法运行。

**Files:**
- Modify: `backend/Dockerfile`

**Interfaces:**
- Produces: 容器内可用的 `g++`（供 `cpp_judge.py` 的 `subprocess` 调用），以及 `learning_router.py` / `qa_router.py` 早已写好的 `cpp → g++` 语言映射终于可用。

- [ ] **Step 1: 改 `backend/Dockerfile`**

当前是 `FROM python:3.11-slim`、无任何编译器。**只插入一段 apt 安装**，其余每一行都必须原样保留——尤其第 7 行的 pip 装了国内镜像，漏掉它会让构建慢到像卡死：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 判题要用 g++ 编译 C++ 关卡（1-1 试点）。--no-install-recommends 避免拖进
# 一堆文档包；build-essential 太重（含 make/gcc 全家桶），只要 g++ 本体。
# libc6-dev 显式写出，只为不依赖传递依赖：gcc-14 对 libc6-dev 只是 Recommends
# （--no-install-recommends 会跳过它），但 g++ 实际是被
# g++-14 → libstdc++-14-dev → libc6-dev 这条硬 Depends 链带进来的，
# 所以只装 g++ 也能链接。写明后即使这条链将来变了，也不会退化成
# 「能编译、链接不了」（ld: cannot find Scrt1.o / crti.o）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制源码
COPY . .

# Fail the image build if resource configuration points at an SVG that was
# not committed. This prevents a successful deploy with silent placeholders.
RUN python scripts/validate_resource_images.py

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 启动服务（生产模式，无热重载）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

改完之后自查两条，确认**只多了一段 apt、没少别的**：

```bash
grep -n "tuna.tsinghua" backend/Dockerfile
grep -c "apt-get install -y --no-install-recommends g++ libc6-dev" backend/Dockerfile
```

Expected: 第一条仍有一行命中（第 7 行那行 pip），第二条输出 `1`。

- [ ] **Step 2: 重建并启动**

在仓库根目录 `D:\code\innovational-competition` 执行：

```bash
docker compose up -d --build
```

等待约 30s（apt 层首次构建较慢）。

- [ ] **Step 3: 验证容器里编译器和运行环境都在**

```bash
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend sh -c 'g++ --version | head -1'
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend sh -c 'printf "#include <vector>\n#include <iostream>\nint main(){std::vector<int> v{1,2};std::cout<<v.size();return 0;}\n" > /tmp/t.cpp && g++ -std=c++17 -O2 -Wall /tmp/t.cpp -o /tmp/t && /tmp/t; echo'
```

Expected: 第一行打印 `g++ (Debian ...) 14.x`（基础镜像是 Debian 13 trixie，版本号随镜像漂移，不必纠结具体数字）；第二条打印 `2`（证明「编译 → 运行」在容器里跑得通，这正是判题要做的两件事）。

**第二条是这一步的重点，别用 `which g++` 代替它**：`which g++` / `g++ --version` 只证明
编译器这个二进制在，不证明它能产出能跑的可执行文件——链接缺的是启动目标文件、头文件、
库这些**同一次真编译才会暴露**的东西。这一步失败即 Step 1 的 apt 行有问题，别改判题代码。

> 试点实测（已核对 `docker history` + 容器内 `dpkg -l`）：**只写 `g++`、不写 `libc6-dev`
> 也能链接**。`gcc-14` 对 `libc6-dev` 确实只是 `Recommends`，但 `g++` 走的是
> `g++-14 → libstdc++-14-dev → libc6-dev`，而 `libstdc++-14-dev` 的 `Depends` 里
> **硬依赖** `libc6-dev (>= 2.23-1~)`，`--no-install-recommends` 跳不掉。
> 所以计划里「不加 libc6-dev 就会 `cannot find Scrt1.o`」的说法是**错的**，已更正；
> apt 行仍保留 `libc6-dev`，理由从「否则链接不了」改成「不依赖传递依赖」——
> 这条链将来变了不至于退化成链接失败。

- [ ] **Step 4: 确认容器与后端都没被这一步弄坏**

```bash
docker ps --format '{{.Names}}|{{.Status}}' | grep -E 'ai-learning'
curl -sS -o /dev/null -w 'backend /docs -> %{http_code}\n' http://127.0.0.1:8001/docs
```

Expected: 两个容器 `Up`；`/docs` 返回 `200`。若后端起不来，先检查 `docker-entrypoint.sh` 是否被编辑器改成了 CRLF（`file backend/docker-entrypoint.sh` 应报 `ASCII text`，不是 `with CRLF line terminators`）。

- [ ] **Step 5: 记录镜像体积变化**

```bash
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep -i learning
```

Expected: 镜像变大。**实测 `1.16GB → 1.54GB`，约 +380MB**——远高于原先估的约 130MB
（g++ 只是入口，真正吃体积的是 `libstdc++-14-dev` 与 `libc6-dev` 的整套工具链依赖）。
把这个数字记在任务小结里，Task 9 上生产前要确认线上磁盘放得下。

---

### Task 2: C++ 判题执行路径

**Files:**
- Create: `backend/services/cpp_judge.py`
- Modify: `backend/services/judge_service.py`（`_run_judge`，第 470 行）
- Test: `backend/tests/test_cpp_judge.py`

**Interfaces:**
- Consumes: Task 1 的容器内 `g++`。
- Produces:
  - `run_cpp_judge(code: str, spec: dict, expected_total: int, timeout: int) -> dict` —— 返回体与 `judge_service._run_judge` **完全同构**（`passed` / `total` / `passed_count` / `compile_error` / `results` / `execution_time` / `judge_mode`），`results` 里每行是 `{"case_index": int, "description": str, "passed": bool, "error": str | None, "duration_ms": float | None}`。
  - `compile_cpp_only(code: str, timeout: int = 20) -> dict` —— 只 `-fsyntax-only`，返回 `{"ok": bool, "error": str}`。供 Task 4 的 `first_llm_call` 阶段替代 Python 的 `ast.parse`。
  - `cpp_policy_error(code: str) -> str | None`
  - `CppContractError`（关卡声明写错时抛，服务端 bug，不是学生错）
  - `run_cpp_judge` 由 `judge_service._run_judge` 在 `spec["language"] == "cpp"` 时调用；`_with_case_views` 保持不变，因此 `judge_submission` / `judge_samples` 对外行为不变。

- [ ] **Step 1: 先写失败的测试（合成 spec，不依赖任何真实关卡）**

创建 `backend/tests/test_cpp_judge.py`：

```python
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

        已知的不精确处（不改，但要知道）：这份 fixture 的 body 没转义引号，所以它其实
        **编译不过**——本测试真正覆盖的是「策略在编译前拒绝」那条路。`exit(` 只要还在
        黑名单里，转义与否测的都是同一件事；要让它测到「编译之后」的行为，得照下面那条
        测试的写法给 body 转义。
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
```

- [ ] **Step 2: 跑测试确认它失败**

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -p "test_cpp_judge.py" -v
```

Expected: FAIL —— `ModuleNotFoundError: No module named 'services.cpp_judge'`。

- [ ] **Step 3: 写实现 `backend/services/cpp_judge.py`**

整份文件如下（这是本计划的核心，逐字照抄）：

```python
"""C++ 关卡的判题执行路径。

Python 关卡把学生代码 exec 进一个受限命名空间；C++ 关卡换一套等价物：
按关卡声明的签名生成 main.cpp，和学生写的 solution.cpp 分两个编译单元一起
g++ 编译，逐条用例调用后把结果打成 __CASE__ 行回传。

**比对、归类、渲染仍然全部在 Python 侧完成**（judge_service._case_views 那条
管线一行不改）。C++ 只负责把 actual 或 threw 吐回来，因此现有 26 个工作区单测
继续覆盖同一套逻辑。

与 judge_service 一样，这是应用级隔离（拒绝明显的危险调用 + ulimit + 临时目录），
不是安全沙箱。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path


COMPILE_TIMEOUT = 20
CASE_MARKER = "__CASE__"

# ⚠️ 这条路径的边界，写在这里免得以后有人高估它（设计文档的措辞是「应用层隔离边界，
# 不是加固的多租户沙箱」）：
#   1) 判题结论**只在 Python 侧产生**。学生进程只回传观测（actual / threw / mutated /
#      ms），不回传「过没过」——曾经打过 "ok" 字段，那等于让学生进程自己宣布通过。
#   2) 同一个 index 的 payload **取最后一条**，且**出现重复即判该用例失败**：
#      判题器自己的结果行永远打在学生输出之后，所以「在函数体开头打一行伪造」盖不住
#      真结果；但只靠「取最后一条」还不够——学生可以在**后续用例的调用里**给**已经判完
#      的用例**再补一行伪造（该函数每用例都被调用一次，伪造语句也就重复执行），实测
#      能把 index 1..N-1 全部翻成通过。脚手架每条用例只打一行，重复即伪造。
#   3) 仍然关不掉的：学生代码与判题脚手架同进程、共享 stdout。它可以
#      `std::ifstream` 读 main.cpp（拿到用例入参）、可以 dup/freopen 重定向 stdout、
#      可以在全局析构里在判题器结果行之后再补一行伪造、也可以猜出异常类型名。
#      **「提前收工」这一类只关掉了一半**：returncode 门管住的是**非零**退出的那一半
#      （terminate / 信号 / 段错误），**正常退出（returncode 0）那一半仍然开着** ——
#      在全局构造里打满 N 行伪造（每条 index 恰好一行、不重复），再用
#      `syscall(SYS_exit, 0)` 或 `dlsym(RTLD_DEFAULT, "_exit")(0)` 直接退出，
#      进程正常结束、真结果行一条都不存在，伪造行被逐条采信（实测 passed=True, 4/4）。
#      `syscall(` / `dlsym(` 已进黑名单，但**这不能算修好了**：内联汇编、手写声明
#      `extern "C" void _exit(int);` 等等都绕得过去。
#
#      为什么 C++ 做不到 Python 那一侧的强度（不是懒惰，是语言差异）：Python 关卡靠
#      三条**结构性**规则把这条路堵死了 —— ①模块顶层只能定义函数/类/常量（等价于
#      「不许有全局构造函数」）；②模块白名单挡住 os / sys / ctypes（`os._exit` 到不了）；
#      ③禁 exit/quit/SystemExit。而 C++ 三个都做不到：全局对象天然允许、没有「模块」
#      概念（头文件里全是这些能力）、手写函数声明就能拿到同名系统调用。
#      判题器要真正关掉它，只能靠 OS 级隔离（独立进程 + 命名空间/seccomp 或父进程守门），
#      那时「脚手架跑完了」才是一个**学生进程无法伪造的观测**。
#      本试点按设计文档的定位（应用层隔离边界，不是加固的多租户沙箱）接受这一残留风险；
#      **据此不要说「C++ 判题防作弊」，也不要说「黑名单挡住了提前退出」**。
#
#   判断进展时请对照上面三条：现在的状态是「1 关掉了、2 关掉了、3 关掉一半」。

# 明显的危险调用直接拒绝。跟 Python 侧的 ast 白名单相比这是权宜之计：
# C++ 没有可用的标准库级沙箱，能做的是「把最危险的一小撮挡在门外」，
# 真正的边界是 ulimit + 临时工作目录 + 判题进程与业务进程分离。
#
# ⚠️ 别把这份清单当防线。它在两轮审查里各漏过一次（先是 exit(0)，再是 terminate()），
# 真正的防线是另外两条**结构性**规则：进程非正常退出即整份不算数（returncode 非 0）、
# 同一 index 出现两行结果即判伪造。黑名单只负责把常见的自杀写法在编译前点名，
# 报出人话——漏掉某个 token 不应该让攻击成立。
BANNED_CPP_TOKENS = (
    "system(", "popen(", "fork(", "execl(", "execv(", "execve(",
    "dlopen(", "setuid(", "chroot(",
    # 进程自杀类，与 Python 侧 ast 策略禁掉 exit/quit/SystemExit 对齐。
    # 少了这一组，「伪造 __CASE__ 行」就能直接变成「整份判题伪造」：学生先打一批
    # 伪造行、再 exit(0)，进程提前且**正常**退出，判题器自己的结果行一条都没来得及
    # 打出来，而 returncode==0 又让「没拿到结果就拒绝」那道兜底不触发。
    # atexit 一并禁掉，否则改由退出时回调打印假行，同样能绕到真结果之后。
    #
    # terminate( 必须一起进来：它把上面那条路换成**非零**返回码，正好绕开「returncode==0
    # 才需要挡」的思路（实测：全局构造里伪造 4 行再 std::terminate() → passed=True, 4/4）。
    # 顺带覆盖 set_terminate(。_exit( / longjmp( 同属「不抛异常、直接终止/跳走」的写法。
    # syscall( / dlsym( 是**同一类里的另一条**：绕开上面这些名字，直接发退出系统调用
    # （实测 syscall(SYS_exit, 0) 与 dlsym(RTLD_DEFAULT, "_exit")(0) 都能拿到
    # passed=True, 4/4，因为它们是**正常**退出、returncode 门不管）。这两个在这类
    # DSA 题里没有任何正当用途，所以收进来。
    # 没把 raise( / signal( / kill( 放进来：它们由 returncode 门覆盖，而 signal( 在
    # 将来用得上 <csignal> 的关卡里会误伤。
    # **仍然不要**把这份清单当防线：内联汇编、手写 `extern "C" void _exit(int);`
    # 之类都绕得过去（见上面第 3 条的说明）。
    "exit(", "_Exit(", "quick_exit(", "abort(", "atexit(",
    "terminate(", "_exit(", "longjmp(", "syscall(", "dlsym(",
)


class CppContractError(RuntimeError):
    """关卡声明的 C++ 契约有误。这是服务端配置问题，不是学生的代码问题。"""


_CPP_SUPPORT = r'''
// ── 判题支持代码（由判题器生成，学生不必也不应关心）──────────────
// 非模板重载必须写在模板之前：模板内部对 int / bool 这类内置类型的调用，只能
// 靠定义点可见的普通查找解析（内置类型没有关联命名空间，ADL 帮不上忙），
// 顺序颠倒会在编译期找不到匹配的重载。
static std::string json_escape(const std::string& s) {
  std::string out;
  for (char c : s) {
    switch (c) {
      case '"':  out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n";  break;
      case '\r': out += "\\r";  break;
      case '\t': out += "\\t";  break;
      default:   out += c;
    }
  }
  return out;
}

static void to_json(std::ostream& os, int v) { os << v; }
static void to_json(std::ostream& os, long v) { os << v; }
static void to_json(std::ostream& os, long long v) { os << v; }
static void to_json(std::ostream& os, double v) { os << v; }
static void to_json(std::ostream& os, bool v) { os << (v ? "true" : "false"); }
static void to_json(std::ostream& os, const std::string& v) { os << '"' << json_escape(v) << '"'; }

template <typename T>
static void to_json(std::ostream& os, const std::vector<T>& v) {
  os << '[';
  for (std::size_t i = 0; i < v.size(); ++i) {
    if (i) os << ',';
    to_json(os, v[i]);
  }
  os << ']';
}
'''.strip()


def cpp_policy_error(code: str) -> str | None:
    """最小安全扫描：学生代码里出现这些调用就直接拒绝。"""
    # 注释里出现 system( 是正常的（学生在讲解为什么不用它），先去掉注释再扫。
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", code, flags=re.S)
    # 报「最长」的那个命中项，而不是第一个：子串匹配下 `exit(` 会先命中 `atexit(` /
    # `quick_exit(`，于是学生写 std::atexit(nullptr) 会被告知「不允许调用 exit」——
    # 拒绝了是对的，但点名的不是他写的东西，读起来像判题器认错了。多个同长命中时
    # 取清单里靠前的那个（顺序即优先级），结果稳定。
    hit = max(
        (token for token in BANNED_CPP_TOKENS if token in stripped),
        key=lambda token: (len(token), -BANNED_CPP_TOKENS.index(token)),
        default=None,
    )
    if hit:
        return f"安全检查未通过：C++ 关卡不允许调用 {hit.rstrip('(')}"
    return None


# 类型关键字：出现在末尾说明它本身就是类型的一部分（unsigned int / long long），
# 不是形参名；struct/class/enum/union 属于「首词定调」，后面那个词也不能当形参名剥。
_TYPE_KEYWORDS = {
    "void", "bool", "char", "short", "int", "long", "float", "double",
    "signed", "unsigned", "wchar_t", "char8_t", "char16_t", "char32_t",
    "auto", "const", "volatile", "size_t",
}
_ELABORATED_HEAD = {"struct", "class", "enum", "union"}


def _strip_param_name(text: str) -> str:
    """剥掉签名里的形参名：`std::vector<int> items` → `std::vector<int>`。

    关卡声明的是完整 C++ 签名，而人写签名时一定会带形参名
    （`array_insert(std::vector<int> items, int index, int value)`）。生成的
    main.cpp 要用**纯类型**声明实参变量，留着名字会生成
    `std::vector<int> items a0 = {…};` 这种编译不过的东西。
    只剥「最后一个词是标识符、且它不是类型关键字」的情形，所以
    `unsigned int` / `long long` / `struct Foo` 都原样保留。
    """
    tokens = text.split(" ")
    if len(tokens) < 2:
        return text
    last = tokens[-1]
    if not re.fullmatch(r"[A-Za-z_]\w*", last):
        return text
    if last in _TYPE_KEYWORDS or tokens[0] in _ELABORATED_HEAD:
        return text
    return " ".join(tokens[:-1])


def _normalize_type(type_name: str) -> str:
    """去掉形参名、const 与引用/指针修饰，得到可以直接用来声明变量的类型名。"""
    text = re.sub(r"\s+", " ", type_name).strip()
    text = re.sub(r"^(const|volatile)\s+", "", text).strip()
    text = _strip_param_name(text)
    text = re.sub(r"[\s&*]+$", "", text).strip()
    return text


def _cpp_param_types(signature: str) -> list[str]:
    """从签名里取出形参类型。只在最外层逗号处切分，尊重 <> () [] 的嵌套。"""
    if "(" not in signature or ")" not in signature:
        raise CppContractError(f"cpp.signature 不是合法签名：{signature!r}")
    inner = signature[signature.index("(") + 1: signature.rindex(")")]
    if not inner.strip():
        return []
    parts, depth, current = [], 0, ""
    for char in inner:
        if char in "<([":
            depth += 1
        elif char in ">)]":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    parts.append(current)
    return [_normalize_type(part) for part in parts]


def _cpp_element_type(type_name: str) -> str:
    """取 std::vector<T> 的 T；非容器原样返回。"""
    text = _normalize_type(type_name)
    match = re.fullmatch(r"std::vector\s*<\s*(.+?)\s*>", text)
    if not match:
        return text
    return _normalize_type(match.group(1))


def _cpp_literal(value, type_name: str) -> str:
    """把用例里的 JSON 参数写成 C++ 字面量。不需要任何 JSON 解析库。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if "double" in type_name or "float" in type_name:
            return f"{value}.0"
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        element = _cpp_element_type(type_name)
        return "{" + ", ".join(_cpp_literal(item, element) for item in value) + "}"
    raise CppContractError(
        f"C++ 关卡的用例暂不支持 {type(value).__name__} 类型的参数：{value!r}"
    )


def _cpp_case_block(
    index: int,
    item: dict,
    param_types: list[str],
    target: str,
    exception_types: list[str],
) -> list[str]:
    """生成一条用例的调用与结果打印。整条结果攒在 ostringstream 里最后一次性
    输出：学生代码里的 cout 调试输出就不会把 __CASE__ 行截断成两半。"""
    args = list(item.get("args", []))
    if len(args) != len(param_types):
        raise CppContractError(
            f"用例「{item.get('description')}」有 {len(args)} 个参数，"
            f"而签名声明了 {len(param_types)} 个"
        )
    lines = ["  {", "    std::ostringstream buf;", f'    buf << "{{\\"i\\":{index}";']
    for position, value in enumerate(args):
        lines.append(
            f"    {param_types[position]} a{position} = "
            f"{_cpp_literal(value, param_types[position])};"
        )
        if isinstance(value, list):
            lines.append(f"    auto a{position}_before = a{position};")
    lines.append("    bool mutated = false;")
    # 逐用例计时：评测面板在用例行尾显示「{duration_ms}ms」，Python runner 也是
    # 逐条给的，这条路径不能只有 C++ 关卡缺这一列。
    lines.append("    auto t0 = std::chrono::steady_clock::now();")
    lines.append("    try {")
    call = ", ".join(f"a{position}" for position in range(len(args)))
    lines.append(f"      auto actual = {target}({call});")
    for position, value in enumerate(args):
        if isinstance(value, list):
            lines.append(
                f"      if (a{position} != a{position}_before) mutated = true;"
            )
    # 只回传**观测**，不回传判题结论：这里曾经打过 "ok":true/false，等于让运行在
    # 学生机器上的这段代码自己宣布「本条通过」。学生只要伪造一批 __CASE__ 行就能
    # 全绿——而伪造的门槛极低，因为「是否通过」这个判断本来就是这段代码做的。
    # 现在所有结论都在 Python 侧由 _compare_case 从 actual/threw 重新算出来。
    lines.append('      buf << ",\\"actual\\":";')
    lines.append("      to_json(buf, actual);")
    for cpp_type in exception_types:
        lines.append(f"    }} catch (const {cpp_type}&) {{")
        lines.append(f'      buf << ",\\"threw\\":\\"{cpp_type}\\"";')
    lines.append("    } catch (const std::exception& e) {")
    lines.append(
        '      buf << ",\\"threw\\":\\"other\\",\\"what\\":\\""'
        ' << json_escape(e.what()) << "\\"";'
    )
    lines.append("    } catch (...) {")
    lines.append('      buf << ",\\"threw\\":\\"unknown\\"";')
    lines.append("    }")
    lines.append("    auto t1 = std::chrono::steady_clock::now();")
    lines.append(
        "    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();"
    )
    # mutated 在按值签名下**结构上永远为 false**：a{position} 是 main.cpp 的局部量，
    # 按值传给学生的函数，callee 改的是自己的副本，改不到这里。要让学生真改到调用方
    # 的容器，签名得改成引用——而那时链接期就挂了（判题声明的原型是按值）。
    # 保留这段是为了「声明改了签名语言却还允许」这种将来变化下仍能报出来，但要知道
    # 它现在零区分度：它对应的 immutable 用例在 C++ 下永远静默通过。
    lines.append('    if (mutated) buf << ",\\"mutated\\":true";')
    # 用 llround 而不是流格式化（std::fixed）取两位小数：fixed 是粘性状态，
    # 将来在这之后再加字段会被一起改掉。
    lines.append('    buf << ",\\"ms\\":" << std::llround(ms * 100.0) / 100.0 << "}";')
    lines.append(f'    std::cout << "{CASE_MARKER}" << buf.str() << std::endl;')
    lines.append("  }")
    return lines


def build_main_cpp(spec: dict) -> str:
    """按关卡声明生成 main.cpp。"""
    contract = spec.get("cpp") or {}
    signature = str(contract.get("signature") or "").strip().rstrip(";").strip()
    if not signature:
        raise CppContractError("关卡声明缺少 cpp.signature")
    target = str(spec.get("target") or "").strip()
    if not target or f"{target}(" not in signature.replace(" ", ""):
        raise CppContractError(
            f"cpp.signature 里找不到目标函数 {target!r}：{signature!r}"
        )
    param_types = _cpp_param_types(signature)

    exception_map = contract.get("exception_map") or {}
    exception_types: list[str] = []
    for cpp_type in exception_map.values():
        text = _normalize_type(str(cpp_type))
        if text == "std::exception" or text in exception_types:
            continue
        exception_types.append(text)

    # 支持代码自己要用的头文件放最前，关卡声明的追加在后（去重）。
    # <chrono>/<cmath> 是判题脚手架自己要用的（逐用例计时），与关卡声明无关。
    includes = [
        "<iostream>", "<sstream>", "<string>", "<vector>", "<cstddef>",
        "<exception>", "<chrono>", "<cmath>",
    ]
    for name in list(contract.get("includes") or []):
        if name not in includes:
            includes.append(name)

    lines = [f"#include {name}" for name in includes]
    lines += [
        "",
        _CPP_SUPPORT,
        "",
        "// 关卡声明的函数原型。学生若改动了签名，这里会编译不过或链接不上——",
        "// 换 C++ 之后，「签名不许改」是编译器保证的，不再依赖静态检查。",
        f"{signature};",
        "",
        "int main() {",
    ]
    for index, item in enumerate(spec.get("cases", []), start=1):
        lines += _cpp_case_block(index, item, param_types, target, exception_types)
    lines += ["  return 0;", "}"]
    return "\n".join(lines) + "\n"


def _first_compiler_error(text: str) -> str:
    """取第一条 error 行。编译时传的是相对文件名，因此不会出现临时目录前缀。"""
    for line in (text or "").splitlines():
        if ": error:" in line or line.startswith("g++:") or ": fatal error:" in line:
            return line.strip()[:300]
        # 链接期诊断同样是「学生的错」，而且比 collect2 那句有用得多：改签名 → ld 报
        # undefined reference（带上判题方期望的完整签名）；学生自己写 main →
        # multiple definition。只认 "collect2: error: ld returned 1 exit status" 等于
        # 什么都没告诉学生，所以这里必须一并收进来。
        if "undefined reference to" in line or "multiple definition of" in line:
            return line.strip()[:300]
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:300]
    return "编译失败，但编译器没有给出错误信息"


def _run_limits() -> None:
    """给判题程序加上限。仅在 POSIX 上由 preexec_fn 调用。"""
    import resource

    cpu = COMPILE_TIMEOUT
    for name, value in (
        ("RLIMIT_CPU", (cpu, cpu)),
        ("RLIMIT_AS", (512 * 1024 * 1024, 512 * 1024 * 1024)),
        ("RLIMIT_FSIZE", (8 * 1024 * 1024, 8 * 1024 * 1024)),
        ("RLIMIT_NPROC", (64, 64)),
    ):
        limit = getattr(resource, name, None)
        if limit is not None:
            try:
                resource.setrlimit(limit, value)
            except (ValueError, OSError):
                pass


def _cpp_repr(value, max_len: int = 300) -> str:
    """与 RUNNER 里的 _safe_repr 保持一致。那份定义在 judge_service.RUNNER 的
    源码字符串里，只能被 runner 子进程使用，无法 import，因此这里镜像一份——
    改一处必须改两处。"""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) > max_len:
        text = text[:max_len] + "...(截断)"
    return text


def _compare_case(
    item: dict, payload: dict | None, exception_map: dict, duplicated: bool = False
) -> dict:
    """把 C++ 侧吐回的一条原始结果，整成与 Python runner 同构的一行。

    报错文案沿用 runner 的三段式（输入/期望/实际），因为评测面板的「实际」列
    就是靠 `_sample_actual` 去 error 里找 `实际:` 这一行取数的。
    """
    description = str(item.get("description", ""))
    if duplicated:
        # 判题脚手架每条用例只打一行。多出来的那一行只可能来自学生代码，
        # 而且它的存在本身就说明这次提交在试图伪造判题输出——这条用例直接判失败，
        # 不采信任何一条（采信「最后一条」会被后续调用里补的那一行翻盘，见
        # _parse_case_lines 的说明）。
        return {
            "description": description,
            "passed": False,
            "error": "这一条的结果行出现了多次，疑似伪造判题输出",
        }
    if payload is None:
        return {
            "description": description,
            "passed": False,
            "error": "程序在跑到这一条用例之前就退出了（可能是崩溃、死循环或提前 return）",
        }

    token = item.get("exception")
    if token:
        want = str(exception_map.get(token) or "")
        if not want:
            raise CppContractError(f"关卡声明缺少异常 {token} 的 C++ 类型映射")
        thrown = payload.get("threw")
        if thrown == want:
            return {"description": description, "passed": True, "error": None}
        if thrown == "other":
            actual = f"抛出了别的异常：{payload.get('what', '')}"
        elif thrown == "unknown":
            actual = "抛出了非 std::exception 的异常"
        elif thrown is None:
            actual = _cpp_repr(payload.get("actual"))
        else:
            actual = f"抛出了 {thrown}"
        return {
            "description": description,
            "passed": False,
            "error": f"该非法输入必须抛出 {token}\n实际: {actual}",
        }

    # payload 里没有「是否通过」这种字段：那是判题器的结论，不能由跑着学生代码的
    # 那个进程自己宣布。这里只读观测——threw 出现即「这次调用没有正常返回」。
    thrown = payload.get("threw")
    if thrown:
        what = str(payload.get("what") or "")
        detail = f"抛出了 {thrown}" + (f"：{what}" if what else "")
        return {
            "description": description,
            "passed": False,
            "error": f"这条用例不应该抛出异常\n实际: {detail}",
        }

    actual = payload.get("actual")
    if actual != item.get("expected"):
        return {
            "description": description,
            "passed": False,
            "error": (
                "返回结果不符合该业务场景\n"
                + "输入: " + _cpp_repr(item.get("args", [])) + "\n"
                + "期望: " + _cpp_repr(item.get("expected")) + "\n"
                + "实际: " + _cpp_repr(actual)
            ),
        }
    if item.get("fresh_result"):
        raise CppContractError("C++ 关卡暂不支持 fresh_result 用例（按身份比较无法直译）")
    if item.get("immutable") and payload.get("mutated"):
        return {
            "description": description,
            "passed": False,
            "error": "函数修改了输入对象\n实际: 入参容器在调用后被改动",
        }
    return {"description": description, "passed": True, "error": None}


def _parse_case_lines(stdout: str) -> tuple[dict[int, dict], set[int]]:
    """从学生程序的标准输出里挑出判题器自己打的结果行。

    学生代码里的 cout 调试输出会混在 stdout 里，所以用 __CASE__ 前缀做标记，
    而不是假设 stdout 只有判题输出。

    返回 `(payloads, duplicated)`：
    - `payloads[index]` 取**最后一条**同名行——判题器自己的结果行永远打在学生输出之后，
      所以「在函数体开头打一行伪造」盖不住真结果。
    - `duplicated` 是出现过 **多于一条**结果行的用例下标。判题脚手架每条用例**只打一行**，
      所以重复只可能来自学生伪造。这一条不能省：只靠「取最后一条」的话，学生可以在**后续
      用例的调用里**给**已经判完的用例**再补一行伪造，让它成为最后一条——实测过，这样
      index 1..N-1 全都能被翻成通过（只有最后一条用例因为不再有学生代码运行而安全）。
    """
    payloads: dict[int, dict] = {}
    seen: set[int] = set()
    duplicated: set[int] = set()
    for line in (stdout or "").splitlines():
        if not line.startswith(CASE_MARKER):
            continue
        try:
            payload = json.loads(line[len(CASE_MARKER):])
        except ValueError:
            continue
        index = payload.get("i")
        if isinstance(index, int):
            if index in seen:
                duplicated.add(index)
            seen.add(index)
            payloads[index] = payload
    return payloads, duplicated


def _payload_duration_ms(payload: dict | None) -> float | None:
    """取出这一条用例的耗时，统一成 float。

    C++ 侧打的是 double，但耗时恰好取整时 JSON 文本里就是 `0`，json.loads 会解析
    成 int；Python runner 那一侧永远是 float（`round(..., 2)`）。这里是判题面板的
    「{duration_ms}ms」与通过快照共用的字段，不统一类型就会时而 int 时而 float。
    """
    value = (payload or {}).get("ms")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compile_cpp_only(code: str, timeout: int = COMPILE_TIMEOUT) -> dict:
    """只做语法与语义检查，不链接。

    `first_llm_call`（热身阶段）用它替代 Python 关卡的 ast.parse：那时学生还没
    实现目标函数，链接必然失败，但「语法对不对」正是这一阶段要回答的问题。
    """
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "solution.cpp").write_text(code, encoding="utf-8")
            proc = subprocess.run(
                ["g++", "-std=c++17", "-fsyntax-only", "solution.cpp"],
                cwd=temp_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
    except FileNotFoundError:
        return {"ok": False, "error": "服务器未安装 g++，无法检查 C++ 代码"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"编译检查超时（>{timeout} 秒）"}
    except Exception as exc:  # pragma: no cover - 兜底
        return {"ok": False, "error": f"编译检查失败：{str(exc)[:200]}"}
    if proc.returncode == 0:
        return {"ok": True, "error": ""}
    return {"ok": False, "error": _first_compiler_error(proc.stderr or proc.stdout)}


def run_cpp_judge(code: str, spec: dict, expected_total: int, timeout: int) -> dict:
    """跑一份 C++ spec，返回与 judge_service._run_judge 同构的逐用例结果。"""
    started = time.perf_counter()

    def _fail(message: str) -> dict:
        return {
            "passed": False, "total": expected_total, "passed_count": 0,
            "compile_error": message, "results": [],
            "execution_time": round(time.perf_counter() - started, 3),
            "judge_mode": "server_private_cases",
        }

    policy_error = cpp_policy_error(code)
    if policy_error:
        return _fail(policy_error)

    # 关卡声明写错就让它冒出去：那是服务端配置问题，不该伪装成学生的编译失败。
    main_source = build_main_cpp(spec)
    contract = spec.get("cpp") or {}
    cases = spec.get("cases", [])
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "solution.cpp").write_text(code, encoding="utf-8")
            (Path(temp_dir) / "main.cpp").write_text(main_source, encoding="utf-8")
            # 编译单独 try：它的超时是 20 秒（COMPILE_TIMEOUT），与外层的运行超时
            # （timeout 参数，默认 6 秒）不是一回事。混在一起报的话，编译被拖死的学生
            # 会看到「运行超时（>6 秒）」——既指错了阶段，秒数也是错的。
            try:
                compile_proc = subprocess.run(
                    ["g++", "-std=c++17", "-O2", "-Wall", "main.cpp", "solution.cpp", "-o", "prog"],
                    cwd=temp_dir, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=COMPILE_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                return _fail(
                    f"编译超时（>{COMPILE_TIMEOUT} 秒）：提交的代码在编译阶段就耗尽了时间"
                    "（常见于病态模板递归或超大实例化）"
                )
            if compile_proc.returncode != 0:
                return _fail(_first_compiler_error(compile_proc.stderr or compile_proc.stdout))
            run_proc = subprocess.run(
                ["./prog"],
                cwd=temp_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
                preexec_fn=_run_limits if os.name == "posix" else None,
            )
    except FileNotFoundError:
        return _fail("服务器未安装 g++，无法评测 C++ 关卡")
    except subprocess.TimeoutExpired:
        return _fail(f"运行超时（>{timeout} 秒）")
    except Exception as exc:
        return _fail(f"判题执行失败：{str(exc)[:240]}")

    payloads, duplicated = _parse_case_lines(run_proc.stdout or "")
    # 进程**正常结束**是「stdout 上的东西可信」的前提，这条不能跟「拿到了几行结果」做与。
    #
    # 曾经写成 `returncode != 0 and not payloads`：谁都没想到「早退」有第二种死法——
    # 伪造一批 __CASE__ 行（每条用例恰好一行、不重复），然后 std::terminate() 或
    # std::raise(SIGABRT) 自杀。此时 payloads 非空 ⇒ 这道门不触发；每条 index 只出现
    # 一次 ⇒ 「重复即伪造」也不触发；进程在 main 的用例循环**开始之前**就死了，真结果行
    # 一条都不存在 —— 伪造的观测于是被逐条采信，整关判为通过，学生的函数零次调用。
    # （实测复现：terminate 与 raise(SIGABRT) 两条路都拿到 passed=True, 4/4。）
    #
    # 为什么 `returncode != 0` 就足以判定「这一趟不算数」：脚手架每条用例都包在
    # catch (const <映射类型>&) / catch (const std::exception&) / catch (...) 里，
    # **学生函数抛任何异常都不会让进程死**。所以非零返回码只可能来自「进程被杀」——
    # 段错误、terminate、被信号打死——此时 stdout 上的任何内容都不构成证据。
    # 处理方式与「编译返回非 0」对称：编译非 0 = 编译失败，运行非 0 = 运行失败。
    if run_proc.returncode != 0:
        error_lines = (run_proc.stderr or "提交代码未能完成执行").strip().splitlines()
        detail = error_lines[-1][:240] if error_lines else "提交代码未能完成执行"
        return _fail(
            f"判题进程异常退出（exit code {run_proc.returncode}）：{detail}"
        )

    exception_map = contract.get("exception_map") or {}
    results = [
        {
            "case_index": index,
            # 程序没跑到这条用例时 payload 缺失，给 None 让面板自己隐藏这个
            # 徽标，而不是显示一个假的 0ms。
            "duration_ms": _payload_duration_ms(payloads.get(index)),
            **_compare_case(
                item, payloads.get(index), exception_map, index in duplicated
            ),
        }
        for index, item in enumerate(cases, start=1)
    ]
    passed_count = sum(1 for item in results if item["passed"])
    return {
        "passed": bool(results) and passed_count == len(results),
        "total": len(results), "passed_count": passed_count,
        "compile_error": None, "results": results,
        "execution_time": round(time.perf_counter() - started, 3),
        "judge_mode": "server_private_cases",
    }
```

- [ ] **Step 4: 在 `judge_service.py` 的 `_run_judge` 顶部加分发**

在 `judge_service.py` 第 470 行的 `def _run_judge(...)` 里，紧跟 docstring 之后、`started = time.perf_counter()` 之前插入分发。**用函数内导入**，避免 `cpp_judge` 与 `judge_service` 的模块级循环导入：

```python
def _run_judge(code: str, spec: dict, expected_total: int, timeout: int) -> dict:
    """在隔离子进程里跑一份 spec，返回逐用例结果。正式判题与自测共用这条路径。"""
    # C++ 关卡走独立的编译 + 运行路径。函数内导入：cpp_judge 需要复用本模块的
    # 一些约定（结果行结构、_safe_repr 的三段式报错）。没有循环依赖（cpp_judge 不
    # import 本模块），这里放函数内是为了让只跑 Python 关卡的进程根本不加载这条路径。
    if str(spec.get("language") or "python") == "cpp":
        from services.cpp_judge import run_cpp_judge

        return run_cpp_judge(code, spec, expected_total, timeout)

    started = time.perf_counter()
```

注意 `judge_samples` 已经做了 `spec = dict(SPECS[exercise_id])` 的浅拷贝并替换 `cases`，因此 `language` / `cpp` 会一并带过去，自测自动走同一条 C++ 路径。**`_with_case_views`、`_case_views`、`_sample_actual`、`feedback_guidance`、`judge_submission`、`judge_samples` 一行都不用改**——这是本任务最关键的验收点。

- [ ] **Step 5: 跑测试确认全绿**

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -p "test_cpp_judge.py" -v
```

Expected: `Ran 16 tests ... OK`。C++ 单测会真的调 `g++`，整轮大约 5-10 秒，不要误判成卡住。
（14 → 16 是第三轮修复新增的两条：`test_the_reported_token_is_the_one_the_student_wrote`、
`test_a_run_that_died_cannot_be_passed_off_as_a_finished_run`。）

- [ ] **Step 6: 确认 Python 关卡的判题没被动过**

```bash
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -p "test_judge_service.py" -v
```

Expected: 全绿（此时 1-1 还是 Python，13 关都还是 Python，本任务只加了分发分支，没有改任何 Python 行为）。

---

### Task 3: 1-1 的语言声明与内容改写

**Files:**
- Modify: `backend/services/agent_lab_specs.py`（`SPECS["1-1"]`）
- Modify: `backend/scripts/verify_lab_content.py`（`REF_1_1`，第 28 行）
- Modify: `backend/data/flagship_exercises.json`（1-1 条目）
- Test: `backend/tests/test_judge_service.py`

**Interfaces:**
- Consumes: Task 2 的 `run_cpp_judge`。
- Produces: `SPECS["1-1"]` 带 `language: "cpp"` 与 `cpp: {signature, includes, exception_map}`，13 条用例；`REFERENCE_SOLUTIONS["1-1"]` 是 C++ 参考解。后续任务依赖 `SPECS["1-1"]["cases"]` 是 13 条、`SPECS["1-1"]["language"] == "cpp"`。

- [ ] **Step 1: 改 `SPECS["1-1"]`**

在 `agent_lab_specs.py` 里把整个 `"1-1": {...}` 条目替换为：

```python
    "1-1": {
        "target": "array_insert",
        "targets": ["array_insert"],
        # 缺省视为 python。语言决定工作区文件名、阶段检查文案与判题执行路径。
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<int> array_insert(std::vector<int> items, int index, int value)",
            "includes": ["<vector>", "<stdexcept>", "<string>"],
            "exception_map": {"out_of_range": "std::out_of_range"},
        },
        # exception 用语言中立的 token，由本关的 exception_map 映射到 C++ 类型。
        # 原来 10 条「传字符串/浮点/布尔当索引」的用例在 C++ 里编译期就挡掉了
        # （bool→int、double→int 是静默转换，不报错），因此改写成 C++ 真正的
        # 边界考点：单元素、size()-1、重复元素、下界越界。
        "cases": [
            {"description": "在中间插入元素", "args": [[1, 2, 3], 1, 9], "expected": [1, 9, 2, 3]},
            {"description": "在头部插入元素", "args": [[1, 2, 3], 0, 9], "expected": [9, 1, 2, 3]},
            {"description": "在末尾插入元素", "args": [[1, 2, 3], 3, 9], "expected": [1, 2, 3, 9]},
            {"description": "向空容器插入", "args": [[], 0, 5], "expected": [5]},
            {"description": "插入后不修改原容器", "args": [[1, 2, 3], 1, 9], "expected": [1, 9, 2, 3], "immutable": True},
            {"description": "拒绝越界索引", "args": [[1, 2, 3], 4, 9], "exception": "out_of_range"},
            {"description": "拒绝负数索引", "args": [[1, 2, 3], -1, 9], "exception": "out_of_range"},
            {"description": "单元素容器插入到头部", "args": [[7], 0, 9], "expected": [9, 7]},
            {"description": "单元素容器插入到末尾", "args": [[7], 1, 9], "expected": [7, 9]},
            {"description": "较长容器中间插入", "args": [[1, 2, 3, 4, 5], 2, 0], "expected": [1, 2, 0, 3, 4, 5]},
            {"description": "插入到 size()-1 位置", "args": [[1, 2, 3, 4], 3, 9], "expected": [1, 2, 3, 9, 4]},
            {"description": "含重复元素的容器", "args": [[5, 5, 5], 1, 5], "expected": [5, 5, 5, 5]},
            {"description": "下界越界", "args": [[1, 2, 3], -4, 9], "exception": "out_of_range"},
        ],
    },
```

同时把文件头的模块 docstring 换成下面这块。**注意这不是"只补一句语言说明"**：原有的
「判题约定（run_generic）」那一节必须**有保留地**搬回来——里面「用例是服务端私有、不会
发给浏览器」和 `{args, expected}` / `{exception}` / `"immutable"` 三条格式约定在本关改完之后
**仍然成立**，删掉就是文档倒退（T3 审查判为 Minor，起因是我这份计划给的替换块写漏了）。
但**不能照原样搬**：`"func"` 字段只有 Python 判题路径认，C++ 路径的 `build_main_cpp`
只读 `spec["target"]`（已核），原样搬回来等于在文档里声明一个 C++ 侧不存在的性质。

```python
"""关卡声明。13 关全部只用标准库实现，零第三方依赖（缺省 Python，1-1 为 C++ 试点）。

语言由每关的 "language" 字段声明，缺省 "python"。C++ 关卡额外声明 "cpp"
契约（signature / includes / exception_map），用例里的 exception 取语言中立
的 token（如 out_of_range），由该关的 exception_map 映射到具体的 C++ 类型。

用例约定（服务端私有，不会通过资源接口发送给浏览器；学生只能看到公开样例与
失败场景名称）：
- {"args": [...], "expected": ...} 要求返回值等于 expected；
- {"args": [...], "exception": <token>} 要求抛出对应异常：Python 关卡按内置异常名解析
  （SAFE_BUILTINS），C++ 关卡由该关的 exception_map 映射到具体类型；
- "immutable": True 要求调用前后输入对象完全不变；
- "func" 字段只在 Python 判题路径生效（改调该函数）；C++ 判题路径只调用
  spec["target"]。

本文件不再使用 mode=tool_call / tool_plan / checkpoint / sqlalchemy_query
等专用判题分支。
"""
```

- [ ] **Step 2: 改 `verify_lab_content.py` 的 `REF_1_1`（第 28 行）**

```python
REF_1_1 = '''
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
```

- [ ] **Step 3: 改 `flagship_exercises.json` 的 1-1 条目**

**改完宿主文件后必须把它写进容器**，否则页面还是旧内容：

```bash
MSYS_NO_PATHCONV=1 docker cp student/backend/data/flagship_exercises.json ai-learning-backend:/app/data/flagship_exercises.json
```

原因：应用读的是 `/app/data/flagship_exercises.json`，而 `/app/data` 是**命名卷**，
卷里那份会盖住镜像里 `COPY . .` 烘进去的那份——**重建镜像也不会刷新它**
（已实测：卷里那份的 mtime 是卷创建时间，与镜像构建时间无关；`down -v` 又绝不能跑）。
`docker cp` 到容器这个路径写的就是卷，所以立刻生效；`load_flagship_exercises()`
每次调用都重读文件，不需要重启后端。
自查：`md5sum student/backend/data/flagship_exercises.json` 与容器里同一路径的 md5 必须相同。

把 1-1 对象的 `description` / `input_output` / `starter_code` / `steps` / `acceptance` / `skills` 换成下面这组（`id` / `module` / `title` 保持原样）：

```json
"description": "顺序表（数组）的元素在内存里是连着的，所以在中间插入一个元素时，后面的元素必须整体后移一位——这正是插入操作为什么比在末尾追加更慢。实现 array_insert(items, index, value)：返回插入后的新容器，不要改动传入的 items。index 允许取 0 到 items.size()，等于 size() 表示追加到末尾；越界时抛出 std::out_of_range。本关用 C++17，只允许用标准库容器，不需要自己写 main，也不要引入任何第三方库。",
"input_output": "items 是 std::vector<int>，index 是 int，value 是 int。\n示例输入：([1, 2, 3], 1, 9)\n示例输出：[1, 9, 2, 3]\n示例输入：([1, 2, 3], 3, 9)\n示例输出：[1, 2, 3, 9]（index 等于 size() 表示追加到末尾）\n示例输入：([], 0, 5)\n示例输出：[5]",
"starter_code": "#include <vector>\n#include <stdexcept>\n#include <string>\n\n// 在顺序表的 index 位置插入 value，返回新的顺序表。\n// index 的合法范围是 0..items.size()：0 表示插到最前，size() 表示追加到末尾。\n// 越界时抛出 std::out_of_range。\n// 注意：签名、参数顺序、返回值类型都不能改动——判题会按这个签名调用你的函数。\nstd::vector<int> array_insert(std::vector<int> items, int index, int value) {\n  throw std::logic_error(\"请实现 array_insert：先做边界校验，再复制容器插入\");\n}\n",
"steps": [
  "按 0..size() 的合法范围校验 index，越界抛出 std::out_of_range",
  "复制一份 items，不要改动传入的容器",
  "在 index 位置插入 value 并返回新容器",
  "用中间位置的输入验证元素顺序，用 size() 验证末尾追加"
],
"acceptance": [
  "原容器保持不变",
  "插入后元素顺序正确，元素个数等于原 size() + 1",
  "越界（含负数）抛出 std::out_of_range",
  "不改动判题声明的函数签名"
],
"skills": [
  "顺序表",
  "边界校验",
  "值语义",
  "时间复杂度"
]
```

骨架用 `std::logic_error` 而不是 `std::out_of_range` 是刻意的：用 `out_of_range` 占位会让「拒绝越界索引」那两条用例被空骨架蒙对，学生一进来就看到 2/13 通过。`logic_error` 与任何用例的期望异常都不匹配，空骨架稳定 0/13。

- [ ] **Step 4: 改 `tests/test_judge_service.py`**

把文件第 8-20 行的 `CORRECT_SOLUTION` 换成 C++ 版：

```python
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
```

然后把 1-1 的 8 个测试换成下面这 8 个（1-3 的 `CORRECT_RPN_SOLUTION` 与 `test_rpn_evaluator_passes_every_private_scenario` 保持不动）：

新旧各 8 个方法**不是一一对应**：4 个照旧（`test_correct_solution_passes_every_private_scenario`、`test_rpn_evaluator_passes_every_private_scenario`、`test_off_by_one_boundary_rejects_appending_at_the_end`，以及把 `test_starter_not_implemented_error_fails_every_scenario` 改名为 `..._logic_error_...`），2 个换成 C++ 下的等价写法，2 个删除，另外**新增 2 个**（`test_changing_the_declared_signature_fails_to_link`、`test_wrong_exception_type_fails_the_boundary_case`）。下面这 4 个消失的方法都是**故意删的**，不是漏写，别把它们「补」回来：

| 原方法 | 处置 | 理由 |
|---|---|---|
| `test_printing_pass_marker_cannot_bypass_judge` | 换成 `test_a_program_with_its_own_main_cannot_bypass_the_judge` | C++ 下「打印 `[PASS]`」不再是绕过路径，**自己写 `main()`** 才是，判题靠重复定义在链接期拦下 |
| `test_import_and_file_access_are_rejected` | 换成 `test_banned_calls_are_rejected` | C++ 没有 `import`；设计文档第 110 行定的黑名单就是 `system(` / `popen(` / `fork(` 三条（**只禁进程创建，不禁普通文件读写**——读文件在 C++ 里是合法的标准库用法），所以按黑名单测，不要加 `ifstream` 之类的断言 |
| `test_mutating_the_caller_list_fails_the_immutability_case` | 删除 | 按值传参（`std::vector<int> items`）下，学生**无论如何都改不到调用方的容器**——这条在 C++ 里结构上就不可能失败，留着是永远为真的空测试。用例本身（`{"immutable": True}`）保留，`cpp_judge.py:401` 仍在判 `mutated`，学生要是把签名改成引用，链接期就挂了 |
| `test_missing_input_validation_fails` | 删除 | 类型校验那批用例（传字符串/浮点/布尔当索引）在 C++ 里编译期就挡掉了，已按设计换成真实的 C++ 边界用例，由 `test_off_by_one_boundary_rejects_appending_at_the_end` 与 `test_wrong_exception_type_fails_the_boundary_case` 覆盖 |

```python
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
        # （比如 JSON 没拷进命名卷、还是旧的 Python 骨架）**照样变绿**。
        # compile_error 非空 = 这次失败是编译/链接期失败，本测试没测到想测的东西。
        self.assertIsNone(result["compile_error"], result)

    def test_rpn_evaluator_passes_every_private_scenario(self):
        result = judge_submission("1-3", CORRECT_RPN_SOLUTION)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["passed_count"], 20)

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
```

并在 `CORRECT_SOLUTION` 下面补一个常量（骨架从关卡数据取，避免两处各写一份）：

```python
# 空骨架：解题时学生打开 solution.cpp 看到的就是它。
from services.judge_service import get_flagship_exercise

STARTER_SOLUTION = get_flagship_exercise("1-1")["starter_code"]
```

`test_judge_service.py` 顶部已有的 `from services.judge_service import judge_submission` 改为 `from services.judge_service import get_flagship_exercise, judge_submission`，并删掉上面那行重复 import。

- [ ] **Step 5: 跑判题测试**

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend md5sum data/flagship_exercises.json
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -p "test_judge_service.py" -v
```

Expected: 全绿。`test_starter_logic_error_fails_every_scenario` 通过这一点很关键——它同时证明了骨架被正确下发、`logic_error` 策略生效、13 条用例没被误算（它现在带 `assertIsNone(compile_error)`，所以「骨架编译不过」这种假通过会被抓住）。

重建会换掉容器，但**不会动命名卷**，所以 Step 3 `docker cp` 进 `/app/data/flagship_exercises.json` 的那份仍在；重建后再拷一次也同样是正确顺序，两种顺序都行——md5 自查是唯一的裁判，别靠推理。

- [ ] **Step 6: 跑内容校验**

```bash
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python scripts/verify_lab_content.py
```

Expected: 参考答案一节里 1-1 显示 `[PASS] 1-1  13/13  (...s)`（脚本的打印格式见 `verify_lab_content.py:1513`），其余 12 关仍 `[PASS]`，脚本退出码 0。1-1 的耗时会明显长于其它关（每次判题多一次 g++ 编译）。

注意此时 `run_stage_checks()` 应该仍然全 PASS：1-1 的 `project_files` 还是 `["solution.py"]`（工作区尚未改），这属于 Task 4 的范围。若这一步 `run_stage_checks` 报错，说明在 Task 4 之前就动了工作区，应停下检查。

- [ ] **Step 7: 记录结果**

把 `verify_lab_content.py` 的完整输出与 `test_judge_service` 的总结行记在任务小结里。**不要提交**（无 git）。

---

### Task 4: 工作区按语言派生（文件名 / 阶段表 / 检查逻辑 / 提示词）

**Files:**
- Modify: `backend/services/agent_lab_specs.py`（新增语言查询助手）
- Modify: `backend/services/lab_workspace_service.py`
- Modify: `backend/scripts/verify_lab_content.py:1470`
- Test: `backend/tests/test_lab_workspace_service.py`, `backend/tests/test_guidance_context_service.py`

**Interfaces:**
- Consumes: `SPECS[exercise_id]["language"]`（Task 3 已声明）。
- Produces:
  - `agent_lab_specs.lab_language(exercise_id) -> str`（`"python"` / `"cpp"`）
  - `agent_lab_specs.lab_solution_file(exercise_id) -> str`（`"solution.py"` / `"solution.cpp"`）
  - `agent_lab_specs.lab_repair_file(exercise_id) -> str`（`"repair_target.py"` / `"repair_target.cpp"`）
  - `agent_lab_specs.lab_language_label(exercise_id) -> str`（`"Python"` / `"C++"`）
  - 课程对象新增字段：`language`、`language_label`、`solution_file`、`repair_target_file`（前端只读这四个，不再猜扩展名）。
  - `lab_workspace_service.compile_cpp_only` 的调用点（`first_llm_call` 阶段）。

- [ ] **Step 1: 在 `agent_lab_specs.py` 末尾加助手**

```python
# ── 语言派生 ────────────────────────────────────────────────
# 工作区的文件名、阶段检查的措辞、给 AI 导师的提示词全部从这里取，避免
# 「solution.py」这个字符串散落在 service 各处后改不干净。
_LANGUAGE_FILES = {
    "python": ("solution.py", "repair_target.py", "Python"),
    "cpp": ("solution.cpp", "repair_target.cpp", "C++"),
}
_DEFAULT_LANGUAGE_FILES = _LANGUAGE_FILES["python"]


def lab_language(exercise_id: str) -> str:
    """本关的实现语言，缺省 python。"""
    spec = SPECS.get(str(exercise_id)) or {}
    return str(spec.get("language") or "python")


def _language_files(exercise_id: str) -> tuple[str, str, str]:
    return _LANGUAGE_FILES.get(lab_language(exercise_id), _DEFAULT_LANGUAGE_FILES)


def lab_solution_file(exercise_id: str) -> str:
    """本关学生要实现的那个文件。"""
    return _language_files(exercise_id)[0]


def lab_repair_file(exercise_id: str) -> str:
    """故障修复阶段生成的独立文件。"""
    return _language_files(exercise_id)[1]


def lab_language_label(exercise_id: str) -> str:
    return _language_files(exercise_id)[2]
```

- [ ] **Step 2: 在 `_course()` 里算出语言并写入返回值**

`_course()` 从第 162 行开始，`_IMPL_NOTES`（第 221 行）与 `_FIRST_RUN_STAGES`（第 377 行）都是**它内部的局部变量**、每次调用重建——所以语言必须在它们之前算好。先在第 27 行补导入：

```python
from services.agent_lab_specs import (
    SPECS, lab_language, lab_language_label, lab_repair_file, lab_solution_file,
)
```

再紧跟第 164 行的 `track_id = exercise_id.split("-", 1)[0]` 之后插入：

```python
    # 本关的语言属性决定文件名、阶段措辞与判题执行路径。必须放在下面所有
    # _IMPL_NOTES / _FIRST_RUN_STAGES / stages 的构造之前。
    language = lab_language(exercise_id)
    solution_file = lab_solution_file(exercise_id)
    repair_file = lab_repair_file(exercise_id)
    language_label = lab_language_label(exercise_id)
```

把第 611 行的 `project_files = ["solution.py"]` 与其上方的注释换成：

```python
    # 零依赖、零框架：常驻项目文件只有一个（Python 是 solution.py，C++ 是
    # solution.cpp）。故障修复与变式迁移阶段会另行生成 repair_target.* /
    # VARIANT_TASK.md，但那由 capability_service 负责，不进入这里的结构检查。
    project_files = [solution_file]
```

把 `structure` 阶段的文案与检查（第 628-637 行）换成：

```python
        {
            "id": "structure", "title": "确认题目文件", "icon": "FolderOpened",
            "instruction": (
                f"本关的项目文件是 {', '.join(project_files)}，文件名必须完全一致。\n\n"
                f"打开 {solution_file}，里面已经给出目标函数的骨架与返回值契约，"
                "你的任务就是把它实现出来。不需要创建虚拟环境、不需要声明或安装依赖——"
                f"本关只用 {language_label} 标准库。"
            ),
            "command": "", "checks": [f"{solution_file} 存在", "文件名大小写一致"],
            "target_file": solution_file,
        },
```

`first_run` 分支（第 642-646 行）改成按语言选表。注意这两个字典是 `_course()` 的局部变量，每次调用都是全新的，直接改不会污染下一次请求，不需要深拷贝：

```python
    first_run_source = _FIRST_RUN_STAGES_CPP if language == "cpp" else _FIRST_RUN_STAGES
    first_run = first_run_source.get(exercise_id)
    if first_run is not None:
        first_run["hints"] = _stage_hints(
            "first_llm_call", exercise, targets, track,
            solution_file=solution_file, language=language,
        )
        first_run["target_file"] = solution_file
        first_run["checks"] = [
            f"{solution_file} 编译通过" if language == "cpp" else f"{solution_file} 语法正确",
            "已运行过一次自测",
        ]
        stages.append(first_run)
```

把 `implementation` 阶段（第 648-666 行）换成：

```python
    implementation_checks = (
        [f"{language_label} 编译通过", f"{test_count} 个业务测试点通过"]
        if language == "cpp"
        # C++ 下「目标函数已定义」不用单独检查：未定义符号就是链接失败，
        # 走同一条编译错误路径，比 Python 时代的 ast 名字扫描更可靠。
        else [f"{language_label} 语法正确", "目标函数已定义", f"{test_count} 个业务测试点通过"]
    )
    stages.append({
        "id": "implementation", "title": impl_title, "icon": "EditPen",
        "instruction": (
            f"创建 {solution_file}，实现 {', '.join(targets)} 函数。"
            f"{implementation_hint}"
            f"{chr(10) + chr(10) + impl_notes if impl_notes else ''}"
        ),
        "command": "", "test_count": test_count,
        "checks": implementation_checks,
        "target_file": solution_file,
        "micro_steps": [
            {
                "id": f"implementation-{index}",
                "title": step,
                "description": "先完成这一小步并用一个最小输入自测，再继续下一步。",
            }
            for index, step in enumerate(implementation_steps, 1)
        ],
    })
```

`acceptance` 阶段（第 667-675 行）的 `"target_file": "solution.py"` 改成 `"target_file": solution_file`。

最后，在 `for stage in stages: stage["hints"] = ...`（第 677-678 行）之后、`return {` 之前，加统一的措辞本地化：

```python
    # 阶段文案是 13 关共用的一套模板，里面写死了 solution.py 与「Python 标准库」。
    # 在这里统一按语言替换，而不是去改 13 处字面量——模板加一句新话不用再想一遍
    # 「C++ 关卡要不要另写一份」。替换是幂等的：Python 关卡 solution_file 就是
    # solution.py，替换是空操作。
    for stage in stages:
        for key in ("instruction", "title"):
            if isinstance(stage.get(key), str):
                stage[key] = _localize_text(stage[key], solution_file, language_label)
        stage["checks"] = [_localize_text(str(item), solution_file, language_label) for item in stage.get("checks", [])]
```

并在 `_course` 函数**之前**定义：

```python
def _localize_text(text: str, solution_file: str, language_label: str) -> str:
    """把阶段模板里的 Python 措辞换成当前关卡语言的措辞（幂等）。"""
    if solution_file != "solution.py":
        text = text.replace("solution.py", solution_file)
    if language_label != "Python":
        text = text.replace("Python 标准库", f"{language_label} 标准库")
    return text
```

返回字典里补四个字段（第 679-707 行），放在 `"framework"` 前后都行，建议紧跟 `"title"`：

```python
        "language": language,
        "language_label": language_label,
        "solution_file": solution_file,
        "repair_target_file": repair_file,
```

框架字段按语言覆盖（`TRACK_CONFIG` 是按轨道配的，1-1 与 1-2 同属一轨，不能在那里分开）：

```python
        "framework": f"{language_label} 标准库" if language != "python" else track["framework"],
        "packages": [] if language != "python" else track["packages"],
        "framework_imports": [] if language != "python" else track["imports"],
```

前置知识（第 695-698 行）同样按语言覆盖：

```python
        "prerequisites": exercise.get(
            "prerequisites",
            [f"{language_label} 基础", "函数与异常处理"] if language != "python"
            else TRACK_PREREQUISITES.get(exercise_id.split("-", 1)[0], ["Python 基础"]),
        ),
```

累积链按语言门控（第 173-176 行）——这是 spec 第八节第 1 条的要求：

```python
    # 阶段一是累积式项目（1-2 继承 1-1、1-3 继承 1-2）。只在前一关与本关语言
    # 相同时才继承：1-1 改成 C++ 后，1-2 再宣称「继承 1-1 的 solution.py」就是假话，
    # 而且 _carry_over_toolbox 也找不到那个文件。
    previous = _CARRIES_FROM.get(exercise_id, "")
    carries_from = previous if previous and lab_language(previous) == lab_language(exercise_id) else ""
    carried_targets = targets[1:] if carries_from else []
```

- [ ] **Step 3: 加 C++ 专属的热身阶段与实现提示**

在 `_FIRST_RUN_STAGES`（第 377 行）这个字典的结束大括号之后、`stages` 之前加同结构的 C++ 版（**4 空格缩进，仍在 `_course()` 内**）：

```python
    # ── C++ 关卡的热身阶段。与 Python 版的区别：热身不写 main()，因为判题会把
    # 学生的 solution.cpp 和自动生成的 main.cpp 一起编译，多一个 main 会重复定义。
    _FIRST_RUN_STAGES_CPP = {
        "1-1": {
            "id": "first_llm_call", "title": "跑通第一段顺序表操作", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，用最朴素的方式把这件事做一遍（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 打开 solution.cpp，找到 array_insert 的骨架\n"
                "2. 先不管边界和值语义，直接在函数体里写：把 value 插到 items 的 index 位置后返回\n"
                "   （例如 items.insert(items.begin() + index, value); return items;）\n"
                "3. 点【自测】跑一次公开样例，看看通过了几条、错在哪一条\n"
                "4. 想一想：返回值对不对？换成越界的下标会发生什么？这些是下个阶段要解决的事\n\n"
                "热身阶段不要求做对，只要动过骨架、跑过一次自测就能进入下一阶段。"
                "注意不要在 solution.cpp 里写 main()——判题会另外生成一个 main。"
            ),
            "command": "",
            "checks": ["solution.cpp 编译通过", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
    }
```

在 `_IMPL_NOTES`（第 221 行）这个字典的结束大括号之后加同结构的 C++ 版（**4 空格缩进，仍在 `_course()` 内**）：

```python
    _IMPL_NOTES_CPP = {
        "1-1": (
            "C++ 要点：\n"
            "1. index 的合法范围是 0..items.size()（size() 本身合法，表示追加到末尾），"
            "越界就 throw std::out_of_range；\n"
            "2. 参数是按值传入的，函数体内的 items 已经是副本，但请明确写一行 "
            "std::vector<int> result = items; 再插入——把「不改动入参」写成代码，"
            "而不是依赖语言恰好帮你做到了；\n"
            "3. 插入用 result.insert(result.begin() + index, value)，"
            "不要用 push_back（那只能追加到末尾）；\n"
            "4. 注意 index 是 int，items.size() 是 size_t，比较前先 "
            "static_cast<int>(items.size())，避免有符号/无符号比较的坑。"
        ),
    }
```

并把第 374 行改成按语言选表：

```python
    notes_source = _IMPL_NOTES_CPP if language == "cpp" else _IMPL_NOTES
    impl_notes = notes_source.get(exercise_id, "")
```

（`language` 在 Step 2 已于第 164 行算好，这里直接可用。）

**Step 3 续：提示阶梯、AI 提示词与工具描述的 Python 措辞**

上面那条 `_localize_text` 扫描只覆盖 `stages` 的 `instruction` / `title` / `checks`，覆盖不到下面这些地方——它们各自硬编码了 `solution.py` 或「Python」：

**(a) `_stage_hints`（第 87 行，模块级函数）**：第 94-96 行的 `structure` 提示、第 106 行与第 109 行的 `first_llm_call` 提示写死了 `solution.py`，第 115 行写死了 `print`。改函数签名并替换这几处：

```python
def _stage_hints(stage_id: str, exercise: dict, targets: list[str], track: dict,
                 solution_file: str = "solution.py", language: str = "python") -> list[dict]:
```

```python
        texts = [
            f"本关只有一个文件 {solution_file}——不需要虚拟环境，也不需要 requirements.txt。",
            f"打开 {solution_file}，先看清目标函数的签名、参数顺序和返回值契约，这些不能改动。",
            f"如果找不到文件，确认项目根目录下 {solution_file} 存在且大小写完全一致。",
        ]
    elif stage_id == "doc_intro":
```

```python
        texts = [
            f"先别管函数签名，用最朴素的方式把这件事在 {solution_file} 里做一遍，怎么方便怎么来。",
            "写完点【自测】跑一次样例，看清每一步发生了什么，再回头看下面的现象描述对不对得上。",
            "这一步只求看懂现象，不必写成最终形态；正式实现留到下一阶段。",
            (
                "自测没有任何输出时，先确认目标函数已经 return，而不是仍然 throw 占位异常。"
                if language == "cpp"
                else "自测没有任何输出时，先确认目标函数已经 return，而不是仍然 raise NotImplementedError。"
            ),
        ]
```

`implementation` 分支第 115 行改成：

```python
            f"把上一阶段热身的写法改写成 {target_label} 函数：写死的输入换成参数，"
            + ("观察用的 std::cout 换成 return。" if language == "cpp" else "观察用的 print 换成 return。"),
```

**(b) 第 677-678 行的调用点**（`_localize_text` 那一层之后）改成：

```python
    for stage in stages:
        stage["hints"] = _stage_hints(
            stage["id"], exercise, targets, track,
            solution_file=solution_file, language=language,
        )
```

**(c) 两处 AI 提示词**：第 1778 行（AI 导师）与第 2207 行（能力答辩评分）都有同一句「Python 基础语法仅在它是根因时解释」。这两处是给 LLM 的系统提示，**不要改整段结构**，在各自拼装好、准备调用 LLM 之前加一行注入即可：

```python
    prompt = prompt.replace("Python 基础语法", f"{language_label} 基础语法")
```

（`language_label` 从 `course["language_label"]` 取；这两个函数里都能拿到 `course` 或 `exercise_id`。）

**(d) 面向 LLM 的工具描述与 docstring**（低风险，一起改掉以免 AI 被误导）：

| 行 | 现状 | 改成 |
|---|---|---|
| 1467 | `"""自测：拿当前 solution.py 跑一遍公开样例。` | `f"""自测：拿当前 {solution_file} 跑一遍公开样例。` |
| 1881 | `"文件路径，如 app.py, solution.py, requirements.txt"` | `f"文件路径，如 {solution_file}、README.md"` |
| 1931 | `"用当前 solution.py 跑一遍本关公开样例，返回逐条的输入、期望与实际结果。"` | `f"用当前 {solution_file} 跑一遍本关公开样例，…"` |
| 1973 | `"项目内相对路径，如 solution.py、src/tools.py"` | `f"项目内相对路径，如 {solution_file}"` |

（这几处都在已经能拿到 `course` / `solution_file` 的函数体内；若某一处拿不到，就把该函数的签名加上一个 `solution_file: str = "solution.py"` 参数并让调用方传 `course["solution_file"]`——不要为了改一句话去重排函数结构。）

- [ ] **Step 4: 让所有写盘/读盘的路径都按语言取文件名**

`lab_workspace_service.py` 里剩下每一处 `"solution.py"` 字面量都改成从 `course` 取。逐处对照（行号为改前）：

| 行 | 现状 | 改成 |
|---|---|---|
| 810 | `return {"solution.py": solution_code}`（`_canonical_passed_project_files`） | `return {_course_solution_file(course): solution_code}` |
| 820 | `solution = root / "solution.py"`（`_enrich_passed_stage_results`） | `solution = root / _course_solution_file(course)` |
| 996 | `target = root / "solution.py"`（`_carry_over_toolbox`） | `target = root / _course_solution_file(course)` |
| 1002 | `legacy = source_root / "solution.py"` | `legacy = source_root / lab_solution_file(previous)` |
| 1010 | `conventions = ["- 全部实现写在 \`solution.py\` 里…"]` | 见下方约定块 |
| 1013 | README 里的累积说明 | 见下方约定块 |
| 1048 | `solution = root / "solution.py"`（`_seed` 落骨架） | `solution = root / _course_solution_file(course)` |
| 1085 | `solution = root / "solution.py"` | `solution = root / _course_solution_file(course)` |
| 1336 | `snapshot["solution.py"] = solution_code` | `snapshot[_course_solution_file(course)] = solution_code` |
| 1351 | `(root / "solution.py").write_text(...)` | `(root / _course_solution_file(course)).write_text(...)` |
| 1346 | `(root / "repair_target.py").write_text(...)` | `(root / course.get("repair_target_file") or "repair_target.py").write_text(...)` |
| 1358 | 变式提示里的 `\`solution.py\`` | 用 `course.get("solution_file")` 拼进 f-string |
| 1475/1477/1496/1498 | `run_samples` / `submit_judge` 读写 `solution.py` | 用 `course` 的文件名，报错文案同理 |
| 1541/1543/1548/1550/1554/1555 | `first_llm_call` 分支 | 见 Step 5（整段重写） |
| 1562/1564 | `implementation` 分支的文件名 | 用 `course` 的文件名 |
| 1616/1624 | `acceptance` 分支 | 用 `course` 的文件名 |
| 1641 | `solution = root / "solution.py"` | 用 `course` 的文件名 |
| 2056/2058 | 自测工具的错误文案 | 用 `course` 的文件名 |
| 2309/2310 | `fallback_path` 猜测 | `fallback_path = course.get("solution_file") or "solution.py"` |

加一个取文件名的小助手（放在 `_localize_text` 旁边），让上面这些改法保持一致：

```python
def _course_solution_file(course: dict) -> str:
    """课程对象里的实现文件名。所有读写 solution.* 的地方都从这里取。"""
    return str(course.get("solution_file") or "solution.py")


def _language_label_of(course: dict) -> str:
    """课程对象里的语言显示名。"""
    return str(course.get("language_label") or "Python")
```

改完之后**扫一遍残留**，这一步比逐行核对可靠：

```bash
grep -n 'solution\.py' backend/services/lab_workspace_service.py
# ⚠️ 上面这条**不够**：它扫不出按扩展名分支的判据。再扫这两条：
grep -n 'endswith(\|\.py"\|\.cpp"\|suffix' backend/services/lab_workspace_service.py
```

**为什么必须加后两条**：字符串字面量 `solution.py` 与扩展名元组是两回事。
第 1865 行那句 `if item["path"].endswith((".py", ".txt", ".md")) and (mode == "agent" or item["path"] == active_file):`
里**根本没有 `solution.py` 这个子串**，所以第一条 grep 扫不到它——但它决定了
**AI 导师的代码上下文里是否会包含学生的实现文件**。只扫第一条的话，C++ 关卡下
`solution.cpp` 会被这个元组挡掉，学生问导师时导师看不到代码，而且**没有任何测试会红**。
——这不是假想：本计划的第一版清扫判据就只有第一条，是执行者交回后控制器复核才发现的。

剩下的命中只允许有三类：`_course_solution_file` / `_language_label_of` 里的默认值、注释与 docstring、以及 13 关通用模板（第 174 行那句注释）。**任何一处真实的读盘/写盘路径还带着 `solution.py` 都是 bug**——C++ 关卡会读写错文件，而且只在学生进到那一步才暴露。

**Step 4 补充（控制器在 T4 审查后追加）：扩展名判据按语言派生，并配一条会红的测试**

上面两条 grep 能**发现**扩展名元组，但发现之后还得改对。两处同类缺口（下面的行号是**当前文件**的，
不是本表「改前」行号——T4 已经动过这个文件）：

**(a) `ask_assistant` 拼 AI 导师代码上下文的筛选器（第 1865 行）**

```python
    solution_suffix = Path(_course_solution_file(course)).suffix  # ".py" / ".cpp"
    for item in _read_files(root):
        if item["path"].endswith((solution_suffix, ".txt", ".md")) and (mode == "agent" or item["path"] == active_file):
```

**必须从 `course` 派生，不要写 `if language == "cpp"` 的分支**：同一个筛选器对 13 关都生效，
按课程对象取后缀时 Python 关卡拿到的仍然是 `(".py", ".txt", ".md")`，行为逐字节不变。

**(b) `read_project_file` 的「可用文件」提示（第 2159 行）**

同一写法，但它手上是 `exercise_id` 而不是 `course`，直接用已经 import 进来的 `lab_solution_file`：

```python
        hint = ", ".join(
            f['path'] for f in _read_files(root)
            if f['path'].endswith((Path(lab_solution_file(exercise_id)).suffix, ".txt", ".md", ".json", ".yml", ".yaml", ".env", ".toml"))
        )
```

这一处只影响**错误提示里列出哪些文件名**——真正的读盘 `file_path.read_text()` 没有任何筛选，
所以 `read_project_file("solution.cpp")` 本来就读得到。它的问题是「导师被告知项目里只有 README.md」，
不是「读不到」。

**光靠 grep 不够：这一关必须新增一条会红的测试。**

第 1865 行这个缺口能穿过 T4 的验收，原因就是**验收手段只有 grep**——没有任何测试会因为
「AI 导师看不到 `solution.cpp`」而变红。所以把筛选逻辑抽成一个纯函数，然后测这个函数：

```python
def _tutor_code_snippets(files: list[dict], solution_file: str, mode: str, active_file: str) -> list[str]:
    """AI 导师能看到哪些项目文件。按本关的实现文件后缀派生，13 关共用同一套判据。"""
    suffix = Path(solution_file).suffix
    return [
        f"--- {item['path']} ---\n{redact_secrets(item['content'][:2500])}"
        for item in files
        if item["path"].endswith((suffix, ".txt", ".md")) and (mode == "agent" or item["path"] == active_file)
    ]
```

`ask_assistant` 里那个循环改成调用它（`snippets = _tutor_code_snippets(_read_files(root), _course_solution_file(course), mode, active_file)`）。
测试放进 `tests/test_lab_workspace_service.py`，两条断言：

- **C++ 关卡**（`solution_file="solution.cpp"`，文件含 `solution.cpp`、`README.md`、`notes.bin`）：
  agent 模式的结果**必须含 `solution.cpp`**，且不含 `notes.bin`；
- **Python 关卡**（`solution_file="solution.py"`，文件含 `solution.py`、`README.md`、`data.json`）：
  结果含 `solution.py` 与 `README.md`，且**不含 `data.json`**——这条把 Python 关卡的旧行为钉死，
  防止这次改动顺手把 13 个 Python 关卡放宽了。

再顺手修两处已经说不通的 docstring（都是同一次改动的产物）：
`_carry_over_toolbox` 的「把上一关通过后的 solution.py 带进本关」与
`_canonical_passed_project_files` 的「整个项目就是 solution.py」——两处代码都已经是按语言取文件名了。

`_seed` 的约定与 README（第 1010-1024 行）改成：

```python
def _seed(root: Path, course: dict, preserved_state: dict | None = None) -> None:
    solution_file = _course_solution_file(course)
    language_label = str(course.get("language_label") or "Python")
    conventions = [f"- 全部实现写在 `{solution_file}` 里，本关不需要其他文件"]
    if course.get("carries_from"):
        conventions.append(
            f"- 本关会在上一关（{course['carries_from']}）的 `{solution_file}` 基础上继续累积："
            "已经写好的函数请保留，不要删掉"
        )
    if str(course.get("language") or "python") == "cpp":
        conventions += [
            "- 判题会把你的 `solution.cpp` 和一份自动生成的 `main.cpp` 一起用 "
            "`g++ -std=c++17` 编译，编译不过就没有分数",
            "- 不要在自己的文件里写 `main()`，也不要改动函数的签名、参数顺序和返回值类型",
            "- 只用 C++17 标准库，不需要 CMake，也不需要安装任何第三方库",
        ]
    readme = (
        f"# {course['title']}\n\n"
        "这是你的独立实验项目。请跟随左侧阶段清单，从读题开始完成本关。\n\n"
        "## 项目目标\n\n"
        f"{course['description']}\n\n"
        "## 约定\n\n"
        + "\n".join(conventions)
        + "\n"
    )
```

（其余保持原样，包括 `_write_state`、`_carry_over_toolbox`、骨架落盘那几行——它们已在上面按语言改过。）

- [ ] **Step 5: `check_stage` 的分支按语言走**

`first_llm_call`（第 1540-1560 行）整段换成：

```python
    elif stage_id == "first_llm_call":
        solution_file = _course_solution_file(course)
        path = root / solution_file
        if not path.is_file():
            add(solution_file, False, f"请先创建 {solution_file}")
        else:
            source = path.read_text(encoding="utf-8")
            if str(course.get("language") or "python") == "cpp":
                # C++ 用「能编译」代替 ast.parse。热身阶段学生还没实现目标函数，
                # 一旦链接就会 undefined reference，所以只做 -fsyntax-only。
                from services.cpp_judge import compile_cpp_only

                compiled = compile_cpp_only(source)
                add(f"{solution_file} 编译", compiled["ok"],
                    "语法检查通过" if compiled["ok"] else compiled["error"])
            else:
                try:
                    ast.parse(source)
                    add(f"{solution_file} 语法", True, "AST 解析成功")
                except SyntaxError as exc:
                    add(f"{solution_file} 语法", False,
                        f"第 {exc.lineno or '?'} 行：{exc.msg}")
            starter = str(course.get("starter_code") or "").strip()
            moved = bool(source.strip()) and source.strip() != starter
            add("已写下你的热身代码", moved,
                f"{solution_file} 内容已超出初始骨架" if moved
                else f"请先在 {solution_file} 里用最朴素的方式把这件事做一遍，不必写成最终形态")
            state = _read_state(root)
            ran = bool(state.get("sample_run_at"))
            add("已运行过一次自测", ran,
                "已检测到自测运行记录" if ran
                else "点面板上的【自测】跑一次样例，观察现象后再进入下一阶段")
```

`implementation`（第 1561-1588 行）整段换成：

```python
    elif stage_id == "implementation":
        solution_file = _course_solution_file(course)
        language = str(course.get("language") or "python")
        path = root / solution_file
        if not path.is_file():
            add(solution_file, False, f"请先创建 {solution_file}")
        else:
            source = path.read_text(encoding="utf-8")
            names: set[str] = set()
            if language == "cpp":
                # C++ 不做名字扫描：目标函数没定义就是链接失败，judge 会连同
                # 编译错误一起报回来，比这里猜一遍更准。
                from services.cpp_judge import compile_cpp_only

                compiled = compile_cpp_only(source)
                add(f"{_language_label_of(course)} 语法", compiled["ok"],
                    "编译单元检查通过" if compiled["ok"] else compiled["error"])
                names = set(course["targets"]) if compiled["ok"] else set()
            else:
                try:
                    tree = ast.parse(source)
                except SyntaxError as exc:
                    add("Python 语法", False, f"第 {exc.lineno or '?'} 行：{exc.msg}")
                else:
                    add("Python 语法", True, "AST 解析成功")
                    names = {
                        node.name for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
            if language != "cpp":
                carried = set(course.get("carried_targets") or [])
                for target in course["targets"]:
                    if target in names:
                        add(target, True, "目标函数已定义")
                    elif target in carried:
                        add(target, False,
                            f"算法工具箱里还缺上一关的 {target}；"
                            f"请先完成上一关让它带过来，或者在本关把它一起补上")
                    else:
                        add(target, False, f"还没有定义 {target}")
            if all(target in names for target in course["targets"]):
                judged = judge_submission(exercise_id, source)
                if judged.get("compile_error"):
                    add("编译与链接", False, judged["compile_error"],
                        _judge_case_feedback(judged))
                add(
                    "核心函数行为", judged.get("passed", False), _judge_check_detail(judged),
                    _judge_case_feedback(judged),
                )
```

（`_language_label_of` 已在 Step 4 定义，直接用即可。`course["language_label"]` 在 Step 2 已写入返回值。）

**注意**：C++ 关卡在 `compile_cpp_only` 失败时 `names` 为空集，因此 `all(...)` 为假、不会调用判题器——避免一个语法错误的文件还去跑一遍完整编译。若编译单元检查通过但没实现目标函数（例如热身版把函数删了），`names` 被显式设成 targets，会进入判题器并拿到链接错误，学生看到的是 g++ 的原话而不是内部报错。

`acceptance`（第 1616-1624 行）只需把 `root / "solution.py"` 换成 `root / _course_solution_file(course)`，其余不动。

- [ ] **Step 6: `verify_lab_content.py` 的 `project_files` 断言按语言**

第 1470-1471 行改成：

```python
        expected_files = [lab_solution_file(exercise_id)]
        if course["project_files"] != expected_files:
            problems.append(f"project_files = {course['project_files']}，应为 {expected_files}")
```

并把函数内的导入（第 1458-1459 行）补上：

```python
    from services.agent_lab_specs import lab_solution_file
    from services.judge_service import load_flagship_exercises
    from services.lab_workspace_service import _course
```

- [ ] **Step 7: 改测试**

`backend/tests/test_lab_workspace_service.py`：

顶部（第 22-25 行）补：

```python
from services.agent_lab_specs import lab_repair_file, lab_solution_file

ALL_EXERCISE_IDS = [item["id"] for item in load_flagship_exercises()]
CORRECT_ARRAY_INSERT = REFERENCE_SOLUTIONS["1-1"]
# 1-1 已经改成 C++：文件名不再写死，测试也跟着关卡声明走，
# 否则「1-1 改语言」这件事会在测试里留下一串需要手工同步的字面量。
SOLUTION = lab_solution_file("1-1")
```

全文的 `"solution.py"` 按用途替换（共 20 处）：
- 作为 `save_file`/`delete_file`/`models.get` 的文件名（第 147、167、181、199、215、224、240、268、279、292、327、365、379 行）→ `SOLUTION`
- 第 62 行的 `{"path": "solution.py"}` → 保持字面量不变（它断言的是助手工具调用参数的重建，不是关卡文件名）
- 第 68-71 行 → 注释改成「一个 README 加一个带骨架的 solution.cpp」，`{"README.md", "solution.py"}` → `{"README.md", SOLUTION}`
- 第 80-81 行 → `assertIn("std::vector<int> array_insert", files[SOLUTION])` 与 `assertIn("std::logic_error", files[SOLUTION])`
- 第 89 行 → `self.assertEqual(course["project_files"], [SOLUTION])`
- 第 119 行 → `self.assertEqual(implementation["target_file"], SOLUTION)`
- 第 220 行 → `self.assertIn(SOLUTION, str(ctx.exception))`
- 第 391、432、459 行 → `files[SOLUTION]` / `assertIn(SOLUTION, files)`

把注入 Python 源码的用例换成能在 C++ 下编译的等价物：

第 178-183 与第 196-201 行（同两个测试）的
`"def array_insert(items, index, value):\n    return items + [value]\n"` 换成：

```python
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
```

第 236-242 行的热身用例同样换成 `WRONG_APPEND`。

第 266-272 行（`test_checker_reports_exact_missing_target`）改成测链接错误：

```python
    def test_checker_reports_a_link_error_when_the_target_is_missing(self):
        service.get_workspace(7, "1-1")
        # 编译单元检查能过（语法没问题），但目标函数没定义 → 链接失败。
        service.save_file(7, "1-1", SOLUTION, "int something_else() { return 1; }\n")
        result = service.check_stage(7, "1-1", "implementation")
        self.assertFalse(result["passed"])
        link = next(item for item in result["checks"] if item["label"] == "编译与链接")
        self.assertFalse(link["passed"])
        self.assertIn("array_insert", link["detail"])
```

第 274-288 行（`test_implementation_stage_rejects_a_function_with_no_behavior`）改成：

```python
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
```

第 292 行起的 `CORRECT_ARRAY_INSERT` 用法不用改（值现在是 C++ 参考解）。

第 379 行的 `"raise NotImplementedError\n"` 换成 `'#include <vector>\n#include <stdexcept>\n#include <string>\n\nstd::vector<int> array_insert(std::vector<int> items, int index, int value) { throw std::logic_error("未实现"); }\n'`。

第 354-360 行的进度测试里 `"environment"` 的注入保持不动（它测的是旧状态过滤）。

`backend/tests/test_guidance_context_service.py`：
- 第 46-51 行的 `save_file(..., "solution.py", "def array_insert(...): ...")` → 文件名 `"solution.cpp"`，内容换成 `"std::vector<int> array_insert(std::vector<int> items, int index, int value) { return {}; }\n"`
- 第 62 行 `assertIn("solution.py", result["project_files"])` → `assertIn("solution.cpp", result["project_files"])`
- 第 96 行与第 123 行的 `"solution.py"` 实参 → `"solution.cpp"`

- [ ] **Step 8: 跑工作区与上下文测试**

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -v
```

Expected: 全绿。若有失败，先看是不是漏掉了某一处 `"solution.py"` 字面量——`get_workspace(7, "1-1")` 的文件集应当是 `{"README.md", "solution.cpp"}`。

- [ ] **Step 9: 跑内容校验（含阶段表校验）**

```bash
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python scripts/verify_lab_content.py
```

Expected: 13 关全 `[PASS]`，阶段表校验 13 关全 `[PASS]`（1-1 的 `project_files` 现在是 `['solution.cpp']`，断言已按语言参数化）。

- [ ] **Step 10: 浏览器里确认 1-1 真的换了文件（本地）**

```bash
docker compose up -d --build
```

用 Playwright MCP：登录 `http://localhost:80`（demo / demo123）→ 打开 1-1 → 文件树应显示 `solution.cpp` → 阶段列表有 5 个阶段 → 点开 `solution.cpp` 应看到 C++ 骨架（此时编辑器还是 Python 高亮，Task 7 才换）。

**注意**：如果看到的是旧的 `solution.py`，说明工作区已经有内容、README/骨架不会刷新。这时的正确做法是重置工作区（删掉 `user-<id>/1-1` 让它重新 seed），不要以为是代码没生效。

---

### Task 5: 故障修复走 C++

**Files:**
- Modify: `backend/services/agent_lab_faults.py`
- Modify: `backend/services/capability_service.py`（兜底变异器按语言跳过 + 空故障时的学生可见文案）
- Modify: `backend/tests/test_capability_service.py`
- Modify: `backend/scripts/verify_lab_faults.py`（第 52 行的 `ast.parse` 按语言分流，见 Step 3）

**Interfaces:**
- Consumes: Task 4 的 `lab_language` / `lab_repair_file`。
- Produces: `curated_mutation_candidates("1-1", <C++ 参考解>)` 返回**三个**候选（都带 `(?!=)` 那条修正），
  至少一个能编译且被判为失败；非 C++ 关卡行为完全不变。

- [ ] **Step 1: 改写 1-1 的故障画像与变异候选**

`agent_lab_faults.py` 的 `FAULT_PROFILES["1-1"]` 改成 C++ 措辞：

```python
    "1-1": {
        "focus": "顺序表插入的下标边界与值语义",
        "root_cause": (
            "插入位置的边界判断被收紧成 index >= static_cast<int>(items.size())，"
            "导致「追加到末尾」这个合法调用被误判为越界。"
        ),
        "root_terms": ["array_insert", "index", "size", "out_of_range", "越界", "末尾"],
    },
```

**不要在这里加 `"language": "cpp"` 字段。** 语言只有一个来源：`agent_lab_specs.SPECS` 的 `language`
（经 `lab_language(exercise_id)` 读）。`agent_lab_faults.py` 现在**没有任何代码读 `language` 键**
（已 grep 确认），在这里放一份等于凭空造出第二个真相来源——将来 SPECS 改了、这里没改，
读代码的人会以为故障画像的语言是权威的。（本文件现有的 13 个画像一个 `language` 键都没有。）

`curated_mutation_candidates` 的 1-1 分支（第 103-107 行）换成：

```python
    if exercise_id == "1-1":
        # 边界收紧：合法的「追加到末尾」被当成越界。
        # 只匹配 "index >" 这一段、不把右边写进正则——学生可能写成
        # static_cast<int>(items.size()) / (int)items.size() / items.size()，
        # 把 RHS 一起写死就会漏掉其中那几种写法。
        #
        # ⚠️ (?!=) 这个否定断言是必须的，别省：合法写法里 `index >= 0` 很常见，
        # 而 `index\s*>\s*` 会匹配到 `index >=` 里的那个 `>`，把 `index >= 0`
        # 变成 `index >= = 0` —— 一份**编译不过的残骸**。更糟的是 _build_mutation
        # 只检查「判题是否不通过」，编译错误同样导致 passed=False，所以这份残骸
        # 会被当成一个「有效故障」收下，学生看到的是语法垃圾而不是逻辑 bug。
        candidates.append(_replace(code, r"index\s*>(?!=)\s*", "index >= "))
        # 位置偏移：无论要插到哪个位置都插到最前面，中间/末尾插入全错（仍然编译得过）。
        # 同样只匹配 ".begin() + index" 这一段，容器变量名叫什么都不影响。
        candidates.append(_replace(code, r"\.begin\(\)\s*\+\s*index", ".begin()"))
        # 异常类型替换：越界仍然被拦住，但抛的不是题目要求的 std::out_of_range，
        # 两条边界用例会失败。
        # 注意**不要**把这条说成「必然命中」：学生完全可能写 `using namespace std;`
        # 之后直接 `throw out_of_range(...)`，这样正则里的 `std::` 就匹配不上。
        # 控制器实测过一份这样的解（three 条候选全部落空）——见 Step 3 下面的说明。
        candidates.append(_replace(code, r"std::out_of_range", "std::runtime_error"))
```

原来那条「破坏不可变语义」被删掉了：按值签名下「返回入参本身」在 C++ 里根本改不动调用方（那是副本），注入不出可观察的故障，所以换成能真实抓到的位置偏移。

三条都**不带反向引用**，因此不依赖 `_replace` 的替换语法细节（第一条用了否定前瞻 `(?!=)`，
它不产生捕获组，替换串里不需要 `\1`）；`_build_mutation` 会逐条试判、只保留真能判失败的那条。

`_replace`（第 91-93 行）本身就是正则字符串替换，C++ 代码同样适用，不需要改。

- [ ] **Step 2: 兜底变异器按语言跳过（否则 C++ 代码会被 `ast.parse` 直接炸掉）**

`capability_service.py` 里两条兜底路径都只认 Python，对 C++ 必须整个跳过：

- `_force_mutation(exercise_id, code)`（`:640`）第 648 行就是 `tree = ast.parse(code)`，
  而且它后面的 `_ForceMutator`（`:670`）把 `return x` 改写成 `return [x]` / `str(x)`，
  全是 Python 语义。对 C++ 代码这里是**真的 `SyntaxError`**。
- `_mutation_candidates(code)`（`:432`）**并不是 AST 路径**——控制器核过：它全函数 **0 处 `ast.parse`**，
  是纯正则的 Python 惯用法匹配（浅拷贝 `copy.deepcopy(`、`list(...)` 之类）。
  它不会因为 C++ 语法而抛异常，**但这正是要跳过它的理由**：这些正则针对的是 Python 惯用法，
  套在 C++ 文本上要么一条都不中、要么在注释/巧合处误中，产出一个未必编译得过、
  更未必与知识点相关的「故障」。**别把它当成「反正不会崩所以留着也无妨」。**

所以门控加在**两者的共同上游** `_build_mutation`（`:619`）里，位置在 `curated_mutation_candidates` 循环之后、`_mutation_candidates` 之前。先在 `_build_mutation` 上方定义异常类：

所以门控加在**两者的共同上游** `_build_mutation`（`:619`）里，位置在 `curated_mutation_candidates` 循环之后、`_mutation_candidates` 之前。先在 `_build_mutation` 上方定义异常类：

```python
class NoMutationAvailable(ValueError):
    """本关找不到可注入的故障。C++ 关卡只有规则候选这一条路。"""
```

`_build_mutation` 改成（只插入中间那段分支，首尾两段保持原样）：

```python
def _build_mutation(exercise_id: str, code: str) -> tuple[str, str]:
    # 优先选择与本实验知识目标绑定的故障；只有学生写法无法命中时才使用通用兜底。
    for mutated, meta in curated_mutation_candidates(exercise_id, code):
        evaluation = _judge_exercise_code(exercise_id, mutated)
        if not evaluation["passed"]:
            return mutated, _encode_mutation_metadata(meta, evaluation)

    from services.agent_lab_specs import lab_language

    if lab_language(exercise_id) != "python":
        # 两条兜底路径都是 Python 专有：_force_mutation 直接 ast.parse（对 C++ 是
        # SyntaxError），_mutation_candidates 是 Python 惯用法的正则（不会崩，但套在
        # C++ 上产不出有意义的故障）。与其伪造一个并不存在的故障（学生会去找一个
        # 根本没有的 bug），不如此处如实中止。
        raise NoMutationAvailable(
            "本关暂无可注入的故障：你的实现写法没有命中本关的变异规则，"
            "请换一种等价写法再提交，或联系教师调整关卡。"
        )

    for mutated, description in _mutation_candidates(code):
        evaluation = _judge_exercise_code(exercise_id, mutated)
        if not evaluation["passed"]:
            return mutated, _encode_mutation_metadata(
                _generic_fault_profile(exercise_id, description), evaluation,
            )
    # 所有候选都未命中 → 强制注入一个底层故障，保证每道题都有真实的修复挑战
    mutated, description = _force_mutation(exercise_id, code)
    evaluation = _judge_exercise_code(exercise_id, mutated)
    return mutated, _encode_mutation_metadata(
        _generic_fault_profile(exercise_id, description), evaluation,
    )
```

再改调用点 `mark_code_passed`（`:747`）。**这条路径是真的会走到的**，不是理论分支——
控制器实测：一份**13/13 全过**的合法 C++ 写法（`using namespace std;` + `throw out_of_range(...)`、
边界写成 `index >= (int)items.size() + 1`、插入写成 `items.begin() + static_cast<size_t>(index)`）
让上面三条候选**全部落空**：

```
[实测] 这份解判题结果: passed = True | 13 / 13 | compile_error = None
       候选1(?!=)  命中 0 处    候选2  命中 0 处    候选3  命中 0 处
```

所以 `NoMutationAvailable` 必须被如实接住，**不能让它冒成 500**，也不能把它当成不会发生的事：

```python
    try:
        mutation_code, mutation_description = _build_mutation(row["exercise_id"], code)
    except NoMutationAvailable as exc:
        # 如实记录「本关没有故障」。学生确实通过了判题，不能因为我们的注入器
        # 找不到合适的故障就把他挡在答辩之外——那是工具的问题，不是他的。
        mutation_code = ""
        mutation_description = json.dumps(
            {"public": str(exc), "root_cause": ""}, ensure_ascii=False,
        )
```

**下游不是「已有的无故障分支」，得自己补。**（控制器核过：`mutation_code.strip()` 只在
`retry_repair`（`:1438`）里出现一次，`if not mutation_code.strip(): raise ValueError("当前会话没有可重新注入的故障代码")`
——它是**抛异常**，而且在**另一个函数**里，不是 `mark_code_passed` 的下游。）要补两处**面向学生**的话：

1. `retry_repair`（`:1448-1449`）那句 `ValueError` 的文案改成可行动的说明，别让前端显示
   「当前会话没有可重新注入的故障代码」这种内部口吻——例如
   `"本关没有可注入的故障，无需重复注入，请继续变式迁移"`。**保持是异常**（路由层照旧能呈现），
   不要改成静默通过——静默通过会让「重试」按钮看起来生效了却什么都没发生。
2. **修复阶段的工作区不能给学生一个空的 `repair_target.cpp`**。`repair_target` 的内容就是
   `mutation_code`，为空时学生看到的是一个空文件配「找出被注入的故障」的说明——这比没有故障更糟。
   在写这个文件的地方（Task 4 已把它改成 `repair_target.cpp`）对空内容写一行说明性注释，
   例如 `// 本关暂无可注入的故障：你的实现写法没有命中本关的变异规则。`。

**把这两处补完，并在报告里写清**：空故障时学生在修复阶段**实际看到**的是什么（贴出你实测的
`repair_target.cpp` 内容与 `retry_repair` 抛出的文案），不要只写「已处理」。

- [ ] **Step 3: 验证故障修复链路（脚本本身要先按语言改一处）**

`scripts/verify_lab_faults.py` 对每道关卡的每个候选断言三件事（脚本 docstring 里写着）：至少一条命中、
**注入后的代码语法合法**、注入后判题不通过。它的第 2 条是这么实现的（`:52`）：

```python
            try:
                ast.parse(mutated)
            except SyntaxError as exc:
```

**`ast.parse` 对 C++ 恒抛 `SyntaxError`**，所以直接跑，1-1 的每个候选都会被报成
「语法错误(...)」，而这个脚本的判定逻辑是「所有候选都必须『有效』」→ 1-1 必然 FAIL。
这不是「脚本对 1-1 有 Python 假设」这么含糊，就是这一行。

改法：把第 2 条按语言分流，**对 C++ 用真正的编译器**（比 `ast.parse` 更强，不是放宽）：

```python
            result = judge_submission(exercise_id, mutated) if language != "python" else None
            if language == "python":
                try:
                    ast.parse(mutated)
                except SyntaxError as exc:
                    failures.append(label); verdicts.append(f"#{index}=语法错误({exc.msg})"); continue
            elif result.get("compile_error"):
                failures.append(label); verdicts.append(f"#{index}=编译失败({result['compile_error'][:60]})"); continue
```

（实现细节可自行安排，例如把 `judge_submission` 提前到 `ast.parse` 之前只对 C++ 调用；
`language` 从 `services.agent_lab_specs.lab_language(exercise_id)` 取。
**「未改变代码」与「假故障(仍然全过)」这两条断言一个字都不要放宽**——它们与语言无关。）

然后：

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python scripts/verify_lab_faults.py
```

Expected: **13 关全 `[PASS]`**，其中 1-1 显示 3 个候选。若 1-1 出现 `[MISS]`，说明候选一条都没命中
参考答案——回去看 Step 1 的正则，不要放宽脚本。

**Step 3b（必做）：为刚才那个「残骸」缺陷补一条会红的测试。**

`index\s*>\s*` 会把合法写法 `index >= 0` 毁成 `index >= = 0`（编译不过），而 `verify_lab_faults.py`
**抓不到它**——那个脚本只跑**参考答案**，而参考答案里没有 `index >= 0`。所以这个缺陷只会在
真实学生代码上发作，测试全绿。补一条针对它的测试（放 `tests/test_capability_service.py`）：

```python
    def test_mutation_does_not_corrupt_a_legitimate_ge_zero_comparison(self):
        # 合法写法里 index >= 0 很常见；候选正则若匹配到 ">=" 里的那个 ">"，
        # 会把它毁成 "index >= = 0" —— 一份编译不过的残骸，而且 _build_mutation
        # 会因为「判题不通过」把它当成有效故障收下。
        code = (
            '#include <vector>\n#include <stdexcept>\n'
            'std::vector<int> array_insert(std::vector<int> items, int index, int value) {\n'
            '  if (index >= 0 && index > (int)items.size()) throw std::out_of_range("越界");\n'
            '  std::vector<int> result = items;\n'
            '  result.insert(result.begin() + index, value);\n'
            '  return result;\n'
            '}\n'
        )
        mutated, _meta = capability_service._build_mutation("1-1", code)
        result = capability_service._judge_exercise_code("1-1", mutated)
        self.assertIsNone(result.get("compile_error"), f"注入后的代码编译不过：\n{mutated}")
        self.assertFalse(result["passed"])
```

**并自证它不是假绿**：把 Step 1 的正则临时改回 `r"index\s*>\s*"`，确认这条测试**确实变红**
（报「编译不过」，因为 `index >= 0` 被毁掉了），再改回来。把这个实测结果写进报告。

- [ ] **Step 4: 改 `test_capability_service.py` 的 1-1 夹具**

**先看清楚：这个文件里没有 `CORRECT_SOLUTION` 常量，也没有 Python 参考解要换。**
（控制器核过，别去找。）它是**import 进来的**——第 13 行 `from tests.test_judge_service import CORRECT_SOLUTION`，
而 `test_judge_service.py:9-22` 的那份**已经是 C++ 参考解**（`std::vector<int> array_insert(std::vector<int> items, int index, int value)`，
断言 13/13 通过）。`correct_code()`（第 60-61 行）只是把它转发出来。
⇒ **这一项无事可做。** 不要在本文件里另立一个 `CORRECT_SOLUTION`（会遮蔽共享夹具、
让两份参考解各自漂移），也不要动 `test_judge_service.py`。

要改的只有下面三处按名字索引 1-1 文件的地方：

- 第 263 行 `save_file(self.user_id, "1-1", "solution.py", ...)` → 用 `lab_solution_file("1-1")`
- 第 292 行 `repair_files["repair_target.py"]` → `repair_files[lab_repair_file("1-1")]`
- **第 293 行** `repair_files["solution.py"]` → `repair_files[lab_solution_file("1-1")]`；
  **第 346 行** `restored_files["solution.py"]` → 同样用 helper 取。
  这两处都是从 `{item["path"]: item["content"]}` 里按名索引：1-1 的文件名变成 `solution.cpp`
  之后，`"solution.py"` 这个键不存在，报的是 **KeyError（测试报错）而不是断言失败**，
  排查时容易先怀疑判题。
- 第 451 行的 `"source": "solution.py"` 是事件负载里的普通字符串（那条测试只数条数），**不要动**
- 第 306-309 行的变式断言在 Task 6 里一起改

- [ ] **Step 5: 跑能力层测试**

```bash
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -p "test_capability_service.py" -v
```

Expected: 全绿（本任务只改了故障路径；变式相关断言若失败，说明 Task 6 还没做，属预期——先确认失败的只有变式那两条）。

---

### Task 6: 变式迁移走 C++，并删掉第三份判题 runner

**Files:**
- Modify: `backend/services/agent_lab_variants.py`
- Modify: `backend/services/capability_service.py`（`_judge_variant_code` 第 2009-2133 行、`_variant_starter_code` 第 1763-1804 行）
- Modify: `backend/scripts/verify_lab_content.py`（第 728 行起的 `REF_V_1_1` 换成 C++ 实现，见 Step 1b）
- Modify: `backend/tests/test_capability_service.py`（第 306-309 行）
- Test: `backend/tests/test_variant_learning_content.py`（跑现成的）

**Interfaces:**
- Consumes: Task 2 的 `run_cpp_judge`（经 `judge_service.judge_submission` 可达）、Task 4 的 `lab_solution_file`。
- Produces: `_judge_variant_code(code, variant_spec)` 在 `variant_spec["language"] == "cpp"` 时委派给 C++ 路径；Python 变式（其余 12 关）走原路径不变。删掉 `capability_service.py` 第 **2030-2133** 行的 `runner_code` 那份重复实现。

**范围是 2030-2133，以 Step 2 为准**（这里以前写过「2038-2107」，是旧稿的残留，**别用**）。
按错的窄范围删，`:2111` 的 `variant_runner.py` 与三处 `SAFE_BUILTINS` 会有一部分留下来，
Step 6 的期望值（第一条剩 1 处、第二条变 0）就对不上，而你会以为是判题链路的问题。
边界已实测：`:2111` 在删除范围内、`_run_custom_variant_harness`（`:2136`）的 `:2160` **不在**。

- [ ] **Step 1: 1-1 的变式改 C++**

`agent_lab_variants.py` 的 `ADDITIONAL_VARIANT_SPECS["1-1"]` 改成：

```python
    "1-1": {
        "target": "insert_interval",
        "language": "cpp",
        "cpp": {
            "signature": (
                "std::vector<std::vector<int>> insert_interval("
                "std::vector<std::vector<int>> intervals, std::vector<int> new_interval)"
            ),
            "includes": ["<vector>", "<stdexcept>", "<string>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "日程表场景。每个日程是一个 [start, end] 二元组，同一份日程表里的区间"
            "互不重叠且按 start 升序排好。现在有一个新日程 new_interval，请把它插入"
            "日程表并保持有序、互不重叠：\n"
            "1. 新日程与已有日程重叠（含端点相接）时，把它们合并成一个区间；\n"
            "2. 合并可能连锁发生，要一直合到不再重叠为止；\n"
            "3. 新日程落在所有日程之前或之后时，直接放进正确的位置；\n"
            "4. 日程表为空时，返回只含新日程的表格；\n"
            "5. 任何一个日程的 start 大于 end、或元素个数不是 2 时，"
            "抛出 std::invalid_argument。\n"
            "不得修改传入的任何容器，返回一份新的日程表。"
        ),
    },
```

这个字典还差两个字段，按同样的缩进（8 空格）补进去。先是 `hints`（原来的三条引导，措辞改成 C++ 契约）：

```python
        "hints": [
            {
                "level": 1, "title": "思考问题",
                "content": "两个日程在什么情况下算重叠？端点相接（前一个的 end 正好等于后一个的 start）算不算？先把定义写清楚再动手。",
            },
            {
                "level": 2, "title": "方向提示",
                "content": "先把新日程按 start 插进有序表，再从左往右扫一遍合并相邻区间，比一边找位置一边合并更好写。",
            },
            {
                "level": 3, "title": "检查清单",
                "content": "空表、插在最前、插在最后、被一个大区间完全包含、把多个区间串成一串、端点相接——六种都试过再提交；返回新容器，不要改动传入的 intervals。",
            },
        ],
```

然后是 `cases`（**13 条**，把原来考 Python 动态类型的「拒绝非整数端点」「拒绝布尔端点」「拒绝非列表」三条去掉，
换成 C++ 能表达的边界）：

```python
        "cases": [
            {"description": "插入到空日程表", "args": [[], [1, 3]], "expected": [[1, 3]]},
            {"description": "完全在已有的日程之前", "args": [[[5, 7]], [1, 2]], "expected": [[1, 2], [5, 7]]},
            {"description": "完全在已有的日程之后", "args": [[[1, 2]], [5, 7]], "expected": [[1, 2], [5, 7]]},
            {"description": "落在两个日程之间且不重叠", "args": [[[1, 2], [5, 7]], [3, 4]], "expected": [[1, 2], [3, 4], [5, 7]]},
            {"description": "与已有日程重叠时合并", "args": [[[1, 3], [6, 8]], [2, 7]], "expected": [[1, 8]]},
            {"description": "链式合并多个日程", "args": [[[1, 2], [4, 5], [7, 9]], [2, 8]], "expected": [[1, 9]]},
            {"description": "端点相接也要合并", "args": [[[1, 3], [5, 7]], [3, 5]], "expected": [[1, 7]]},
            {"description": "新日程完全覆盖已有日程", "args": [[[3, 4], [6, 7]], [1, 9]], "expected": [[1, 9]]},
            {"description": "新日程被已有日程完全包含", "args": [[[1, 9]], [3, 4]], "expected": [[1, 9]]},
            {"description": "落在首位并触发合并", "args": [[[3, 5], [8, 9]], [1, 4]], "expected": [[1, 5], [8, 9]]},
            {"description": "落在末位并触发合并", "args": [[[1, 2], [5, 6]], [6, 9]], "expected": [[1, 2], [5, 9]]},
            {"description": "拒绝 start 大于 end 的日程", "args": [[[1, 2]], [4, 3]], "exception": "invalid_argument"},
            {"description": "拒绝元素个数不是 2 的日程", "args": [[[1, 2, 3]], [4, 5]], "exception": "invalid_argument"},
        ],
```

**这里特意不放 `"immutable": True` 用例**，虽然原来的 Python 变式有一条「不得修改传入的日程表」。
原因是 C++ 下它**永远通过、不可能失败**，是一条「什么都不检查」的用例：

- 判题声明的签名是**按值**的 `std::vector<std::vector<int>> intervals`，学生函数拿到的是副本，
  **改不到 main.cpp 里那个 `a0`**；
- `cpp_judge.py:284-293` 自己就写着这件事：「mutated 在按值签名下**结构上永远为 false**……
  它现在零区分度：它对应的 immutable 用例在 C++ 下永远静默通过」；
  判题侧 `:474` 也只在 `payload.get("mutated")` 为真时才判失败——而它永远是假。
- 想让它真能失败，签名得改成引用，而那时**链接期就挂了**（判题声明的原型是按值）。

这与 Task 5 删掉「破坏不可变语义」那条变异是**同一个理由**（按值签名下改不动调用方），
两处必须一致，不能一个删一个留。「不得修改传入的容器」这条要求已经由**按值语义**保证，
`scenario` 文案里继续写着即可，不需要也不应该再用一条假用例去"验证"它。
（保留它还有个副作用：学生看到一条「不得修改传入的日程表 ✓」会以为自己被检查过了。）

`test_variants_are_single_target_without_agent_runners` 断言 `len(cases) >= 12`，13 条满足。

- [ ] **Step 1b: 变式的**参考答案**也要改成 C++（原计划漏了这一步）**

原来的「Task 6 范围」只写了变式规格，**漏了变式的参考答案**。它在
`scripts/verify_lab_content.py:1327` 的 `VARIANT_REFERENCE_SOLUTIONS` 里，`"1-1"` 指向 `REF_V_1_1`
（`verify_lab_content.py:728` 起），目前是**一份 Python 实现**（`def insert_interval(intervals, new_interval):`，
里面全是 `isinstance(item, list)` / `isinstance(start, bool)` 那套动态类型校验）。

变式规格一旦声明 `"language": "cpp"`，这份 Python 参考答案就会被拿去喂 C++ 判题器，
**编译不过**。具体会红三处（都在你 Step 5 要跑的命令里）：

| 位置 | 现象 |
|---|---|
| `scripts/verify_lab_content.py:1403` `run_variant_checks()` | `[FAIL] 变式 1-1 0/13` + 编译错误 → 脚本**退出码非 0** |
| `tests/test_variant_learning_content.py:41` `test_every_variant_reference_solution_passes` | 1-1 断言失败 |
| `tests/test_capability_service.py:147`（拿 `VARIANT_REFERENCE_SOLUTIONS["1-1"]` 当提交） | 该测试失败 |

把 `REF_V_1_1` 换成 C++ 的 `insert_interval`（**与上面 13 条用例逐条对齐**）：

```python
REF_V_1_1 = '''
#include <vector>
#include <stdexcept>
#include <string>

std::vector<std::vector<int>> insert_interval(
    std::vector<std::vector<int>> intervals, std::vector<int> new_interval) {
  // 先整体校验，再合并：两条非法用例分别考「新日程非法」与「已有日程非法」，
  // 所以两边都要过一遍。
  auto validate = [](const std::vector<int>& item) {
    if (item.size() != 2) throw std::invalid_argument("区间必须是长度为 2 的容器");
    if (item[0] > item[1]) throw std::invalid_argument("区间起点不能大于终点");
  };
  for (const auto& item : intervals) validate(item);
  validate(new_interval);

  // 按 start 插进有序表；start 相同时插在后面也无妨——它们必然重叠，会合并。
  std::vector<std::vector<int>> ordered;
  bool placed = false;
  for (const auto& item : intervals) {
    if (!placed && new_interval[0] < item[0]) {
      ordered.push_back(new_interval);
      placed = true;
    }
    ordered.push_back(item);
  }
  if (!placed) ordered.push_back(new_interval);

  // 从左往右合并相邻区间：后一个的 start 小于等于前一个的 end 就并（端点相接也算）。
  std::vector<std::vector<int>> merged;
  for (const auto& interval : ordered) {
    if (!merged.empty() && interval[0] <= merged.back()[1]) {
      if (interval[1] > merged.back()[1]) merged.back()[1] = interval[1];
    } else {
      merged.push_back(interval);
    }
  }
  return merged;
}
'''
```

写的时候注意两点：
- **不要用 `std::sort`**：那要 `#include <algorithm>`，而本关 `cpp.includes` 里没有它。
  手动插入位置既避开这个问题，也更贴合「插入有序表」这个考点。
- `intervals` 是**按值**传参，所以「不得修改传入的容器」自动成立——这正是 Step 1 里
  不放 `immutable` 用例的原因，两者是同一件事的两面。

`scripts/verify_lab_content.py` 的 `Files` 也要补上（原计划只写了 Modify 另外两个文件）。

- [ ] **Step 2: `_judge_variant_code` 改为委派（**先把安全检查按语言分流**，否则这整步是死代码）**

⚠️ **这一步有个前置改动，漏了的话下面所有工作都不会生效。**

`_judge_variant_code` 的**开头**（`:2013-2020`，在你要替换的那段**之前**）无条件调了一次
`_policy_error(code)`：

```python
    from services.judge_service import _policy_error
    policy_error = _policy_error(code)
    total = len(variant_spec.get("cases", []))
    if policy_error:
        return {"passed": False, "total": total, "passed_count": 0,
                "compile_error": policy_error, "results": []}
```

而 `_policy_error`（`judge_service.py:53-57`）第一件事就是 `ast.parse(code)` —— 对 C++ 代码
**必然**返回 `"语法错误：第 1 行，invalid syntax"`（`#include <vector>` 在 Python 里是注释后面跟语法错误）。
⇒ **每一份 C++ 变式提交都会在这里被挡掉**，带着一条莫名其妙的「语法错误」，
根本走不到你新写的委派。**失败现象会被误读成「C++ 判题没接通」，其实是这一行。**

正课路径早就解决过同一个问题：`judge_service._run_judge`（`:475`）把 C++ 分发放在
`_policy_error` **之前**。这里照做——**安全检查按 spec 的语言分流**：

```python
    # 安全检查只对 Python 生效：_policy_error 是 AST 实现的 Python 模块白名单，
    # 对 C++ 必然报「语法错误」。C++ 有自己的最小安全扫描（cpp_policy_error），
    # 由 run_cpp_judge 在内部执行，不会漏掉。
    if str(variant_spec.get("language") or "python") == "python":
        from services.judge_service import _policy_error
        policy_error = _policy_error(code)
    else:
        policy_error = None
    total = len(variant_spec.get("cases", []))
    if policy_error:
        return {
            "passed": False, "total": total, "passed_count": 0,
            "compile_error": policy_error, "results": [],
        }
```

（`cpp_policy_error` 确实在 C++ 路径内部生效，不是「跳过了检查」：`run_cpp_judge`（`cpp_judge.py:567`）
开头就是 `policy_error = cpp_policy_error(code)`，命中即 `_fail(...)`。）

**然后**才是替换：把 `capability_service.py` 第 2030-2133 行（从 `# 构建临时判题脚本`
到那段 `try/except subprocess.TimeoutExpired/except Exception as exc` 的结尾，即那份完整的
`runner_code` 与它的执行）整段删掉，换成：

```python
    # 变式判题直接走正课那条语言感知的路径：判题器、比对方式、用例形态三者
    # 只有一份实现。原先这里手抄过一份 Python runner，注释里写着「必须与
    # judge_service.RUNNER 的能力集一致」——靠人工同步的东西迟早会漂。
    from services.judge_service import _with_case_views, _run_judge

    outcome = _run_judge(code, variant_spec, total, timeout=10)
    outcome = _with_case_views(outcome, cases)
    if outcome.get("compile_error"):
        return {
            "passed": False, "total": outcome["total"], "passed_count": 0,
            "compile_error": outcome["compile_error"], "results": [],
        }
    results = [
        {
            "case_index": item["case_index"] if "case_index" in item else index,
            "description": item["description"],
            "passed": item["passed"],
            "error": item.get("detail") or None,
            "duration_ms": item.get("duration_ms"),
        }
        for index, item in enumerate(outcome.get("results", []), 1)
    ]
    passed_count = sum(1 for item in results if item["passed"])
    return {
        "passed": passed_count == len(results) and bool(results),
        "total": len(results), "passed_count": passed_count,
        "compile_error": None, "results": results,
    }
```

`_run_judge(code, spec, expected_total, timeout)` 的第 3 个参数是「用例总数」，传 `total`（= `len(variant_spec["cases"])`）；返回值里 `total` 会被 `_with_case_views` 覆盖成 `len(cases)`，两者一致，因此下游的 `passed_count` / `total` 语义不变。

`_run_judge` 要求 spec 带 `language`（缺省 python）与 `target`——变式 spec 现在两者都有。

三点补充（控制器核过，省得你现场再判断）：

- **不要给这段补 try/except。** 被你删掉的那段自己包了 `except subprocess.TimeoutExpired` 与
  `except Exception`，而 `_run_judge` **内部已经有两层同样的兜底**（`judge_service.py:521-528`），
  超时与异常都被转成带 `compile_error` 的返回体，**不会往外抛**。再加一层是死代码。
- 用到的 `total`（`:2016`）、`target`（`:2031`）、`cases`（`:2032`）在删除段之前就已定义，
  直接可用；`cases` 在替换后的新代码里只用于 `_with_case_views(outcome, cases)`。
- **变式的用例不要用 `fresh_result`**：C++ 路径对它直接抛 `CppContractError`
  （`cpp_judge.py:472`，按身份比较无法直译）。Step 1 给的 13 条用例里没有，保持这样。

- [ ] **Step 3: 变式骨架按语言生成**

`_variant_starter_code`（第 1763-1804 行）在最后的兜底 return 之前加 C++ 分支：

```python
    if str(variant_spec.get("language") or "python") == "cpp":
        signature = str((variant_spec.get("cpp") or {}).get("signature") or "").strip()
        if not signature:
            raise ValueError(f"变式 {variant_spec.get('target')} 声明了 cpp 却没有签名")
        return (
            "/* 变式迁移独立实现区。\n\n"
            "   请根据 VARIANT_TASK.md 中的新业务场景和输入输出契约完成下面这个函数。\n"
            "   不得修改签名——判题会按这个签名调用你的实现。 */\n\n"
            '#include <vector>\n#include <stdexcept>\n#include <string>\n\n'
            f"{signature} {{\n"
            '  throw std::logic_error("请完成变式迁移实现");\n'
            "}\n"
        )
```

- [ ] **Step 4: 改 `test_capability_service.py` 的变式断言（第 306-309 行）**

```python
        variant_files = {item["path"]: item["content"] for item in variant["workspace"]["files"]}
        self.assertIn("VARIANT_TASK.md", variant_files)
        self.assertIn(
            "insert_interval",
            variant_files[lab_solution_file("1-1")],
        )
        # 1-1 的变式现在也是 C++：骨架必须是签名，不能再是 def 语句
        self.assertIn("std::vector<std::vector<int>>", variant_files[lab_solution_file("1-1")])
        self.assertNotIn("def insert_interval", variant_files[lab_solution_file("1-1")])
        self.assertIn("把单个区间插入已有日程", variant_files["VARIANT_TASK.md"])
```

- [ ] **Step 5: 跑变式与能力层测试**

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -p "test_variant_learning_content.py" -v
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -p "test_capability_service.py" -v
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -m unittest discover -s tests -v
```

Expected: 全绿。

- [ ] **Step 6: 确认第三份 runner 真的没了**

改之前先记下基线（控制器已实测，你复核一下对不对）：

```bash
grep -n "variant_runner.py" backend/services/capability_service.py   # 改动前：2111 与 2160 两处
grep -c "SAFE_BUILTINS" backend/services/capability_service.py       # 改动前：3
```

改完再跑同样两条，**期望值不是「无输出」也不是「少 1」**：

```bash
grep -n "variant_runner.py" backend/services/capability_service.py
grep -c "SAFE_BUILTINS" backend/services/capability_service.py
```

- 第一条 **应当只剩 1 处，在 `:2160` 附近**——那是 `_run_custom_variant_harness` 里的另一条私有路径，
  **本任务明确不动**。（`variant_runner.py` 在改动前有**两**处：`:2111` 在你删掉的块里，`:2160` 不在。
  所以「无输出」是个错的期望；按它判，你会以为没改干净、甚至可能顺手把 `:2160` 也删了——
  那就动了一条不归你的私有路径。）
- 第二条 **应当变成 0**——三处（`:2041` / `:2065` / `:2084`）**全部**在那个 `runner_code` 里，
  整块删掉就一个都不剩。不是「少 1」。

把改动前后的实测数字都记在任务小结里。**如果第一条剩下的是 2 处或 0 处，停下报控制器**——
2 处说明删除块没找准范围，0 处说明你误删了 `_run_custom_variant_harness` 里的那处。

---

### Task 7: 前端 C++ 支持

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`
- Modify: `frontend/src/views/CodeLab.vue`
- Modify: `frontend/src/components/LabFileTree.vue`
- Modify: `frontend/src/config/flagshipExercises.js`

**Interfaces:**
- Consumes: 后端的 `course.language` / `course.language_label` / `course.solution_file` / `course.repair_target_file`（Task 4 已下发）。
- Produces: 1-1 的编辑器是 C++ 语法与补全；前端不再出现任何写死的 `solution.py` / `repair_target.py`。

- [ ] **Step 1: 装 C++ 语言包**

```bash
cd student/frontend && npm install @codemirror/lang-cpp@^6.0.2 --package-lock-only --no-audit --no-fund
```

**`--package-lock-only` 是控制器实测后加的，别去掉。** 这个仓库的宿主**没有 `node_modules`**
（依赖是 Docker 构建期 `npm ci` 装的，本地从不装），所以裸 `npm install` 会为了改两个文本文件
把整棵依赖树下载下来（几分钟）。`--package-lock-only` 只写 `package.json` + `package-lock.json`，
**实测 484ms**，且因为 Docker 走的是 `npm ci`（只读锁文件），本地不需要 `node_modules`。

Expected（控制器在临时副本上实测过，**这是真实的产出形状，不是示意**）：
- `package.json` 的 `dependencies` 里出现 `"@codemirror/lang-cpp": "^6.0.3"`
  （写 `^6.0.2` 会解析到当前最新的 **6.0.3**——registry 实测可解析，caret 范围内，正常）；
- `package-lock.json` 增加 **3 个块 / 约 22 行变更**：根 `dependencies` 一条、
  `node_modules/@codemirror/lang-cpp`、以及它带进来的传递依赖 **`node_modules/@lezer/cpp`**。
  **审查者注意：`@lezer/cpp` 是 `lang-cpp` 的正常传递依赖，不是无关改动。**
- `"lockfileVersion": 3` **保持不变**（npm 11 没有借机重写锁文件）；
- 新条目的 `resolved` 指向 `registry.npmmirror.com`，与本文件**其余 279 条**一致
  （已 `grep` 确认全仓锁文件只用这个镜像），不是引入第二个源。

**`package-lock.json` 必须一起改，这不是「顺手」而是硬要求**：`frontend/Dockerfile` 是
`COPY package.json package-lock.json ./` 然后 **`RUN npm ci`**——`npm ci` 在两者不一致时
**直接报错退出**（`can only install packages when your package.json and package-lock.json are in sync`），
前端镜像就构建不出来，`docker compose up -d --build` 会整个失败，Task 8/9 都做不下去。
所以这一步不能只手改 `package.json`。

改完自查一条，确认锁文件真的写进去了：

```bash
grep -c '"node_modules/@codemirror/lang-cpp"' student/frontend/package-lock.json
```

Expected: `1`（不是 `0`）。本项目无 git，「两个文件都要改」指**两个文件都要上传到线上**。

- [ ] **Step 2: `CodeLab.vue` 的语言识别与补全**

第 675 行旁加导入：

```js
import { cpp } from '@codemirror/lang-cpp'
```

`languageFor`（第 959-966 行）与 `fileKind`（第 968-974 行）各加一条：

```js
  if (path.endsWith('.cpp') || path.endsWith('.cc') || path.endsWith('.hpp') || path.endsWith('.h')) return 'cpp'
```

`fileLabel`（第 976-979 行）加一项：

```js
  return { python: 'Py', cpp: 'C++', markdown: 'M↓', env: '⚙', json: '{}', text: '≡' }[kind]
```

在 `pythonCompletionSource`（第 1164-1175 行）之后加一份 C++ 补全：

```js
const cppCompletionSource = completeFromList([
  snippetCompletion('#include <${header}>\n', { label: '#include', detail: '引入头文件', type: 'keyword' }),
  snippetCompletion('for (int ${i} = 0; ${i} < ${n}; ++${i}) {\n\t${pass}\n}', { label: 'for', detail: '计数循环', type: 'keyword' }),
  snippetCompletion('for (${item} : ${items}) {\n\t${pass}\n}', { label: 'range-for', detail: '范围遍历', type: 'keyword' }),
  snippetCompletion('if (${condition}) {\n\t${pass}\n}', { label: 'if', detail: '条件分支', type: 'keyword' }),
  snippetCompletion('throw std::out_of_range("${message}");', { label: 'throw', detail: '抛出越界异常', type: 'keyword' }),
  ...['return', 'break', 'continue', 'const', 'auto', 'true', 'false', 'nullptr', 'int', 'size_t']
    .map(label => ({ label, type: 'keyword' })),
  ...['items.size()', 'items.push_back()', 'items.insert(items.begin() + , )', 'items.empty()', 'static_cast<int>()', 'std::vector<int>']
    .map(label => ({ label, type: 'function', apply: label.endsWith(')') ? label : `${label}` })),
])
```

`languageExtension`（第 1177-1189 行）加分支：

```js
  if (language === 'cpp') {
    const support = cpp()
    return [support, support.language.data.of({ autocomplete: cppCompletionSource })]
  }
```

补全 override（第 1220 行）从「只认 .py」改成按语言分派：

```js
          override: [context => {
            const language = languageFor(activePath.value)
            if (language === 'python') return pythonCompletionSource(context)
            if (language === 'cpp') return cppCompletionSource(context)
            return null
          }],
```

- [ ] **Step 3: `CodeLab.vue` 里不再写死文件名**

在 `<script setup>` 顶部（`const hasSolution` 附近，第 832 行）加两个 computed：

```js
// 文件名由后端按关卡语言下发（1-1 是 solution.cpp），前端不再猜扩展名。
const solutionFile = computed(() => course.value?.solution_file || 'solution.py')
const repairTargetFile = computed(() => course.value?.repair_target_file || 'repair_target.py')
const languageLabel = computed(() => course.value?.language_label || 'Python')
```

`hasSolution`（第 832 行）改成 `files.value.some(file => file.path === solutionFile.value)`。

`insertStarter`（第 1501-1515 行）改成：

```js
async function insertStarter() {
  const target = solutionFile.value
  const existing = models.get(target)
  if (existing?.getValue().trim()) {
    try { await ElMessageBox.confirm(`${target} 已有内容，是否用本关函数骨架覆盖？`, '插入骨架', { type: 'warning' }) }
    catch (_) { return }
  }
  await saveLabFile(exerciseId.value, target, course.value.starter_code || '')
  if (existing) existing.setValue(course.value.starter_code || '')
  else {
    files.value.push({ path: target, content: course.value.starter_code || '' })
    models.set(target, new LabTextModel(course.value.starter_code || '', languageFor(target)))
  }
  dirtyFiles.delete(target)
  openFile(target)
}
```

其余逐处替换（行号为改前）：

| 行 | 现状 | 改成 |
|---|---|---|
| 90 | `\|\| 'Python 基础'` | `\|\| '编程基础'` |
| 223 | `修复 solution.py 后，填写根因说明并提交判题` | `修复 {{ solutionFile }} 后，填写根因说明并提交判题` |
| 233 | `完成 solution.py 中的变式代码后…` | `完成 {{ solutionFile }} 中的变式代码后…` |
| 256 | `v-if="activePath?.endsWith('.py')"` + `title="显示 Python 代码提示"` | `v-if="hasCompletionTips"` + `:title="'显示 ' + languageLabel + ' 代码提示'"` |
| 266-267 | 写死的 `solution.py` 与 `openFile('solution.py')` | `{{ solutionFile }}` 与 `openFile(solutionFile)` |
| 511 | `请在 <b>solution.py</b> 中实现…` | `请在 <b>{{ solutionFile }}</b> 中实现…` |
| 560 | `不考查基础 Python 语法` | `不考查基础 {{ languageLabel }} 语法` |
| 1346 | `files.value.find(file => file.path.endsWith('.py'))` | `files.value.find(file => file.path === solutionFile.value) \|\| files.value.find(file => file.path.endsWith('.py'))` |
| 1436 | 恢复提示里的 `solution.py` | `{{ solutionFile }}`（同段文字一并改） |
| 1441 | `repair_target.py`（两处） | `repairTargetFile` |
| 1446 | `生成独立的 solution.py 骨架` | `生成独立的 {{ solutionFile }} 骨架` |
| 1482-1483 | `'repair_target.py'` | `repairTargetFile.value` |
| 1488 | `在全新的 solution.py 中完成` | `在全新的 {{ solutionFile }} 中完成` |
| 1950-1951 | `'repair_target.py'` | `repairTargetFile.value` |
| 1972 | `已写入 repair_target.py（solution.py 未受影响）` | `已写入 ${repairTargetFile.value}（${solutionFile.value} 未受影响）` |
| 1989 | `models.get('solution.py')` | `models.get(solutionFile.value)` |
| 2023-2024 | `models.get('solution.py')` / `'没有找到 solution.py'` | `models.get(solutionFile.value)` / `` `没有找到 ${solutionFile.value}` `` |
| 2145 | `models.get('repair_target.py')` \|\| `models.get('solution.py')` | `models.get(repairTargetFile.value)` \|\| `models.get(solutionFile.value)` |
| 2221 | `.tab-dot.python{color:#59a9ff}…` | 追加 `.tab-dot.cpp{color:#6ec7a8}` |

第 256 行的 `v-if` **要改成**下面这个新增的 computed（表格第 256 行那条列的就是这处改动，
这里给出它的定义）。**注意 `hasCompletionTips` 现在还不存在**——`activePath?.endsWith('.py')`
是写死在模板里的，你要**新建**这个 computed **并**把第 256 行的 `v-if` 换成它：

```js
const hasCompletionTips = computed(() => ['python', 'cpp'].includes(languageFor(activePath.value || '')))
```

**只加 computed 而不改第 256 行，等于什么都没做**：1-1 的「代码提示」按钮会因为 `v-if` 里的
`.py` 而不渲染，Step 6 第 4 项「点『代码提示』按钮不报错」也就无从点起、**自动通过**。
（同一条的 `title="显示 Python 代码提示"` 也要按表格改成 `:title="'显示 ' + languageLabel + ' 代码提示'"`，
否则 C++ 关卡上按钮写着「显示 Python 代码提示」。）

**注意**：第 1441、1482、1950 行所在的 `ElMessageBox.confirm` 与提示都是模板字符串或对象字面量，替换时确认引号配平；改完必须 `npm run build` 通过。

- [ ] **Step 4: `LabFileTree.vue`**

**先看清楚这个文件里没有 `LABELS` 常量**（已核：全文件 grep 无此标识符）——
`fileLabel`（第 67-71 行）返回的是一个**内联对象字面量**，`fileKind`（第 58-65 行）是一串 `if`。
所以要改的是这两处本身，不是某个叫 `LABELS` 的东西。

三处改动，**扩展名必须与 CodeLab.vue 的 `languageFor` 逐字一致（是四个，不是三个）**：

1. `fileKind`（第 59 行那条 `if` 之前或之后）加一条：

```js
  if (path.endsWith('.cpp') || path.endsWith('.cc') || path.endsWith('.hpp') || path.endsWith('.h')) return 'cpp'
```

（CodeLab.vue 的 `languageFor` 认的正是这四个后缀。**两边不一致会导致文件树图标与编辑器语法
对同一个文件给出不同判断**——比如 `.h` 在编辑器里是 C++、在文件树里是「文本」。）

2. `fileLabel` 的内联对象（第 69 行）加 `cpp: 'C++'`：

```js
    python: 'Py', cpp: 'C++', markdown: 'M↓', env: '⚙', json: '{}', yaml: 'Y', text: '•',
```

3. 第 26 行的虚拟条目标签改成按路径判断：

```html
<span v-if="entry.virtual" class="lab-tree-tag">{{ entry.path.endsWith('.cpp') ? 'C++' : 'Python' }}</span>
```

4. **还要补一条 CSS**（第 75 行那一大行里）：第 23 行是
`<span v-else :class="['lab-tree-file-icon', fileKind(entry.path)]">`，即图标颜色由
`lab-tree-file-icon.<kind>` 决定，而样式块里**没有 `.cpp` 这一条**——
不补的话 C++ 关卡的图标会**没有颜色**（回落到 `.lab-file-tree` 的 `#b8c2d1`），
与旁边的 `Py` / `M↓` 明显不一致，而功能上不报任何错。在
`.lab-tree-file-icon.python{color:#50b8d8}` 后面接一条：

```css
.lab-tree-file-icon.cpp{color:#6ec7a8}
```

（色值取 CodeLab.vue 里 `.tab-dot.cpp` 那条 `#6ec7a8`，两边保持同色。）

- [ ] **Step 5: `flagshipExercises.js` 的阶段一描述**

第 9 行改成：

```js
    description: '从顺序表开始，用标准库实现线性结构与基础容器。第 1-1 关用 C++ 试点，其余关卡用 Python；同一语言的关卡之间会把函数收进「算法工具箱」复用。',
```

- [ ] **Step 6: 构建并做浏览器验证**

```bash
cd D:/code/innovational-competition && docker compose up -d --build
```

Playwright MCP（`http://localhost:80`，demo/demo123）逐项确认：
1. 1-1 文件树显示 `solution.cpp`，图标是 `C++` 标签**且该图标有颜色**（对应 `.lab-tree-file-icon.cpp` 那条 CSS）
2. 打开 `solution.cpp`，编辑器状态栏显示 `CodeMirror · cpp`
3. 按 Ctrl+Space 出现 C++ 补全（含 `items.insert(...)`）
4. **「代码提示」按钮在 1-1 上必须看得见**，点击后出现补全候选且不报错

   ⚠️ **这一项不能只写「不报错」**：按钮的 `v-if` 若还留着 `.py`，它在 C++ 关卡根本不渲染，
   「点它不报错」就成了一条**永远不会失败**的检查（同 Task 6 删掉 `immutable` 用例的理由）。
   判据是**按钮存在**；按钮不在，就是 Step 3 第 256 行那处没改。
5. 欢迎页文案是「打开 solution.cpp 写下你的实现」
6. 故障修复的确认弹窗提到 `repair_target.cpp`
7. 变式迁移的提示提到 `solution.cpp`
8. 打开 1-2（Python 关），上述每一处仍是 `solution.py` / `Python`
9. 控制台无 JS 错误

Expected: 全部符合。第 8 项是防回归的关键——本地化必须只影响 C++ 关卡。

---

### Task 8: 本地端到端验收

**Files:** 无代码改动（发现问题再回到对应任务修）。

**Interfaces:**
- Consumes: Task 1-7 的全部产物。
- Produces: 一份 E2E 结论，作为 Task 9 生产部署的放行条件。

- [ ] **Step 1: 干净工作区**

先让 1-1 重新 seed（非空工作区的 README / 骨架永不刷新）。

**但先确认容器里生效的 `flagship_exercises.json` 是新版**——`/app/data` 是命名卷，
卷里那份盖住镜像里烘进去的那份，`docker compose up -d --build` **不会**刷新它。
若 Task 3 当时没 `docker cp` 进去，这里就会对着旧关卡内容做 E2E，而且一路「通过」：

```bash
md5sum student/backend/data/flagship_exercises.json
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend sh -c 'md5sum /app/data/flagship_exercises.json'
```

两个 md5 必须相同；不同就补一次（写的是卷，不用重启后端）：

```bash
MSYS_NO_PATHCONV=1 docker cp student/backend/data/flagship_exercises.json ai-learning-backend:/app/data/flagship_exercises.json
```

然后再让 1-1 重新 seed：

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend python -c "
import shutil, pathlib
from services.lab_workspace_service import WORKSPACE_ROOT
target = pathlib.Path(WORKSPACE_ROOT) / 'user-1' / '1-1'
if target.exists():
    shutil.rmtree(target)
print('reset:', target, 'exists =', target.exists())
"
```

（`user-1` 是 demo 账号的 id。若实际不是 1，先用 `get_progress_overview` 或数据库确认 demo 的 id，再删对应的目录。）

- [ ] **Step 2: 五阶段逐个走通**

Playwright MCP，`http://localhost:80`，demo / demo123，进入 1-1：

1. **文档讲解入门** → 点「AI 检查本阶段」（若本地未配置 AI Key，本阶段应给出明确的「未配置」提示而不是报错；这不影响后续阶段）
2. **确认题目文件** → 文件树有 `solution.cpp` 与 `README.md`，检查通过
3. **跑通第一段顺序表操作**（first_llm_call）→ 把热身版的朴素实现写进 `solution.cpp`，点【自测】，检查通过
4. **实现顺序表插入函数** → 粘贴 C++ 参考解（见下方），点「AI 检查本阶段」，应报「编译与链接」+「核心函数行为」双绿、13/13
5. **AI 工程验收** → 通过

用于第 4 步的参考解（与 `verify_lab_content.py` 的 `REF_1_1` 一致）：

```cpp
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
```

Expected: 5/5 阶段完成，进度显示 `5/5`。

- [ ] **Step 3: 自测与提交评测都要有 13 条行结构**

点【自测】：3 条公开样例全绿，评测面板「实际」列与「期望」列逐行可读。
点【提交评测】：17 → **13** 行（其中 10 条隐藏），全部通过，`通过 13/13`。

- [ ] **Step 4: 故意失败，检查编译错误与失败用例的可读性**

把参考解改成有语法错误的版本（例如删掉一个 `}`），点「AI 检查本阶段」：应显示 g++ 的原话（含 `solution.cpp:行号: error:`），**不是**「未定义函数」这类内部报错。
再把 `index > static_cast<int>(items.size())` 改成 `index >= static_cast<int>(items.size())`，
提交评测：**应恰好有 3 条失败、`10/13`**，且失败行的「实际」列有值。控制器**实测**过这个变异：

```
passed = False | 10 / 13 | compile_error = None
失败条数 = 3
  FAIL: 在末尾插入元素        ([1,2,3], index=3, size=3 → 3>=3 误判越界)
  FAIL: 向空容器插入          ([],      index=0, size=0 → 0>=0 误判越界)
  FAIL: 单元素容器插入到末尾   ([7],     index=1, size=1 → 1>=1 误判越界)
```

**不是「恰好一条」，是三条**——因为「合法的末尾插入」在这 13 条里出现在三种规模上
（普通容器、空容器、单元素容器），收紧边界会把它们一起打掉。
预期写成一条的话，执行者看到 3 条红会以为判题坏了或自己改错了地方。

- [ ] **Step 5: 故障修复**

进入故障修复阶段 → 系统写入 `repair_target.cpp` → 文件树里出现该文件 → 点开能看到含错的 C++ 代码 → 修复后提交评分通过。

- [ ] **Step 6: 变式迁移**

进入变式迁移阶段 → 生成 `VARIANT_TASK.md` 与新的 `solution.cpp` 骨架（含 `insert_interval` 的 C++ 签名）→ 实现后提交，**13/13** 通过。
（**是 13，不是 14**：Task 6 Step 1 把变式用例定为 13 条——原 17 条里去掉考 Python 动态类型的
「拒绝非整数端点」「拒绝布尔端点」「拒绝非列表」三条（C++ 具体类型下无法表达，且 `"abc"`/`True`/`2.0`
根本传不进 `std::vector<std::vector<int>>` 参数），再去掉那条按值签名下永远为真的 `immutable`。
控制器逐条数过 `agent_lab_variants.py` 现有 17 条、计划新写 13 条。）

（变式参考解按 Step 1 的场景要求手写：排序 + 合并 + 边界校验。）

- [ ] **Step 7: 其余 12 关不受影响**

逐关打开 1-2、1-3、2-1、4-3：文件仍是 `solution.py`，编辑器是 Python 高亮，题面没有 C++ 措辞，阶段数仍是 5。重点看 **1-2**：它**不应**再出现「本关会在上一关（1-1）的 solution.py 基础上继续累积」这句话（累积链已在 1-1→1-2 处按语言断开）。

- [ ] **Step 8: 控制台与报告**

收集整个过程的浏览器控制台输出。按 `student/CLAUDE.md` 的要求报告：**通过 / 失败 / 控制台错误**三节。任何一项失败都要回到对应任务修，不要在 E2E 里就地打补丁。

---

### Task 9: 生产部署与验收

**Files:**
- Modify: `nginx-analysis/_pta_upload.js`（上传清单加上本次改动的文件）
- 使用：`nginx-analysis/rexec.js <cmdfile> [timeoutSec]`

**Interfaces:**
- Consumes: Task 8 的通过结论。
- Produces: 生产环境（`/opt/edu-ta`）上的 1-1 为 C++，且其余 12 关不受影响。

- [ ] **Step 1: 备份要改的线上文件**

**先导出本机的真实改动集，再据此写清单——不要凭记忆列。**

下面的清单是**手写的**，而手写的清单会漏。控制器实测漏过一个：
`student/backend/services/guidance_context_service.py`（见 Ruling 42）——它的改动是**必需的**
（`_project_snapshot` 的扩展名白名单不收 `.cpp` 时，1-1 的 `solution.cpp` 就进不了指导上下文，
Task 4 的 `assertIn("solution.cpp", result["project_files"])` 会红），却因为只被**测试**提到、
没被任何任务的文件清单提到，在 Step 1 和 Step 2 里都不存在。漏掉它的后果不是报错，而是
**线上那个文件保持旧版、功能静默降级**，而 md5 逐个核对（Step 2）也发现不了——因为漏的文件
根本不在核对清单里。

所以**不要手写目录列表**，用 `manifest.sh changed`——它先取**受管集合**（158 个文件，
`collect()` 里定义），再按 mtime 过滤，所以「清单」和「受管集合」**不可能不一致**：

```bash
cd /d/code/innovational-competition && bash \
  .superpowers/sdd/lab-1-1-cpp-pilot/manifest.sh changed "2026-09-19 18:30"
```

**为什么不是裸 `find`**（Ruling 63）：控制器最初在这里写的是一条 `find`，它的目录列表是
**手打的**，因而比受管集合**窄**——少了 `backend/*.py`（根级，比如 `schemas.py`）、
`backend/docker-entrypoint.sh`。这与 Ruling 42/55/57 是**同一个成因**：人手列的集合会漏。
`manifest.sh changed` 还多一条**反向核对**：若某个改动文件的 mtime 变新、却**不在**受管集合里，
它会以 `⚠️` 单独列出——那就是「受管集合漏了目录」的信号，此时**先补 `collect()` 再继续**，
因为那意味着部署清单也会漏。

（控制器实测：以 `2026-09-19 18:30` 为基准得 **17 个**文件，其中 5 个是 `tests/`——
**测试文件不需要部署**。以 `2026-09-19 00:00` 为基准得 31 个：差集里那些
（`schemas.py`、`agent_course.py`、`router/index.js` 等）是**今天早些时候**别的改动，
不是本试点的产物——**这正是基准必须取试点开始时间的理由**，取宽了会把无关文件也传上线。）

控制器在 T1–T4 完成后实测的输出（**`guidance_context_service.py` 正是漏掉的那个，
它出现在这里而在备份清单里没有**）：

```
student/backend/Dockerfile
student/backend/scripts/verify_lab_content.py
student/backend/services/agent_lab_specs.py
student/backend/services/cpp_judge.py
student/backend/services/guidance_context_service.py   ← 手写清单漏了它
student/backend/services/judge_service.py
student/backend/services/lab_workspace_service.py
```

（此刻还没有 `agent_lab_faults.py` / `capability_service.py` / `agent_lab_variants.py` /
`scripts/verify_lab_faults.py` / 前端文件——它们是 T5/T6/T7 的产物，做完后这一条会把它们一并列出来。
**T9 执行时应当看到它们全部出现**；若某个已改文件没出现，说明它的 mtime 早于基准，把基准往前调再跑。）

**关于 `scripts/verify_lab_faults.py`（T5 改的，见 Ruling 55）**：它是**验证脚本、不是运行时链路**，
所以「不传也不会影响线上功能」。**但它照样要传**，理由有两条：
1. 它与 `verify_lab_content.py` 同类，而后者**已经在**清单里——两个同类脚本一个传一个不传，
   是凭手感而不是凭规则。
2. 不传的后果是**线上留着一份会误报的判断器**：旧版第 52 行是 `ast.parse(mutated)`，对 C++
   恒抛 `SyntaxError`，1-1 必然被判 **FAIL**。谁下次在生产上跑它排查问题，会得到一个假的失败结论。

把这条命令的输出与下面的清单**逐行对齐**，缺哪个补哪个，然后再执行备份：

写一个 `nginx-analysis/_pta_backup_cpp.cmd`，把本次会覆盖的每个文件先复制成 `.bak-20260919`：

```bash
cd /opt/edu-ta && for f in \
  student/backend/Dockerfile \
  student/backend/services/judge_service.py \
  student/backend/services/agent_lab_specs.py \
  student/backend/services/lab_workspace_service.py \
  student/backend/services/guidance_context_service.py \
  student/backend/services/agent_lab_faults.py \
  student/backend/services/capability_service.py \
  student/backend/services/agent_lab_variants.py \
  student/backend/scripts/verify_lab_content.py \
  student/backend/scripts/verify_lab_faults.py \
  student/backend/data/flagship_exercises.json \
  student/frontend/src/views/CodeLab.vue \
  student/frontend/src/components/LabFileTree.vue \
  student/frontend/src/config/flagshipExercises.js \
  student/frontend/package.json student/frontend/package-lock.json ; do
  cp -a "$f" "$f.bak-20260919"
done
ls -l student/backend/services/cpp_judge.py.bak-20260919 2>/dev/null || echo "cpp_judge.py 是新增文件，无备份"
```

用 `rexec.js` 执行并确认每个 `.bak-20260919` 都存在。

- [ ] **Step 2: 上传**

把 `cpp_judge.py`（新增）与上面列出的所有改动文件加进 `_pta_upload.js` 的清单，执行上传，并按脚本自带的方式逐个核对 md5（本地 md5 == 线上 md5）。

- [ ] **Step 3: 确认线上 docker-entrypoint.sh 仍是 LF**

```bash
file /opt/edu-ta/student/backend/docker-entrypoint.sh
```

Expected: `ASCII text`（不带 `with CRLF line terminators`）。

- [ ] **Step 4: 重建（从仓库根目录 `/opt/edu-ta`）**

```bash
cd /opt/edu-ta && docker compose up -d --build
```

**绝对不要执行 `docker compose down -v`**：线上 Key 加密文件在命名卷里，`-v` 会让已配置的 API Key 永久解不开。

- [ ] **Step 5: 确认线上容器里有 g++**

```bash
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend sh -c 'g++ --version | head -1'
docker ps --format '{{.Names}}|{{.Status}}' | grep -E 'ai-learning'
```

- [ ] **Step 5b: 确认线上卷里的关卡 JSON 也是新版**

上传只把文件放到了 `/opt/edu-ta/student/backend/data/`，重建只把它烘进镜像；
**线上容器实际读的是命名卷里那份**，它不会被重建刷新（线上更不能 `down -v`）。
这一步不做，页面会停在旧题面，而且内容校验、接口、控制台全都看不出异常。

```bash
cd /opt/edu-ta && md5sum student/backend/data/flagship_exercises.json
MSYS_NO_PATHCONV=1 docker exec -w /app ai-learning-backend sh -c 'md5sum /app/data/flagship_exercises.json'
```

两个 md5 必须相同；不同就补一次（写的是卷，`load_flagship_exercises()` 每次调用重读文件，不用重启）：

```bash
cd /opt/edu-ta && MSYS_NO_PATHCONV=1 docker cp student/backend/data/flagship_exercises.json ai-learning-backend:/app/data/flagship_exercises.json
```

- [ ] **Step 6: 重置线上 demo 的 1-1 工作区**

线上 demo 的 1-1 已有内容，README 与骨架**不会**刷新。删掉工作区让它重新 seed：

**这一步是整份计划里唯一一处「删线上数据」，所以先备份、再删，不要只「看一眼」。**
`rmtree` 不可撤销，而「看一下内容然后记下来」既不是备份也没法还原——真删错了只能靠记忆重敲。

**第 1 步：先确认 demo 的用户 id，不要假定是 1。**（线上的 id 顺序与本地容器不同，写死 `user-1`
很可能删掉一个不存在的路径——于是脚本打印 `removed:` 看似成功，实际工作区没重置，
页面还停在旧 README，而且没有任何报错。）

```bash
MSYS_NO_PATHCONV=1 docker exec -i -w /app ai-learning-backend python -c "
from services.agent_course import build_course_path, TRACK_NAMES
import database
conn = database.get_db()
row = conn.execute(\"SELECT id, username FROM users WHERE username='demo'\").fetchone()
print('demo 用户:', dict(row) if row else '未找到')
conn.close()
"
```

**第 2 步：先整目录备份，再删。**（备份留在容器里即可，需要时 `docker cp` 取回；
`.bak-20260919` 与 Step 1 的备份同一个命名习惯。）

```bash
MSYS_NO_PATHCONV=1 docker exec -i -w /app ai-learning-backend python -c "
import shutil, pathlib
from services.lab_workspace_service import WORKSPACE_ROOT
root = pathlib.Path(WORKSPACE_ROOT)
target = root / 'user-<上一步查到的 id>' / '1-1'
print('目标:', target, '存在 =', target.exists())
if target.exists():
    print('--- 删除前的内容清单 ---')
    for p in sorted(target.rglob('*')):
        print('   ', p.relative_to(target), p.stat().st_size if p.is_file() else '<dir>')
    backup = target.with_name('1-1.bak-20260919')
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(target, backup)
    print('已备份到:', backup)
    shutil.rmtree(target)
print('删除后 exists =', target.exists(), '(应为 False)')
"
```

删之前**看第 2 步打印出来的清单**：线上 demo 是演示账号，正常情况下只有 `README.md` 与实现文件。
若出现骨架之外的东西（学生自己写的实现、笔记等非模板文件），**先停下把情况报告给用户**
——线上数据不归这次试点处置，不要自行判断「反正是 demo 就删了」。

- [ ] **Step 7: 重跑 Task 8 的 E2E**

在线上域名上按 Task 8 的 Step 2-7 重跑一遍。**注意**：线上的 AI 是配置好的，`aiDiagnose` 会真实调用；提交评测后主结果必须留在「评测结果」页签，运行日志里应恰好有一条 `🔍 已请编程导师分析本次报错`（`focus: false` 的行为）。

⚠️ **但先分清「本次试点引入的失败」与「线上本来就坏的东西」。** 控制器此前在线上观察到
AI 诊断**超时**（`模型连接异常`，涉及 `gpt-4o-mini`），**这是既有问题，与 C++ 试点无关**。
所以若 Step 7 出现 AI 相关失败，**先判定它是不是同一个既有问题**（报 `模型连接异常` /
超时 / 模型名 `gpt-4o-mini` 就是它），是就**如实记进报告但不算试点失败**，
不要去改 AI 配置或模型名——那是另一件事，**不在本计划范围内**（见文末「本计划不做的事」）。
判据：**判题、阶段检查、文件生成、C++ 编译这些与 AI 无关的环节必须全过**；
只有 AI 诊断这一条允许带着既有问题过去，且必须在报告里写清楚它在本试点之前就存在。

- [ ] **Step 8: 报告**

按 `student/CLAUDE.md` 的格式报告：**通过 / 失败 / 控制台错误**，并附上：
- 线上 `g++ --version`
- 1-1 提交评测的 `通过 13/13`
- 1-2 / 1-3 / 4-3 仍是 Python 的截图或 DOM 证据
- 镜像体积变化（Task 1 Step 5 的数字）

---

## 附：本计划**不做**的事（spec 已明确，避免执行时扩大范围）

1. **其余 12 关不动**（仍为 Python）。
2. **学习文档语料不动**：1-1 绑定的 44 篇 runoob 教程里 0 个 C++ 代码块。试点后文档仍在教 Python/Java，这件事在阶段卡片与验收报告里如实说明，不改语料。
3. **`backend/services/lab_test_runner.py` 不动**：它是非旗舰关卡的旧执行路径，不在 1-1 的判题链上。
4. **`_run_custom_variant_harness` / `_judge_repair_db_variant` / `_judge_incident_plan_variant` 不动**：它们是需要真实 ORM 对象或可调用工具的私有变式路径，与数据结构关卡无关。
5. **`immutable` 用例不加新机制**：按值签名下 `mutated` 永远为假，该用例在 C++ 下退化为契约声明；真正的执行者是链接期的签名检查（Task 3 的 `test_changing_the_declared_signature_fails_to_link` 覆盖了它）。
