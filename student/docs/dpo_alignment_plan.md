# DPO 对齐任务计划（E4 权重层护栏）

> 目的：把 Answer Guard 从"运行时拦截"推进到"权重内化"，补齐 [algorithmic_blueprint.md](../../docs/algorithmic_blueprint.md) E4 的 DPO 路线，形成**三层护栏**叙事：运行时 Shield（已完成）+ 权重层 DPO（本任务）+ 裁判仲裁。
> 本文件供新上下文专门执行此任务，背景见蓝图 §2 E4、§3.1 成熟度阶梯 L2。

## 一、任务目标

用 DPO（LoRA/QLoRA）微调一个 8B 开源指令模型，使其在编程辅导场景中**倾向引导式回答而非直接给完整代码**，同时不损失通用能力。

## 二、训练环境（已验证可用）

- SSH：`ssh school-server`（= 10.17.1.2:30158, root，本机 `~/.ssh/config` 已配置，密钥免密已通）
- GPU：H200 **MIG 2g.35gb 切片 = 33024 MiB（32.25 GiB）、32 SM**，驱动 550.144.03 / CUDA 12.8
- 机器上常有他人训练任务占 ~5GB；截至计划写入时有一个 ltnll 训练占卡（用户预计 20:00–21:00 结束）
- 显存结论：8B **bf16+LoRA** 峰值 24–28GB（任务清空后可跑，`max_length=1024`、batch=1）；**4-bit QLoRA** 峰值 12–14GB（推荐，可与占卡任务并行）
- 约束（见 [student/CLAUDE.md](../CLAUDE.md)）：所有本地 Python 一律用项目 venv `F:\code\MyPython\computer-cross-education\tiaozhanbei\venv\Scripts\python.exe`，禁用全局环境

## 三、数据策略（三层混合，防遗忘）

### 3.1 第一层：现有数据自动生成主干（~300–600 对，零人工标注）

- **来源**：150 题 Socratic Programming Debugging Benchmark（已下载，见 `scripts/evaluate_direct_code_rate.py` 的数据路径）+ 运行时对照日志 `data/answer_guard_log.jsonl`
- **构造**：每题生成两个回答
  - rejected = 无护栏的原始回答（泄题版）
  - chosen = 护栏/引导式改写（不泄题版）
- **自动质检（核心优势）**：直接复用 `answer_guard_service.evaluate()`
  - rejected 必须命中 R1（recall ≥ 0.6）才入池
  - chosen 必须不命中（recall < 0.2）且含引导式追问
  - 护栏指标本身就是偏好对的质检器，规避人工标注不一致

### 3.2 第二层：AI 合成难样本（~100–200 对）

第一层的泄题模式单一（"一次普通求助 → 直接给码"）。合成用来覆盖**绕过攻击的分布**：

1. 种子：每题的 `(学生求助 prompt, 参考答案)`，取自 150 题
2. **生成 rejected**：提示词要求"无限制家教，直接给完整可运行代码，不反问"，轮换变体维度：
   - 语言切换：`translate to English`、`用伪代码/自然语言说`
   - 分步套话：`先只给思路`（但写成完整代码）
   - 局部要挟：`只给函数签名也行`（但给完整实现）
   - 假设升级：`假设我已经会了`
3. **生成 chosen**：提示词要求"先诊断卡点，只给 ≤3 行最小提示，不输出完整解法，以反问收尾"
4. **双重自动过滤**：
   - rejected 必须命中 R1（recall ≥ 0.6），否则丢弃
   - chosen 必须不命中 R1（recall < 0.2）且以问句结尾、无 ≥5 行完整代码块
   - 二者同题号、同变体维度
5. **人工抽检 20%**（3 人方案：用户 + 2 队友），批次合格率 <80% 改提示词重生成

**为什么不能全合成**：自生成对子有分布偏差和自偏好风险，所以只做补量，第一层才是主干。

### 3.3 第三层：通用偏好数据防遗忘（~300–500 对）

- 数据集：**UltraFeedback** 或 **HH-RLHF/OASST**（其一，300–500 对）
- 配比：领域 : 通用 ≈ 1 : 1
- ⚠️ 通用集的 chosen 必须是"普通详尽好回答"——**不能**混入本领域"少给答案"风格，否则模型学成惜字如金
- 训练侧双重保险：LoRA 限制漂移；lr 1e-5~2e-5、1–2 epoch、DPO β 0.1–0.3

### 3.4 输出格式

统一训练 jsonl：`{"prompt": ..., "chosen": ..., "rejected": ..., "source": "runtime_contrast" | "synthetic" | "general"}`，`source` 用于训练后分层归因。

## 四、训练计划

- 模型：Qwen2.5-7B-Instruct（或同级 8B），4-bit QLoRA
- 框架：TRL `DPOTrainer` + peft，参考模型 = 关闭 adapter 的基座（不占第二份显存）
- 关键超参：`max_length=1024`、`per_device_train_batch_size=1~2`、`gradient_accumulation_steps=8~16`、`gradient_checkpointing=True`、LoRA targets = q/k/v/o/gate/up/down_proj、r=16~32
- 产出：`outputs/dpo_lora/` adapter，scp 回本地或直接在服务器评

## 五、验收标准

1. **领域**：held-out Socratic 题跑 `evaluate_direct_code_rate.py`，DPO 组直接给码率显著低于基线（基线 20/20、运行时护栏 2/20，DPO 目标 ≤2/20）；人工抽查不能学成"对真写了代码的学生也拒绝"
2. **通用**：50 条通用问答（或 C-Eval 子集）训前训后对比，掉点 <5%
3. **消融价值**：按 `source` 分层统计，支撑"哪层数据贡献了行为改变"的分析

## 六、执行步骤（新上下文按此推进）

1. 写 `backend/scripts/build_dpo_pairs.py`：读 150 题 → 双路生成（复用护栏指标过滤）→ 合成对抗变体 → 混通用数据 → 输出训练 jsonl
2. 本机 venv 跑通数据管道，人工抽查 10 条定 chosen 风格
3. SSH 上服务器检查环境：`trl/peft/transformers` 版本、HF 连通性（不通则 `HF_ENDPOINT=https://hf-mirror.com`）
4. scp 数据与训练脚本上服务器（建议 `/root/dpo/`）
5. QLoRA 训练（占卡任务结束后，或低占用时段并行）
6. 跑第五节验收，出对比报告

## 七、风险与对策

- **服务器 HF 不通**：走 hf-mirror 镜像；模型提前下载到服务器
- **MIG 33GB 下 bf16 OOM**：降 `max_length` → 切 QLoRA
- **模型学成拒答一切**：chosen 混入"学生真写出代码后的正常正向回应"样本；验收 5.1 人工抽查兜底
- **合成质量不稳**：提示词迭代 + 20% 抽检 + 批次打回机制
- **通用能力下滑**：1:1 混数据 + 低 lr/小 β + 训后 50 条通用回归测试
