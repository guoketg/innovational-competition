# 数据结构实验室 PTA 化与答辩内容修复 — 设计

日期：2026-09-19
状态：已批准，待实施

## 背景

2026-09-19 上一轮改造把学生端编程实验室的 13 个关卡从 AI Agent 主题换成了数据结构
主题，覆盖了关卡元数据、判题用例、变式与故障注入。本轮解决两件遗留问题：

1. **原理答辩仍是 Agent 内容**。`capability_service._defense_questions()` 的 q3 用
   `exercise_id` 硬编码分支：`1-1` 问 `AIMessage`、`1-2` 问 `append_turn_and_trim`
   的上下文裁剪，`else` 分支覆盖 `1-3`～`4-3` 共 **11 关**，统一问「LangChain 框架
   在本实验中替你完成了哪些底层工作」。学生在写 BST 时被问 LangChain。
2. **做题环境以终端为中心**，用户要求去掉终端，改为 PTA（拼题A）形态。

### 四个环节的实际状态

| 环节 | 数据源 | 本轮前状态 |
|---|---|---|
| 实验推进 | `flagship_exercises.json` 的 `steps` + `lab_workspace_service` 阶段定义 | 步骤文案已是数据结构；但**阶段判定依赖终端** |
| 原理答辩 | `capability_service._defense_questions()` | q1/q2 通用；**q3 是 Agent 内容** |
| 故障修复 | `agent_lab_faults.py` | 已全数据结构，13 关覆盖完整 |
| 变式迁移 | `agent_lab_variants.py` | 已全数据结构，13/13 判题通过 |

故障修复与变式迁移**本轮不需改动**。

## 目标

1. 原理答辩题目由本关考点数据生成，不再硬编码；换题不再漏改。
2. 移除终端，改为 PTA 形态单文件做题界面。
3. 保留「实验推进 → 原理答辩 → 故障修复 → 变式迁移」四阶段闭环。

## 非目标

- 不改动 `agent_lab_faults.py` / `agent_lab_variants.py` 的内容。
- 不改动题库、RAG 语料、向量库。
- 不改动门户。

## 设计

### 一、答辩题目数据驱动化

`_defense_questions(code, exercise)` 的 q1/q2 是按代码形态分支的通用题，保留不动。
q3 改为从本关已有数据生成，模板取自该关的考点：

- 输入：`SPECS[exercise_id]` 的 `cases`（考点分布）、`exercise` 的 `skills` 与
  `input_output`。
- 输出：一道针对本关数据结构的原理题 + 关键词 rubric。

例如 2-1（BST 插入与查找）得到「你的插入如何维持左小右大？如果比较方向写反，
哪一类用例会先失败？」；3-2（并查集与路径压缩）得到「路径压缩为什么必须返回新
数组？原地改写会破坏什么？」

保留一道**通用兜底题**（复杂度 / 边界 / 替代方案），使任何新增关卡都不会退化为
Agent 题。

同时修正 `capability_service.py:438` 通用故障描述中出现的 `AIMessage` 字样。

### 二、阶段表去终端化

13 关全部是 `framework: "Python 标准库"`、`packages: []`、`imports: []`，因此
虚拟环境、依赖声明、接回应用三个阶段全是空转。

- 删除 `environment` / `dependencies` / `integration` 三个阶段。原 `_ALGO_TRACKS`
  机制下 track 4（4-1～4-3）保留这三阶段，本轮**一并删除**，13 关统一阶段表。
  随之移除 `_ALGO_TRACKS` 与 `_ENGINEERING_STAGE_IDS` 的分支逻辑。
- `structure` 阶段由校验 `requirements.txt + solution.py + app.py` 改为只校验
  `solution.py`；`project_files` 相应收缩。
- `first_llm_call` 阶段（1-1/1-2/1-3 的「先跑通再提取」）不再依赖
  `_has_successful_script_run(root, "app.py")` 的终端执行记录，改为 AST 静态检查
  加自测按钮。该阶段的 `check_mode: "run"` 分支随之移除。
- 清除阶段文案中所有「在终端执行 …」「终端提示符」「已完成安装」等表述。

改后 13 关阶段表统一为：`doc_intro → structure → implementation → acceptance`
（1-1/1-2/1-3 额外含 `first_llm_call`）。

`check_stage` 中 `environment` / `dependencies` 两个 `elif` 分支一并删除。

### 三、PTA 界面重塑

题面数据前端已具备：`/workspaces/{id}` 返回的 `course` 对象已携带
`title / description / input_output / acceptance / skills / framework /
prerequisites / micro_steps`。**不需要新增题面接口**，本次是面板重排。

```
现在:  [顶部栏]
       [图标条][文件树+题面][编辑器+终端][AI 助教]

改后:  [顶部栏 + 能力阶段按钮]
       [题目面板][编辑器][AI 助教]
       [样例 / 输入输出 / 提示]
       [评测面板: 测试点表 + 自测/提交评测]
```

- 移除 `activity-bar`、`side-panel` 中的文件树、`terminal-panel`
  （`CodeLab.vue:305-333`）、「一键创建环境」按钮与 `.venv` 状态。
- 新增左栏题目面板，复用现有题面渲染（`CodeLab.vue:125-190`）。
- 新增底部评测面板：测试点表格（序号 / 结果 / 描述 / 耗时）+ `[自测]` `[提交评测]`。
- **终端当前承载 `checkStage`、故障修复提交、变式提交与全部报错的输出**
  （`terminalLines`）。这些输出全部迁移到评测面板。这是本次最易引入缺陷的部分。

单文件模式下的编辑目标按阶段自动切换：

| 阶段 | 编辑文件 | 左栏题面 |
|---|---|---|
| 实验推进 | `solution.py` | `course.description` 等 |
| 故障修复 | `repair_target.py` | 故障现象描述 |
| 变式迁移 | `solution.py` | `VARIANT_TASK.md` |

### 四、自测样例

判题用例位于 `agent_lab_specs.py`，其文件头注明「不会通过资源接口发送给浏览器」。

- 每关给 2–3 条已有 `cases` 增加 `"public": True` 标记。
- 新增 `POST /workspaces/{id}/run-samples`，只执行公开用例，返回每条用例的
  输入 / 期望输出 / 实际输出 / 是否通过。
- 隐藏用例继续不下发。

### 五、后端清理

- 移除 `/workspaces/{id}/terminal` 与 `/workspaces/{id}/terminal/stream` 两个路由。
- 移除 `lab_workspace_service.stream_terminal` / `run_terminal` 及终端状态字段。
- 移除前端 `api/workspace.js` 的终端调用。
- **保留**文件读写接口（`list_entries` / `read_file` / `save_file` /
  `delete_file` / `entry` 系列）——故障修复与变式迁移仍依赖它在服务端落地文件。

## 验证

1. 单元测试：改 `test_lab_workspace_service.py`（阶段表）、
   `test_capability_service.py`（答辩题），新增自测接口用例。
2. `scripts/verify_lab_content.py`：新增断言——公开样例不得覆盖全部考点，
   即每关至少保留一条隐藏用例。
3. `verify_lab_faults.py` / `verify_lab_wiring.py` 维持全过。
4. Playwright 端到端：13 关题面与样例渲染、自测按钮、提交评测表、四阶段闭环、
   控制台零错误。
5. 部署 `student-backend` + `student-frontend` 到线上，并重置 13 关工作区
   （旧工作区的 `app.py` 与 `.venv` 在 PTA 模式下已无意义）。

## 风险

- 终端是当前所有判题与错误反馈的出口，迁移遗漏会导致学生看不到失败用例。
  缓解：逐条清点 `ElMessage` 与 `terminalLines` 的写入点。
- 阶段表收缩会与已存在的 `.lab-state.json` 中的 `completed_stages` 冲突。
  `check_stage` 末尾已按 `course["stages"]` 重建 `completed_stages`，被删除的阶段
  会自动剔除，无需额外迁移。
- 工作区重置会清除学生的历史文件。沿用上一轮做法：先备份，保留已完成的有效作业。
