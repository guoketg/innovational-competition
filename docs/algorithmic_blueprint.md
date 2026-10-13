# 从算法内核到顶会方法：个性化苏格拉底式编程辅导平台技术蓝图

> 配套文档：[参赛可行性分析](file:///f:/code/MyPython/computer-cross-education/competition_fit_analysis.md) ｜ [文献综述](file:///f:/code/MyPython/computer-cross-education/socratic_programming_tutor_literature_review.md)
> 目标：把这个项目从"提示词技巧 + 教育应用"抬升到"**有算法内核、有对齐方法、有评测科学、可发论文**"的层次。

---

## 0.0 落定取舍（2026-10 对照代码库盘点后定稿，以此为准）

蓝图不是全部照做。以下决议以**已跑通、有数字、可演示**为唯一标准，后续开发与申报书均按此执行：

| 决议 | 对象 | 理由 |
|------|------|------|
| ✅ **继续做深** | E4 输出护栏（✅ qa_router `/ask` + `/ask/stream` 双链路已接入，含输入侧关卡识别；下一步：升级为"重生成再检"） | 全蓝图唯一有对照数字的组件（deepseek-chat 30 题双口径：规则口径基线直给 24/30 → 护栏后 16/30；LLM 裁判口径 28/30 → 24/30；触发 12/30，长代码 3→0，规则-裁判一致 48/60） |
| ✅ **正在做** | E4-DPO 权重层对齐（数据管道已建成，见 [dpo_alignment_plan.md](../student/docs/dpo_alignment_plan.md)） | 测评泄露/false-refusal/时机边界三个死因均已解法 |
| ✅ **保持现状** | E3 规则版教学动作（6 moves 分层策略）+ 六步编排闭环 | 可审计、可演示；分层结构已对应蓝图 SayCan 式高低分离 |
| ✅ **保持现状** | 评测脚本族（A/B 对照 + 自动指标 + 人工核验） | 性价比最高，论文方法论骨架 |
| 🔧 **打折落地** | E1 → 保留启发式掌握度，**✅ 已落地：hint_level 改为掌握度驱动**（stage_mastery/mastery_hint_level，不训 BKT/DKT/AKT，无数据无收益） | 一句话改动接上"脚手架密度自适应"卖点，投入产出比最高 |
| 🔧 **打折落地** | E2 → FAULT_PROFILES + AST 检查定位为"规则版诊断"，不训分类模型 | 已是"可验证的分类任务"，够用 |
| 🔧 **打折落地** | 迁移测验 → 保留即时变式；延迟测验降级为复习提醒，**不做 RCT** | 需真实学生数据，竞赛不现实 |
| 🔧 **打折落地** | E5 → 绕过/越狱话术仅作 DPO 数据（A/X 层），**不做模拟学生 rollout** | 数据层价值已兑现 |
| ❌ **明确不做** | Constitutional AI | 零代码基础，与 DPO 职责重叠 |
| ❌ **明确不做** | gaming / AI 依赖检测 | 需真实学生数据；代码已声明不判定作弊（capability_service） |
| ❌ **明确不做** | 在线 RL（PPO / 模拟学生训练策略） | 蓝图 §8 自认成本高，取"分层 + 离线 DPO"轻量组合 |
| ❌ **明确不做** | DKT/AKT 论文线、E1/E2 独立成文 | 归入申报书"相关工作与展望"，不当开发任务 |

**E1/E2/E5 的正确用法**：写进申报书的"相关工作与展望"，不作为开发任务排期。

---

## 0.1 项目定位（2026-10 定稿）

**面向计算机基础课群的个性化辅导平台：以编程实践为教学闭环载体，覆盖"程序设计 → 数据结构 → 算法"三门核心基础课。**

定位的三层含义：

1. **不是"单纯的编程引导"**——编程（写代码）只是载体，教学对象是课程知识点：变量与控制流（1-1~1-3）、树与堆等数据结构（2-1~2-4）、图与并查集（3-1~3-3）、排序/缓存/工具箱等算法与系统基础（4-1~4-3）。每一关的教学闭环（阶段检查 → 掌握度 → 分级提示 → 变式迁移）服务的是知识掌握，而非单纯的代码产出。
2. **也不窄限于"计算机专业"**——平台解决的是"有结构化练习 + 需要过程性反馈"的通用教学场景，编程关卡是第一个课程群；后续扩展（电子、数学等理工科练习关）复用同一套 L1-L5 分层与五大引擎，只换参考答案与检查器。
3. **护栏作用域随定位划界**：关卡考核场景（题面、作业、判题、参考答案索要）严格拦；通用编程问题（开放讨论、概念请教）不触发拦截——与定位 1 对应：**考核的是课程知识掌握，而非封锁编程知识本身**。

**一句话版本**：面向计算机基础课群、以编程闯关为载体的苏格拉底式教学平台——教的是"课程知识怎么掌握"，不是"代码怎么抄"，也不是"怎么写出任意程序"。

---

## 0. 先纠正定位：提示词不是核心，只是最上面的一层渲染

当前思路的问题不是"用了提示词"，而是**把提示词当成了全部**。正确的分层应该是：

```
┌─────────────────────────────────────────────────────┐
│  L5 渲染层：LLM 用自然语言把"决策"说成人话（提示词在此）  │  ← 你现在的全部
├─────────────────────────────────────────────────────┤
│  L4 决策层：本轮该问什么类型的问题、给几级提示（策略模型）│  ← 需要算法
├─────────────────────────────────────────────────────┤
│  L3 诊断层：学生错在哪、错在什么观念（诊断模型）         │  ← 需要算法
├─────────────────────────────────────────────────────┤
│  L2 状态层：学生哪些知识点掌握/未掌握（知识追踪模型）    │  ← 需要算法
├─────────────────────────────────────────────────────┤
│  L1 约束层：如何保证"永远不泄题"（对齐/护栏/形式化保证）  │  ← 需要算法+架构
└─────────────────────────────────────────────────────┘
```

**核心论点**：提示词属于 L5。真正让项目"变成真的"、并且能写进顶会/顶刊的，是 L1–L4 四层算法。下面给出这四层各自的**可落地算法 + 顶会顶刊依据 + 评测方式**。

---

## 1. 形式化：先把问题写成可计算的模型

一切算法都要有一个统一的数学骨架。建议采用**约束下的部分可观测马尔可夫决策过程（Constrained POMDP）**：

- **状态** $s_t = (\text{学习者知识状态 } k_t,\ \text{错误观念集合 } m_t,\ \text{对话历史 } h_t,\ \text{当前代码 } c_t)$  
  其中 $k_t, m_t$ 是**不可直接观测的隐变量**——这正是"部分可观测"的来源，也是必须做"学习者建模"的根本理由。
- **动作** $a_t$ = 辅导者本轮的教学动作（不是直接生成文本，而是先选"教学动作"，如：澄清概念 / 反问定位 / 给类比 / 给第 1 级提示）。
- **观测** $o_t$ = 学生本轮的代码修改、报错、文字回复、通过率。
- **约束** $C$ = 一条硬约束：**动作的输出空间被限制为"不含可直接运行的解决方案代码"**（安全 RL 中的 shield/约束 MDP，见 §5.4）。
- **回报** $R$ = 短期（下一步是否正确/是否自己改对）+ 长期（延迟测验成绩、迁移能力、独立性指标）的组合。

**为什么这步重要**：一旦这样形式化，你的项目就从"做一个提示词工具"变成"在一个约束 POMDP 里做**策略学习 + 状态估计 + 约束满足**"，这三个词各自对应一整条成熟的研究线，可以逐一引用顶会工作。这正是"顶刊顶会级"叙事的入口。

---

## 2. 五大算法引擎

### 引擎 E1｜学习者状态建模（Knowledge Tracing，知识追踪）

> **决议（§0.0）**：不训 BKT/DKT/AKT，保留启发式掌握度；hint_level 掌握度驱动已落地（stage_mastery/mastery_hint_level，2026-10）。本节仅作申报书"相关工作"参考。

- **做什么**：把学生在"知识点/技能组件（Knowledge Component, KC）"上的掌握程度 $k_t$ 建模为随时间演化的隐状态，输出每个 KC 的掌握概率，作为 E3 决策的输入。
- **算法谱系（可直接复现）**：
  - **BKT**（隐马尔可夫模型，Corbett & Anderson）——可解释、参数少，适合冷启动。
  - **DKT**（Piech et al., **NeurIPS 2015**）——用 RNN 建模，是最被广泛引用的深度学习方案，且**在编程练习题上已有专门工作**（Deep Knowledge Tracing on Programming Exercises）。
  - **SAKT / SAINT**（纯注意力）——适配稀疏数据。
  - **AKT**（Ghosh, Heffernan & Lan, **KDD 2020**）——注意力 + 单调注意力机制 + **用 Rasch 心理测量模型正则化**，兼具精度与**可解释性**（适合向评审解释"为什么判断学生没掌握"）。
- **与本项目的结合点**：知识状态直接决定**脚手架密度**（Zone of Proximal Development / 适应性摩擦）：掌握度低→提示更细；掌握度高→提示更抽象甚至不出提示。这条"随能力自适应"正是前面综述里反复强调的机制，此处有了算法载体。
- **可复现难度**：中。公开数据集（ASSISTments 等）+ 开源实现即可起步。
- **产出**：一篇"面向编程苏格拉底辅导的知识组件级知识追踪"可投 EDM / AIED / IJAIED。

### 引擎 E2｜错误观念诊断（Misconception Diagnosis）

> **决议（§0.0）**：不训诊断分类模型；FAULT_PROFILES + AST 检查即"规则版诊断"，定位为已实现组件。本节仅作申报书"相关工作"参考。

- **做什么**：给定（学生代码, 报错, 题目），输出**结构化的诊断结果**：错误观念类别 + 证据 + 根因。这是决定"该问哪类问题"的关键输入。
- **算法谱系（近年活跃，可直接对接）**：
  - **代码嵌入 + 聚类发现错误观念**：Toward Semi-Automatic Misconception Discovery Using Code Embeddings（使用代码分类模型的表征对错误提交聚类）。
  - **自动识别逻辑错误**：Automated Identification of Logical Errors in Programs（**EDM 2025**，用改进的 SANN 表征预测学生表现，短/长期预测均有提升）。
  - **McMining**：自动发现学生代码中的错误观念（2025），并用 **LLM-as-a-judge 做语义匹配评测**。
  - **知识组件抽取**：Pattern-based Knowledge Component Extraction from Student Code Using Representation Learning（**EDM 2025**）。
- **工程形态**：AST / 静态分析提取结构特征 → 表征模型或微调 LLM 做分类 → 输出错误观念标签。**这一步把"讲原理"从 LLM 的自由发挥，变成"可验证的分类任务"**，工程与算法上都更硬。
- **可复现难度**：中—高（需要编程教育数据集，但已有公开数据与标注方案）。
- **产出**：一篇"编程错误观念的自动化诊断 + 苏格拉底式修复"可投 EDM / SIGCSE / ICER / ITiCSE。

### 引擎 E3｜教学对话策略（Pedagogical Dialogue Policy，策略学习）

> **决议（§0.0）**：规则版 6-moves 分层策略保持现状，不做在线 RL；离线对齐只走 DPO（见 E4）。

- **做什么**：根据 $k_t, m_t, h_t$ 选择本轮**教学动作**（问什么、给几级提示）。这是把"苏格拉底式"从口号变成**可学习的策略**。
- **算法谱系（顶会级，且直接对口）**：
  - **RL 对齐教学法**：Macina et al., *From Problem-Solving to Teaching Problem-Solving: Aligning LLMs with Pedagogy using RL*（**EMNLP 2025**）——用**合成学生-导师交互**做在线 RL，**7B 模型逼近 LearnLM**，并能通过调节惩罚权重在"教学性 vs. 答案正确率"的 Pareto 前沿上**可控取舍**。这条几乎就是你项目的"研究版"。
  - **分层策略（推荐借鉴）**：高层"导演策略"从有限教学动作中选一个（如 8 种 teaching moves），低层 LLM 负责把这个动作渲染成自然语言（SayCan 式高低分离）。好处：**动作空间离散可控、可解释、可审计**——也天然适合竞赛演示。
  - **苏格拉底专用 RL**：PEARL（Training Socratic Tutors with Pedagogically Aligned RL，2026）；Rewarding How Models Think Pedagogically（2026，把辅导形式化为 MDP 并加"思维奖励"）。
  - **规划式提问**：TreeInstruct（**EMNLP Findings 2024**）——用状态空间规划构造"问题树"，多轮分层追问引导自主定位 Bug；这与你"报错时不直接修、用提问引导"的目标**完全一致**。
  - **回合级验证器**：Training Turn-by-Turn Verifiers for Dialogue Tutoring Agents: LLMs as Your Coding Tutors（2025）——训练一个"逐步打分"的验证器来评估每轮辅导质量，可用于 RL 奖励信号。
  - **BKT 状态 + 提示分级 + RL**：RLOO/DPO hint generation，动作空间为四级提示层级（具体数字→计算步骤→概念洞察→重述问题），奖励=下次作答正确率＋教学合规约束。
- **本质**：**提示词在这里退化为"动作渲染器"**，真正决定行为的是策略模型。这就是你要的"不局限于提示词"。
- **可复现难度**：高（需仿真环境或大量交互数据），但**分层+离线RL/DPO 的简化版**可在课程规模内实现。
- **产出**：可投 EMNLP / ACL / AIED / L@S，属"教育 NLP + RL"交叉热点。

### 引擎 E4｜约束生成与"答案释放时机"保障（Constrained Generation / Timing Guarantee）

- **做什么**：让"答案在正确时机释放"成为**可保证的系统性质**——首轮绝不直接给出/修改/补全代码，学生展示尝试后第二轮按脚手架释放完整讲解，而非"希望提示词管住模型"。这是本项目最独特的算法贡献点（理念修正 2026-10-12：控制的是**时机**，不是**拒绝**；详见 [创新性与顶会文献支撑.md](创新性与顶会文献支撑.md) §四）。
- **算法谱系**：
  - **偏好对齐（DPO）**：Rafailov et al., *Direct Preference Optimization*（**NeurIPS 2023**）——构造"(首轮苏格拉底式引导) ≻ (过早直接给答案)"与"(次轮完整讲解) ≻ (该给不给)"的偏好对，把"先引导、后给解"的时机策略内化进模型权重。教育场景 DPO 已有顶会先例：**Findings of ACL: BEA 2026** 的 SFT→DPO 数学纠错与 Tutor Personas 偏好优化，证明教学行为可通过偏好对齐权重内化。
  - **宪法式 AI（Constitutional AI）**：Bai et al. 2022——把你的**教学原则写成一部"宪法"**，让模型对自身输出"自我批评→修订"，从而在训练期注入"不代做"原则。对竞赛而言，"一部面向编程教学的宪法"本身就是一个可讲的创新点。**【决议（§0.0）：明确不做——与 DPO 职责重叠，零代码基础，本条仅保留作相关工作引用】**
  - **护栏（Guardrails）**：输入/输出双向控制——输入侧拦截"诱导要答案/越狱"式提问，输出侧做泄漏检测。使其成为**架构级**能力而非提示词技巧。
  - **运行时屏蔽（Shielding）**：Alshiekh et al., *Safe Reinforcement Learning via Shielding*（**AAAI 2018**）——用外部 monitor 在动作落地前做形式化检查。对应到本项目：**对每条待输出内容做"与参考解/解法片段的相似度校验"，超阈值即拦截重生成**，形成"永远不泄题"的硬保证。这把教育约束升级为**约束满足问题**，是极有分量的技术架构创新。
  - **时机释放阀（✅ 已落地，2026-10-12）**：Shield 不是无状态的——R1 命中时若学生本轮已贴出 ≥3 行自己的代码，或同用户同关卡累计被拦 ≥2 轮，则放行"参考实现 + 对照讲解"（`severity=released`，不拦截不重生成）。使 E4 从"硬保证不泄题"升级为"**该问时问、该讲时讲**"的时机保证，直接对应 PNAS 2025 Bastani（直给伤害保持测验、教师设计 hint 可避免）与 worked-example fading（ITiCSE 2024）。实现见 `answer_guard_service.evaluate_release()`，日志 channel=`released`/`stream_released`。
- **可复现难度**：中（DPO 微调小模型即可起步；shield 可用嵌入相似度+规则实现）。
- **产出**：可投 NeurIPS/ICML（对齐与约束方向）/ EMNLP，或作为强工程亮点。

### 引擎 E5｜模拟学生与对抗评测（Simulated Students & Adversarial Evaluation）

> **决议（§0.0）**：不做模拟学生 rollout；绕过/越狱话术仅作为 DPO 数据（build_dpo_pairs 的 A/X 层）。本节仅作申报书"相关工作"参考。

- **做什么**：在真实学生数据稀缺时，用**可控模拟学生**作为环境来训练 E3 策略、并作为"红队"测试 E4 的抗绕过能力。
- **算法谱系**：
  - **可控学生模拟**：PEARL（2026）——**解耦**学生的"知识状态"与"行为倾向"（如偷懒、急于要答案），分别建模再生成回复，避免把两者混在一个提示里。
  - **学习者式模拟**：Teaching Language Models How to Code Like Learners: Conversational Serialization for Student Simulation（Koutcheme & Hellas）——让模型像"学习者"而不是"专家"那样写代码，用于生成逼真的错误代码。
  - **仿真训练范式**：EMNLP 2025 的 Macina 工作证明——**纯合成学生-导师交互**即可训练出接近商用水平的导师模型，成本远低于人工标注。
- **价值**：既解决"没有学生数据怎么训练"的冷启动问题，又提供**可复现、可对抗**的评测环境（含"学生反复索要答案""提示注入"等对抗样本）。
- **可复现难度**：中。
- **产出**：可作为 EDM/AIED 的独立贡献，或论文中的"环境构建"章节。

---

## 3. 两条闭环

### 3.1 训练闭环（怎么把系统"练"出来）
```
模拟学生(E5) ──rollout──► 辅导者策略(E3) ──动作──► 渲染(L5提示词/LLM)
                                ▲                        │
                                │      奖励 = 短期作答正确率
                                │           + 长期学习增益
                                │           + 教学合规约束(E4)
                                └──── RL(PPO)/DPO/离线RL ◄─┘
   知识追踪(E1) ──► 状态输入             错误观念诊断(E2) ──► 状态输入
```
- **冷启动**：先用 E1/E2 的监督模型 + DPO 偏好对（含"首轮引导 ≻ 过早给码、次轮讲解 ≻ 该给不给"的时机偏好）做一轮对齐。
- **进阶**：引入模拟学生做在线 RL，复现 EMNLP 2025 的"可控教学性—正确率 Pareto 前沿"。

### 3.2 评测闭环（怎么证明有效——这是拿奖与发论文的关键）
> **决议（§0.0）**：✅ 保留 LLM-as-a-judge 与过程分析（已实现）；✅ 保留即时变式迁移测验；❌ 不做 gaming 检测（需真实学生数据，代码已声明不判定作弊）；❌ 不做 RCT/延迟测验流程（降级为 `next_review_at` 复习提醒）。
- **学习效果：延迟测验 + 迁移测验**（前后测、以及**关掉 AI 后的独立解题**），报告效应量。这是被验证过的方法论模板："练习期看似学会、脱机后崩溃"正是要防的假象。
- **教学质量的自动评测（LLM-as-a-judge）**：MRBench 教学能力维度分类法（Maurya et al. 2025）、Tutor Move 评估（2025，检测"有效表扬/错误应对"准确率 82–98%）、开放式反馈质量评分量规（2026）。用于**自动审计每轮提问是否"引导而非泄题"**。
- **反作弊/反依赖检测**：复用 ITS 领域的 **gaming-the-system 检测**（Baker et al. 的决策树分类器，AUC≈0.72）——迁移为"**AI 依赖度 / 规避努力检测**"，这与你综述里"复制粘贴式规避努力"的证据直接衔接。
- **过程分析**：对交互日志做学习分析/过程挖掘，量化"自己改对的比例""提示层级下降趋势"。
- **统计**：采用 RCT 或准实验设计，报告效应量并与已有元分析对比（注意：AI 教育元分析效应量差异很大，有 g≈0.86、g≈0.61 等不同结论，引用时须标注异质性，不可当成定论）。

---

## 4. 系统架构（可直接画进申报书）

```
                    ┌──────────────── 前端：Web IDE / VS Code 插件 ────────────────┐
                    │  代码编辑器 · 运行沙箱 · 单步调试 · 对话面板 · 能力看板          │
                    └───────────────────────────┬────────────────────────────────┘
                                                │ 学生代码/报错/对话
   ┌────────────────────────────────────────────▼────────────────────────────────┐
   │                            编排层 Orchestrator                                │
   │   ① 解析提交 → ② 调用诊断(E2) → ③ 更新知识状态(E1) → ④ 策略决策(E3)            │
   │   → ⑤ 生成 + 约束校验(E4, shield) → ⑥ 输出；不通过则重生成                     │
   └───┬─────────────┬──────────────┬───────────────┬───────────────┬────────────┘
       │             │              │               │               │
  ┌────▼───┐   ┌─────▼─────┐  ┌─────▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐
  │ E1 知识 │   │ E2 错误观念│  │ E3 教学策略 │  │ E4 约束护栏│  │ E5 模拟学生 │
  │ 追踪    │   │ 诊断       │  │ (RL/分层)  │  │ (DPO/盾)   │  │ /对抗评测   │
  └────────┘   └───────────┘  └────────────┘  └────────────┘  └────────────┘
                                                │
                                    ┌───────────▼────────────┐
                                    │ 数据层：提交日志/标注/  │
                                    │ 知识图谱/偏好对/评测集  │
                                    └────────────────────────┘
```

**关键设计点**：E4 的约束校验位于"输出前"的网关位置，是**架构级**的，而不是写在提示词里的一句话——这是从"提示词方案"跃迁到"系统方案"的标志。

---

## 5. 顶会顶刊地图（可直接作为综述/相关工作骨架）

| 引擎 | 代表方法 | 级别 / 场合 | 与本项目的关系 |
|------|----------|-------------|----------------|
| E1 知识追踪 | BKT / **DKT (NeurIPS 2015)** / SAKT / **AKT (KDD 2020)** | 顶会 + EDM | 状态估计输入 |
| E2 错误观念诊断 | Code Embeddings 聚类(2021) / **逻辑错误识别 (EDM 2025)** / McMining(2025) | EDM / SIGCSE / ICER | 诊断输入 |
| E3 教学策略 | **From Problem-Solving to Teaching Problem-Solving (EMNLP 2025)** / TreeInstruct (EMNLP-F 2024) / PEARL(2026) / Turn-by-Turn Verifier(2025) | EMNLP / ACL / AIED | 决策核心 |
| E4 约束/对齐 | **DPO (NeurIPS 2023)** / Constitutional AI(2022) / Guardrails / **Shielding (AAAI 2018)** | NeurIPS / ICML / AAAI | 不泄题保证 |
| E5 模拟学生 | PEARL(2026) / Conversational Serialization 学生模拟 / BEA 2025 | EDM / AIED / BEA | 环境与红队 |
| 评测 | **MRBench (2025)** / Tutor Move 评估(2025) / Gaming 检测(Baker et al.) / AI 教育元分析 | AIED / EDM / 教育期刊 | 效果证据 |
| 学习科学底座 | VanLehn 2011 辅导效应 / 有效失败(Kapur) / 脚手架渐退 / 认知负荷(Sweller) / 合意困难(Bjork) | 元分析与经典理论 | 理论合法性 |

> 注：E1–E5 中，**E3（RL 教学策略）与 E4（约束对齐）是通往顶会的主路**；E1/E2 是系统必需的"硬核骨架"；E5 是让 E3 可训练的"环境基础设施"。

---

## 6. 成熟度阶梯：不要一口吃成胖子

| 层级 | 目标 | 算法内容 | 对应产出 |
|------|------|----------|----------|
| **L1 可跑通**（竞赛底线） | 完整可演示产品 | 规则+BKT 估计掌握度；规则式教学动作选择；输出侧相似度 shield；提示词渲染 | 一份完整软件 + 测试报告 |
| **L2 有算法**（竞赛拿奖线） | 诊断+状态+约束均模型化 | DKT/AKT 知识追踪；表征式错误观念分类；分层策略（规则/离线RL）；DPO 内化"先引导后给解"时机策略；LLM-judge 自动评测 | 可投 EDM/AIED/ITiCSE |
| **L3 研究级**（顶会/顶刊线） | 端到端学习 + 形式化保证 | 模拟学生在线 RL（复现 EMNLP 2025 范式）；形式化 shield 保证不泄题；RCT + 延迟/迁移测验 | 可投 EMNLP/ACL/NeurIPS 或 IJAIED |

**建议**：竞赛作品瞄准 **L2**，把 **L3 的 1–2 个点**（如"形式化不泄题保证"或"模拟学生红队"）做成亮点写进申报书的"技术架构创新"。

> **决议（§0.0）修正**：L3 亮点取"**形式化不泄题保证**"（输出护栏 + DPO，已有对照数字）；"模拟学生红队"不做（见 E5 决议）。当前实际位置：L1 全部达标，L2 约完成一半（E3/E4 规则版已实现，E1/E2 以启发式/规则版代替模型化），缺口 = DPO 训练（数据管道已建成，871 对质检通过；训练暂缓）+ 护栏"重生成再检"推广（CodeLab held-out 三臂已有 guarded_regen 初检，见 `student/backend/data/eval/codelab_heldout_report.json`）。~~hint_level 掌握度驱动~~已落地（stage_mastery/mastery_hint_level，2026-10）。

---

## 7. 与竞赛评分 & 论文产出的对齐

| 评分项 | 本蓝图的对应算法 | 论文/成果载体 |
|--------|------------------|----------------|
| 创新性(20) | E4 约束对齐架构 + E3 策略学习（"拒绝代做"的算法化） | 对齐/教育NLP方向投稿 |
| 技术实现(20) | E1 知识追踪 + E2 诊断 + E3 分层策略 + E4 盾 | 系统论文/工具论文 |
| 功能完整性(20) | 编排层六步闭环 + 前端闭环演示 | 软件著作权 + 演示视频 |
| 方案完整性(20) | 本蓝图 + 六章方案书 + 架构图 | 申报书 |
| 应用价值(15) | 评测闭环（延迟/迁移测验 + 依赖检测） | 教育期刊/实证论文 |
| 总结展望(5) | L1→L3 路线图 | — |

**一举两得**：E3/E4/E5 的组合本身就构成可投稿的研究贡献（"约束下的苏格拉底式编程辅导策略学习"），竞赛与论文可以共用同一套系统与实验。

---

## 8. 风险与取舍

1. **算力与人力**：L3 的在线 RL 成本高。**取舍**：竞赛版本用"分层 + 离线 RL/DPO + 模拟学生"的轻量组合，不必上在线 PPO。
2. **数据冷启动**：编程错误观念标注数据稀缺。**取舍**：先用公开数据集（知识追踪/编程教育）预训练 E1/E2，再以模拟学生+少量真实课程数据微调 E5/E3。
3. **对齐的"对齐税"**：DPO 若过度强化"首轮不给"约束，模型会滑向另一端——该给时也不给（false refusal / 过度拒），这同样是缺陷。**取舍**：偏好对同时含"次轮恰当给码 ≻ 该给不给"两端样本，评测用双指标监控两端（首轮不给码率防过早给、次轮给码率防过度拒），并设"最小必要信息"下限。
4. **评价效度**：LLM-as-a-judge 自身有偏差。**取舍**：以人工标注子集校准 judge，并报告一致性。
5. **不要过度承诺"新算法"**：诚实定位为"**把成熟算法（知识追踪/RL/对齐/屏蔽）在教育约束下做系统性整合与实证**"，这在国际上被认可为扎实贡献，比空喊"全新算法"更稳。

---

## 9. 参考文献（按引擎归类）

**E1 知识追踪**
1. Piech et al. *Deep Knowledge Tracing*. NeurIPS 2015. http://papers.neurips.cc/paper/5654-deep-knowledge-tracing.pdf
2. Piech et al. *Deep Knowledge Tracing on Programming Exercises*. 2015. http://web.stanford.edu/~cpiech/bio/papers/dktCode.pdf
3. Ghosh, Heffernan, Lan. *Context-Aware Attentive Knowledge Tracing (AKT)*. KDD 2020. https://arxiv.org/pdf/2007.12324
4. *Enhancing Knowledge Tracing through Leakage-Free and Recency-Aware Embeddings*. 2025. https://arxiv.org/html/2508.17092v2

**E2 错误观念诊断**
5. *Toward Semi-Automatic Misconception Discovery Using Code Embeddings*. 2021. https://arxiv.org/html/2103.04448v1
6. *Automated Identification of Logical Errors in Programs*. EDM 2025. https://arxiv.org/html/2505.10913v1
7. *McMining: Automated Discovery of Misconceptions in Student Code*. 2025. https://arxiv.org/html/2510.08827v1
8. *Pattern-based Knowledge Component Extraction from Student Code*. 2025. https://arxiv.org/html/2508.09281v3

**E3 教学策略**
9. Macina et al. *From Problem-Solving to Teaching Problem-Solving: Aligning LLMs with Pedagogy using RL*. EMNLP 2025. https://aclanthology.org/2025.emnlp-main.15.pdf
10. *Instruct, Not Assist: TreeInstruct (Socratic Code Debugging)*. EMNLP Findings 2024. https://arxiv.org/html/2406.11709
11. *PEARL: Training Socratic Tutors with Pedagogically Aligned RL*. 2026. https://arxiv.org/html/2605.29582
12. *Rewarding How Models Think Pedagogically*. 2026. https://arxiv.org/html/2601.14560
13. *Training Turn-by-Turn Verifiers for Dialogue Tutoring Agents: LLMs as Your Coding Tutors*. 2025. https://arxiv.org/html/2502.13311v2
14. *Hey Chat, Can You Teach Me? Structuring Socratic Dialogue for Human Learning*. 2026. https://arxiv.org/html/2606.11744v1
15. *Learning Adaptive Tutor Policies ... via Offline RL*. Stanford CS224R. https://cs224r.stanford.edu/projects/pdfs/Aditya%20Bora%20submission_416257309/Aditya_Bora_CS224R_Final_Paper.pdf
16. *RL-Powered Hint Generation for Adaptive Math Tutoring (RLOO/DPO + BKT)*. Stanford CS224R. https://cs224r.stanford.edu/projects/pdfs/Prabu%20Ganesh%20Ravindren%20submission_415987469/CS224r_Project.pdf
17. KITE — Retrieval-Augmented Socratic Tutoring. https://aclanthology.org/people/arto-hellas/unverified/

**E4 约束与对齐**
18. Rafailov et al. *Direct Preference Optimization*. NeurIPS 2023. https://arxiv.org/html/2305.18290
19. Bai et al. *Constitutional AI: Harmlessness from AI Feedback*. 2022. https://arxiv.org/pdf/2212.08073
20. Alshiekh et al. *Safe Reinforcement Learning via Shielding*. AAAI 2018.
21. AI Guardrails: Input/Output Controls. https://www.openlegion.ai/fr/learn/ai-agent-guardrails

**E5 模拟学生**
22. Koutcheme & Hellas. *Teaching Language Models How to Code Like Learners: Conversational Serialization for Student Simulation*. https://www.semanticscholar.org/paper/d3151b71b95d8bb5803476fceec41aae4022394f
23. BEA 2025 Workshop — LLM-based student simulation design. https://aclanthology.org/people/jakub-macina/

**评测与学习科学**
24. Maurya et al. *Towards Reward Modeling for AI Tutors / MRBench taxonomy*. 2025. https://arxiv.org/html/2603.24375
25. *Leveraging LLMs to Assess Tutor Moves in Real-Life Dialogues*. 2025. https://arxiv.org/html/2506.17410v1
26. *Consistently Good vs. Occasionally Great: A Rubric for Open-Ended Feedback Quality*. 2026. https://arxiv.org/html/2608.21850
27. Baker, Corbett, Koedinger. *Detecting Student Misuse of Intelligent Tutoring Systems*. ITS 2004. https://pact.cs.cmu.edu/koedinger/pubs/Baker,%20Corbett,%20Koedinger%20ITS04.pdf
28. VanLehn. *The Relative Effectiveness of Human Tutoring, ITS, and Other Tutoring Systems*. 2011.
29. *Meta-Analysis of Artificial Intelligence in Education* (g≈0.86). https://files.eric.ed.gov/fulltext/EJ1465704.pdf
30. Bjork & Bjork — Desirable Difficulties; Sweller — Cognitive Load Theory. https://www.aft.org/ae/winter2025-2026/kirschner_hendrick_heal
31. *Your Students Don't Use LLMs Like You Wish They Did* (illusion of fluency / Dunning-Kruger). 2026. https://arxiv.org/html/2604.23486

---

*本蓝图的性质是"技术路线设计"，所列算法均为已验证的公开方法，项目定位为在"编程教育 + 不泄题约束"这一特定场景下做**系统性整合与实证验证**，而非提出新底层算法。这一诚实定位本身就是可被顶会/顶刊接受的有效贡献形式。*
