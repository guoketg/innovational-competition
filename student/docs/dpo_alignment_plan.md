# DPO 对齐任务计划（E4 权重层护栏）

> 目的：把 Answer Guard 从"运行时拦截"推进到"权重内化"，补齐 [algorithmic_blueprint.md](../../docs/algorithmic_blueprint.md) E4 的 DPO 路线，形成**三层护栏**叙事：运行时 Shield（已完成）+ 权重层 DPO（本任务）+ 裁判仲裁。
> 本文件供新上下文专门执行此任务，背景见蓝图 §2 E4、§3.1 成熟度阶梯 L2。

## 一、任务目标

用 DPO（LoRA/QLoRA）微调一个 8B 开源指令模型，使其在编程辅导场景中**该引导时引导、该给码时给码**：
首轮引导不泄题，第二轮（学生展示尝试后）给出完整代码与讲解，概念类问题照常直答——而不是学成"拒答一切"。

## 〇、对齐原则与错位复盘（先读）

**对齐原则：线上护栏挡什么，DPO 就学什么。**

初版方案存在三重错位，已复盘修正：

| 错位 | 初版做法 | 修正后 |
|---|---|---|
| 语言错位 | 数据全英文（Socratic benchmark） | 中文为主体（A 层 --zh-ratio 可调，默认 0.5），CodeLab 层天然中文 |
| 题型错位 | 只有 Python 调试题 | 增加 P 层：CodeLab C++ 关卡（与线上 `answer_guard_service` 参考答案同源） |
| 场景错位 | 只有"一次求助→给码" | 增加首轮/次轮时机差异、绕过攻击、概念直答、多轮对话 |

**边界定义（何时给码、何时不给）**：

- **首轮**：学生开口就要答案/完整代码 → 引导（≤3 行提示 + 反问），不给完整码
- **第二轮**：学生展示了自己的尝试/卡点 → 给完整代码 + 讲解（此时给码才是教学）
- **概念/无关请求**：`为什么数组越界会段错误` 这类问题该答就答，不套引导模板
- **红线**：不能拒绝该给的代码——验收含 false-refusal 人工抽查

**测评泄露防线**：按**问题族分组 70/30**（同族题目只进训练或测评一边）；CodeLab 关卡按关卡号分组（9 关训练 / 4 关 held-out）。生成脚本输出 held-out 清单，训练集严禁包含。

## 二、训练环境（已验证可用）

- SSH：`ssh school-server`（= 10.17.1.2:30158, root，本机 `~/.ssh/config` 已配置，密钥免密已通）
- GPU：H200 **MIG 2g.35gb 切片 = 33024 MiB（32.25 GiB）、32 SM**，驱动 550.144.03 / CUDA 12.8
- 机器上常有他人训练任务占 ~5GB；截至计划写入时有一个 ltnll 训练占卡（用户预计 20:00–21:00 结束）
- 显存结论：8B **bf16+LoRA** 峰值 24–28GB（任务清空后可跑，`max_length=1024`、batch=1）；**4-bit QLoRA** 峰值 12–14GB（推荐，可与占卡任务并行）
- 约束（见 [student/CLAUDE.md](../CLAUDE.md)）：所有本地 Python 一律用项目 venv `F:\code\MyPython\computer-cross-education\tiaozhanbei\venv\Scripts\python.exe`，禁用全局环境

## 三、数据策略（六层混合，防遗忘、防泄露、防错位）

总量约 **1000–1050 对**。核心来源全部**离线重新生成**（运行时日志 `answer_guard_log.jsonl` 只有指标没有对话文本，不可作 pair 来源）。

### 3.1 P 层：CodeLab 关卡层（~300 对，主干，与线上护栏同源）

**素材链（全部已在代码库中，零人工标注）**：

- `services/agent_lab_specs.py`：`SPECS["1-1"]...["4-3"]` 13 关，含签名/用例/语言
- `scripts/verify_lab_content.py`：`REFERENCE_SOLUTIONS` / `VARIANT_REFERENCE_SOLUTIONS` 13 关参考答案 = **R1 判据的参考解**
- `services/agent_lab_faults.py`：`FAULT_PROFILES` 中文故障画像 + `curated_mutation_candidates()` 确定性变异出**学生带 bug 代码**

**构造**（每关若干题，覆盖 9 个训练关卡）：

- 学生素材：变异后的带 bug 代码 + 故障画像 → 合成"学生求助"多轮对话
- round1 rejected：无护栏直答（含参考解核心行）；round1 chosen：≤3 行提示 + 反问
- round2 chosen：学生展示尝试后给完整代码 + 讲解；round2 rejected：仍拒答/只给空洞鼓励
- 与线上 `answer_guard_service.evaluate()` 的 R1/R2 判据同源，过滤直接复用

### 3.2 A 层：Socratic 调试层（~300 对，含绕过变体与中文化）

- 来源：150 题 Socratic Programming Debugging Benchmark（英文，见 `scripts/evaluate_direct_code_rate.py` 数据路径）
- 每题生成：round1 引导对 + round2 给码对；部分题目中文化（`--zh-ratio`）
- **绕过变体 rejected**（轮换维度）：语言切换 / 分步套话（"先只给思路"却写成完整码）/ 局部要挟（"只给签名"却给完整实现）/ 假设升级（"假设我已经会了"）

### 3.3 C 层：防拒答边界层（~150–200 对，方向与 P/A round1 相反）

覆盖"不能拒绝该给的代码"：

- **学生已展示尝试** → chosen = 完整代码 + 讲解；rejected = 继续引导/拒给码
- **概念直答**（"解释这个算法为什么错了"）→ chosen = 直接完整解答；rejected = 反问套话
- **明确要完整示例的学习场景**（"给我一个可运行的完整例子对照"）→ 该给就给
- 此层 rejected 是"过度谨慎"行为，`rejected_origin="artificial"` 打标，供训练归因

### 3.4 X 层：输入侧红队层（~80 对）

对应蓝图 E4 输入侧拦截（越狱/诱导提问）：

- rejected：命中越狱话术后仍泄题的回答（须命中 R1）
- chosen：识别诱导意图 + 坚持引导（不命中 R1、不生硬拒答）

### 3.5 G 层：通用偏好防遗忘（~400 对）

- 数据集：**UltraFeedback**（huggingface `datasets` 加载；不可用则跳过并记入报告）
- 配比：领域 : 通用 ≈ 1.5 : 1
- ⚠️ 通用集 chosen 必须是"普通详尽好回答"——不能混入本领域"少给答案"风格，否则模型学成惜字如金
- 训练侧双重保险：LoRA 限制漂移；lr 1e-5~2e-5、1–2 epoch、DPO β 0.1–0.3

### 3.6 分组隔离（防测评泄露）

- **按问题族分组**：文件名剥 `_socratic_dialogue|_conversational_thread_\d+`（含 typo `_thead`）再剥 `^\d+_\d+_` 得到族名；族名哈希 % 10 < 7 → 训练，否则 held-out
- **CodeLab 按关卡分组**：默认 9 关训练 / 4 关 held-out（清单写入报告）
- 报告输出 `held_out_families` 与 `held_out_levels`，验收只跑 held-out

### 3.7 输出格式

统一训练 jsonl（TRL conversational DPO 格式）：

```json
{"prompt": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
 "chosen": "...", "rejected": "...",
 "source": "codelab|socratic|redteam|boundary|general",
 "layer": "P|A|C|X|G",
 "family": "0_0_fibonacci", "round": 1, "lang": "zh|en",
 "hint_level": 0, "rejected_origin": "natural|artificial"}
```

- `prompt` 为 messages 列表（支持多轮：把首轮对话放进 messages，chosen/rejected 是最后一轮助手回复）
- `hint_level` ∈ 0–4：1 具体数字/行号 → 2 计算步骤 → 3 概念洞察 → 4 重述问题（生成时以《提示层级 N》标记开头，脚本解析后剥离）
- `source`/`layer`/`rejected_origin` 用于训练后分层归因与人工抽检定位

### 3.8 每层自动质检矩阵（核心优势：护栏指标即质检器）

| 层 | chosen 必须 | rejected 必须 |
|---|---|---|
| P/A round1 | 不命中 R1（recall<0.2）、无 ≥5 行代码块、以问句结尾 | `is_direct_fix` 或 recall ≥ 0.6 |
| P/A round2 | 含完整代码、无拒答套话、**含讲解**（见下） | 拒答/空洞（不含有效代码） |
| C | 含代码且无拒答、**含讲解** | 命中拒答模式（过度引导） |
| X | 不命中 R1 且不生硬拒答 | 命中 R1（recall ≥ 0.6） |
| G | 通过 UltraFeedback 自带评分过滤 | 对应低分回答 |

**讲解性检查（防"code dump"收敛）**：round2/C 的 chosen 去掉代码块后正文须 ≥30 字符且命中解释性表述（因为/关键在于/讲解/为什么…），否则丢弃。这是防止 DPO 把"甩裸代码"学成正向信号的硬规则。报告按 source 输出 `explanation_stats.explanation_pass_rate`，真实生成时任何一层 <0.9 即重写该层生成指令。人工抽检 rubric 增加一维："chosen 是否解释了根因而非只给码"。

**长度偏差控制**：chosen 短 rejected 长会让 DPO 学成"短=好"。报告按 source 统计 chosen/rejected 平均长度，round2/C 层必须 chosen ≥ rejected 长度的信号要人工核对。
人工抽检 20%（用户 + 2 队友），批次合格率 <80% 改提示词重生成。

### 3.9 部署作用域（权重级行为必须圈定，防止伤及无辜场景）

DPO 改的是权重，"首轮不给码"会随模型部署到处生效——这正是"不能拒绝该给的代码"红线在**部署侧**的对应问题：

1. **只上导师链路**：DPO 模型仅替换 CodeLab 导师 `lab_workspace_service.ask_assistant(/stream)` 的 LLM 调用
2. **不上的链路**：智能答疑 `qa_router`、答辩/变式/修复（capability_service）、题解渲染等——这些场景学生要示例代码是**合理需求**，继续用原基座 + 运行时护栏
3. **护栏不撤**：DPO 上线后运行时护栏仍保留（纵深防御），护栏日志可对比 DPO 组/基座组的泄题率变化
4. **回退开关**：模型路径走配置项，出 false-refusal 可一键切回基座

## 四、训练计划

- 模型：Qwen2.5-7B-Instruct（或同级 8B），4-bit QLoRA
- 框架：TRL `DPOTrainer` + peft，参考模型 = 关闭 adapter 的基座（不占第二份显存）
- 关键超参：`max_length=1024`、`per_device_train_batch_size=1~2`、`gradient_accumulation_steps=8~16`、`gradient_checkpointing=True`、LoRA targets = q/k/v/o/gate/up/down_proj、r=16~32
- 产出：`outputs/dpo_lora/` adapter，scp 回本地或直接在服务器评

## 五、验收标准（双轨）

1. **领域（只跑 held-out）**：
   - Socratic held-out 族跑 `evaluate_direct_code_rate.py`：DPO 组直接给码率显著低于基线（基线 20/20、运行时护栏 2/20，DPO 目标 ≤2/20）
   - CodeLab held-out 4 关：首轮不给码率 + 次轮给码率双指标（防止学成全拒）
   - **false-refusal 人工抽查**：对"学生已展示代码""概念提问"样本，DPO 模型必须正常回答——红线是不能拒绝该给的代码
2. **通用**：50 条通用问答（或 C-Eval 子集）训前训后对比，掉点 <5%
3. **消融价值**：按 `source`/`layer` 分层统计，支撑"哪层数据贡献了行为改变"的分析

## 六、执行步骤（新上下文按此推进）

1. ✅ 写 `backend/scripts/build_dpo_pairs.py`：读素材 → 分层生成 → 质检矩阵过滤 → 分组隔离 → 输出 `data/dpo/dpo_pairs.jsonl` + `dpo_build_report.json`
2. 本机 venv 跑通数据管道（`--dry-run` 模板模式 → `--limit 5` → 全量），人工抽查 10 条定 chosen 风格
3. SSH 上服务器检查环境：`trl/peft/transformers` 版本、HF 连通性（不通则 `HF_ENDPOINT=https://hf-mirror.com`）
4. scp 数据与训练脚本上服务器（建议 `/root/dpo/`）
5. QLoRA 训练（占卡任务结束后，或低占用时段并行）
6. 跑第五节验收，出对比报告

## 七、风险与对策

- **服务器 HF 不通**：走 hf-mirror 镜像；模型提前下载到服务器
- **MIG 33GB 下 bf16 OOM**：降 `max_length` → 切 QLoRA
- **模型学成拒答一切（false-refusal）**：C 层 ~200 对反向样本 + round2 给码样本；验收 5.1 红线人工抽查
- **合成质量不稳**：提示词迭代 + 20% 抽检 + 批次打回机制
- **通用能力下滑**：G 层 1:1 混数据 + 低 lr/小 β + 训后 50 条通用回归测试
- **测评泄露**：分组隔离由生成脚本强制执行，报告输出 held-out 清单；验收只跑 held-out
- **长度偏差学成"短=好"**：报告按 source 输出长度分布，异常批次打回
