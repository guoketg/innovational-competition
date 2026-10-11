# 关卡 1-1 改用 C++ 试点 — 设计

日期：2026-09-19
状态：已与用户确认，待落实施计划

## 一、目标与范围

把学生端编程实验室的**第 1-1 关「实现顺序表插入」**从 Python 改成 C++，作为一次完整试点。目标是验证「判题执行契约 + 内容形态」在 C++ 下跑得通，再决定其余 12 关怎么铺。

**范围内**

- 1-1 的题面、起始代码、参考解、判题用例、注入故障、变式迁移
- 判题执行契约新增 C++ 路径（编译 → 运行 → 回传）、每关「语言」属性
- 前端编辑器 C++ 语法与补全
- 后端镜像补 `g++`

**范围外（明确不做）**

- 其余 12 关保持 Python 不动
- 学习文档语料（44 篇 runoob 数据结构教程）不动
- AI 导师提示词的整体结构不动，只把其中「Python 基础语法」这类措辞按语言参数化

### 已确认的三项决定

1. **试点范围**：只做 1-1。
2. **代码形态**：函数式 + 关卡声明 C++ 签名（学生只写一个函数，不是整程序）。
3. **1-1 签名**：具体类型 `std::vector<int>`，不做模板；无法直译的动态类型用例改写成 C++ 的边界考点。

## 二、为什么要改写内容而不是「移植」

1-1 现有 17 条用例里，**10 条考的是 Python 动态类型校验**（传字符串／浮点／布尔／`None` 当索引、传字典当列表）。在 C++ 里这些**编译期就被挡掉**，而且不是报错而是静默出错：

- `array_insert(v, true, 9)` —— `bool`→`int` 隐式转换，插入到位置 1
- `array_insert(v, 1.0, 9)` —— `double`→`int` 截断，插入到位置 1

所以这 10 条不是移植，是消失，必须补 C++ 真正的边界考点顶上（容量、边界、异常、值语义）。

另外，`immutable`（不得修改入参）在**按值签名**下自动成立——但它仍有价值：学生若把签名改成 `std::vector<int>&`，`main.cpp` 照样能编译链接，这时该用例才会抓住他。因此保留，不删。

## 三、判题执行契约

### 3.1 关卡声明

`backend/services/agent_lab_specs.py` 中每关增加语言与 C++ 契约：

```python
"1-1": {
    "target": "array_insert",
    "targets": ["array_insert"],
    "language": "cpp",                       # 缺省视为 "python"
    "cpp": {
        "signature": "std::vector<int> array_insert(std::vector<int> items, int index, int value)",
        "includes": ["<vector>", "<stdexcept>", "<string>"],
        "exception_map": {"out_of_range": "std::out_of_range"},
    },
    "cases": [...],
}
```

用例格式保持现有形状（`description` / `args` / `expected` / 可选 `exception` / `immutable` / `func`），只有 `exception` 的取值从 Python 异常名改为**语言中立 token**：

```python
{"description": "拒绝越界索引", "args": [[1, 2, 3], 4, 9], "exception": "out_of_range"}
```

Python 关卡沿用原样（`"exception": "ValueError"` 继续有效），映射在关卡声明里显式给出，避免两种语言共用一套隐式约定。

### 3.2 生成与编译

判题器按签名生成 `main.cpp`，与学生的 `solution.cpp` **分两个编译单元**一起编译：

```
g++ -std=c++17 -O2 -Wall main.cpp solution.cpp -o prog
```

`main.cpp` 的职责：

1. 引入关卡声明的 includes，按 `signature` 写函数原型。
   **学生擅自改动签名 → 编译或链接失败**。这是换 C++ 的净收益：Python 时代只能靠 `ast` 静态检查才能发现的事，现在由编译器保证。
2. 逐条用例：由 Python 侧按参数类型直接生成 C++ 字面量（`{1, 2, 3}`、`1`、`9`），**不需要任何 JSON 解析库**。
3. 在 `try/catch` 中调用，按结果打印一行 JSON：

   | 情形 | 输出 |
   |---|---|
   | 正常返回 | `{"i":1,"ok":true,"actual":[1,9,2,3]}` |
   | 抛异常 | `{"i":1,"ok":false,"threw":"std::out_of_range"}` |
   | 其它失败 | `{"i":1,"ok":false,"err":"…"}` |
   | 入参被改（immutable 用例） | 追加 `"mutated":true` |

C++ 侧只需一个几十行的 `to_json` 重载集合（`int` / `long` / `double` / `bool` / `std::string` / `std::vector<T>`）。

异常用例的判定：C++ 侧捕获后报的是**实际类型名**，Python 侧拿 `threw` 与关卡声明的 `exception_map[token]` 比较。也就是关卡自己负责「`out_of_range` 在本关等于 `std::out_of_range`」这层映射，判题器不需要知道任何 C++ 类型。

### 3.3 比对与展示管线不动

`expected` 仍然是 JSON，仍然由 Python 用 `==` 比对。`_case_views`、`_sample_actual`、`_safe_repr`、评测面板的「实际」列、`feedback_guidance` 的分类与下一步建议——**全部原样复用**。

C++ 只负责把 `actual` 吐回来；Python 负责比对、归类、渲染。这是刻意的：现有这条管线已被 26 个单测覆盖，不碰它能把改动风险压到最小。

### 3.4 超时与失败

- 编译 20s、运行 6s（沿用现有默认），两段独立计时。
- 编译失败 → 复用现有 `compile_error` 字段，填入编译器的首条错误（去掉临时目录前缀，学生看得懂）。
- 「目标函数已定义」在 C++ 下**不需要单独实现**：未定义符号就是链接失败，走同一条 `compile_error` 路径。

### 3.5 安全边界

现有 `_policy_error` 基于 `ast.parse`，对 C++ 无效。改为：

- 极简 denylist 扫描：`system(` / `popen(` / `fork(` 直接拒绝，理由写清楚
- 子进程加 `ulimit`（CPU 时间 / 内存 / 文件大小）并跑在临时目录
- 诚实说明：与现状一致，这是**应用级隔离，不是安全沙箱**（`judge_service` 的模块 docstring 已经这么写了，保持不变）

## 四、「语言」成为每关的属性

`solution.py` 与「Python 语法正确」目前硬编码在约 60 处。引入按关的 `language`（默认 `python`）后，以下全部由它派生：

| 位置 | 现状 | 改为 |
|---|---|---|
| `lab_workspace_service.py:611` | `project_files = ["solution.py"]` | 按语言 |
| `_seed` 写骨架（`:1048-1051`） | 写 `solution.py` | 按语言 |
| `structure` 检查（`:628-636`） | 「solution.py 存在 / 文件名大小写一致」 | 「solution.cpp 存在 / …」 |
| `first_llm_call` 检查（`:391` 等 13 处） | 「solution.py 语法正确」 | 「solution.cpp 编译通过」 |
| `implementation` 检查（`:656`） | 「Python 语法正确」 | 「C++ 编译通过」 |
| 故障／变式产物（`:1346`、`:1358`） | `repair_target.py` / `VARIANT_TASK.md` | `repair_target.cpp` / 同 |
| README 约定（`:1010`） | 「全部实现写在 `solution.py` 里」 | 按语言 |
| `_IMPL_NOTES["1-1"]`（`:222-224`） | 讲「校验 items 是列表…」 | 改写为 C++ 契约 |
| AI 提示词（`:1778`、`:2207`） | 「Python 基础语法」 | 按语言参数化 |
| 文件工具描述（`:1881`） | 举例 `app.py, solution.py` | 按语言 |
| `TRACK_CONFIG`（`:50-68`） | `"framework": "Python 标准库"` | 1-1 显示 C++ 标准库 |

单文件形态（去掉终端与 `.venv` 之后的设计）保持不变——1-1 依然只有一个项目文件，只是扩展名与语言不同。

## 五、内容的改写清单（1-1）

- **题面**（`backend/data/flagship_exercises.json` 的 1-1 条目）：`description` / `input_output` / `starter_code` / `skills` 全部改写。删掉「items 是否为列表」「是否为布尔整数」这类动态类型校验，改为容量／边界／异常契约。
- **起始代码**：C++ 骨架，签名写死，体内以 `throw std::out_of_range(...)` 占位替代 `raise NotImplementedError`。保留现有「签名、参数顺序、返回值契约不能改动」的提示（`:95`）。
- **参考解**（`backend/scripts/verify_lab_content.py` 的 `REF_1_1`）：改写为 C++，并保证它被 `run_sample_checks()` 用得上。
- **用例**（`agent_lab_specs.py` 的 `SPECS["1-1"]`）：17 → 13 条，**沿用现有用例格式，不新增用例种类**（仍只有 `expected` / `exception` / `immutable` 三种形态）。

  留下的 7 条（原样可直译）：

  | 用例 | 参数 | 期望 |
  |---|---|---|
  | 在中间插入元素 | `[1,2,3], 1, 9` | `[1,9,2,3]` |
  | 在头部插入元素 | `[1,2,3], 0, 9` | `[9,1,2,3]` |
  | 在末尾插入元素（等价 `push_back`） | `[1,2,3], 3, 9` | `[1,2,3,9]` |
  | 向空容器插入 | `[], 0, 5` | `[5]` |
  | 插入后不修改原容器（`immutable`） | `[1,2,3], 1, 9` | `[1,9,2,3]` |
  | 拒绝越界索引（`exception`） | `[1,2,3], 4, 9` | `out_of_range` |
  | 拒绝负数索引（`exception`） | `[1,2,3], -1, 9` | `out_of_range` |

  补上 6 条（取代消失的动态类型校验，全部用现有格式表达）：

  | 用例 | 参数 | 期望 |
  |---|---|---|
  | 单元素容器插入到头部 | `[7], 0, 9` | `[9,7]` |
  | 单元素容器插入到末尾 | `[7], 1, 9` | `[7,9]` |
  | 较长容器中间插入（同时验证长度与顺序） | `[1,2,3,4,5], 2, 0` | `[1,2,0,3,4,5]` |
  | 插入到 size()-1 位置 | `[1,2,3,4], 3, 9` | `[1,2,3,9,4]` |
  | 含重复元素的容器 | `[5,5,5], 1, 5` | `[5,5,5,5]` |
  | 下界越界 | `[1,2,3], -4, 9` | `out_of_range` |

  注意：**「返回值元素个数 = 原 size + 1」「插入后原容器尺寸不变」不单列用例** —— 前者已被每条 `expected` 隐含校验，后者就是 `immutable` 那条，单列只是重复。
- **注入故障**（`backend/services/agent_lab_faults.py`）：
  - 1-1 的 `root_cause` 文案改为 C++ 措辞（`index >= items.size()`）
  - 现有两条候选是 Python 正则（`:103-107`），要重写为 C++ 正则；其中「破坏不可变语义」那条在按值签名下不再可注入，换成位置偏移／漏掉末尾追加
  - **AST 兜底改写器**（`capability_service._ForceMutator` / `_ast_fallback_mutation`）只认 Python。C++ 关卡按语言跳过并给出明确提示，不要抛一个学生看不懂的错
- **变式**（`backend/services/agent_lab_variants.py` 的 1-1 `insert_interval`）：签名改为 `std::vector<std::vector<int>> insert_interval(std::vector<std::vector<int>> intervals, std::vector<int> new_interval)`，`ValueError` → `std::invalid_argument`，`scenario` 文案改写。

### 顺带消掉一份重复实现

变式迁移目前有**自己第三份判题 runner**（`capability_service.py:2009-2184`），注释里写着「必须与正课判题器（judge_service.RUNNER）的能力集一致」——靠人工同步。这次让 `_judge_variant_code` 直接走新的语言感知判题路径，把这份副本删掉。

（故障修复走的是 `submit_repair` → `_judge_exercise_code` → `judge_submission`，已经是单一来源，不必改。）

## 六、前端

- 新增依赖 `@codemirror/lang-cpp`（当前未安装）
- `CodeLab.vue`：
  - `languageFor()`（`:959-965`）、`languageExtension()`（`:1177-1189`）增加 `cpp` 分支
  - 新增一份 C++ 补全片段，与现有 `pythonCompletionSource`（`:1164-1175`）并列：`#include`、`std::vector`、`for (int i = 0; i < n; ++i)`、`throw std::out_of_range`、`size()`、`push_back`
  - 徽标（`:255-256`）、欢迎文案（`:266-267`「打开 solution.py」）、提示按钮的出现条件（`:256` 的 `endsWith('.py')`）、`repair_target.py` 引用（`:223`、`:1441-1446`、`:1482-1488`、`:1949-1972`）
  - `LabTextModel` 的语言参数（`:1502-1514` 写死 `'python'`）
  - CSS `.tab-dot.python`（`:2221`）→ 增加 `.tab-dot.cpp`
- `LabFileTree.vue`：`:26` 的「Python」标签、`:59` 与 `:69` 的扩展名映射
- `flagshipExercises.js:9`：「用 Python 标准库实现线性结构与基础容器」→ 按语言表述

## 七、镜像与运行环境

`backend/Dockerfile` 当前是 `FROM python:3.11-slim`，**没有任何编译器**。加 `g++`（Debian 基础镜像，apt 可用）。

顺带收益：`learning_router.py:160` 与 `qa_router.py:904-916` 早就配好了 `cpp → g++` 的语言映射，但因为有 `shutil.which` 检查，容器里一直返回「未找到运行环境」。装上编译器后这两个入口自动可用。

## 八、已知代价（用户已知情）

1. **1-2 的累积链断了**。`_CARRIES_FROM = {"1-2": "1-1", "1-3": "1-2"}`（`:175`），1-2 的 `_carry_over_toolbox` 会去 1-1 的工作区找 `solution.py`，而 1-1 只剩 `solution.cpp` → 拿不到工具箱。更麻烦的是 1-2 的 README 仍会写「本关会在上一关（1-1）的 `solution.py` 基础上继续累积」（`:1013`），**变成假话**。
   处理：累积逻辑与文案按「两关语言一致」判断，跨语言时不累积、README 照实说明。

2. **文档讲解与实验语言不一致**。1-1 绑定的文档是 `_KNOWLEDGE_TAGS["1-1"] = "dsa-dsa-linear-data-structures"`（`_KNOWLEDGE_LABELS` 显示为「数据结构与算法 › 线性数据结构 › 数组（Array）」）。该语料 44 篇里有约 60 个 Python 代码块、35 个 Java 代码块、**0 个 C++ 代码块**。试点后文档仍在教 Python/Java。
   处理：本次不动（用户选择的试点范围不含文档），但在阶段卡片与验收报告里如实说明。

3. **immutable 考点变弱**：按值签名下自动成立，仅在学生改动签名时才有区分度。

## 九、验证方式

- **单测**：`backend/tests/test_lab_workspace_service.py` 中断言 `project_files == {"README.md", "solution.py"}` 的几处（`:68`、`:71`、`:108`）按语言参数化；新增 C++ 判题路径的用例——正常通过、编译失败、抛异常、超时、immutable、签名不符。
- **内容校验**：`verify_lab_content.py` 的 `REF_1_1` 与 `run_sample_checks()`；`verify_lab_faults.py`；`verify_lab_wiring.py`。
- **本地 E2E**（Playwright，`localhost:80`，demo/demo123）：5 阶段依次通过、自测（公开样例全绿）、提交评测（全部用例）、故障修复、变式迁移、控制台无错误。
- **生产**：部署后重跑同一套 E2E，并按 `student/CLAUDE.md` 报告通过／失败／控制台错误。

## 十、验收标准

1. 1-1 在浏览器里的项目文件是 `solution.cpp`，编辑器是 C++ 语法与补全，题面不再出现「列表」「ValueError」这类 Python 措辞。
2. 自测与提交评测对 C++ 参考解全绿，对残缺解给出正确的失败用例与输入／期望／实际。
3. 编译失败（含签名不符、语法错误）显示编译器的可读错误，而不是「未定义函数」之类的内部报错。
4. 故障修复与变式迁移在 C++ 下完整可用。
5. 2-1 至 4-3 在浏览器里**完全不受影响**（仍为 Python）。
6. 1-2 与 1-3 仍为 Python，但 1-2 **不再宣称**继承了 1-1 的代码（累积链在 1-1→1-2 处按语言中断，文案照实说明）。
