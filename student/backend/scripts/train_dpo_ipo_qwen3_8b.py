# -*- coding: utf-8 -*-
"""DPO / IPO 偏好对齐统一训练脚本：Qwen3-8B + LoRA（源自 llmTuning 云端训练仓库）

================================================================================
一、这个脚本做什么
================================================================================
用本仓库的偏好对数据（student/backend/data/dpo/）对 Qwen3-8B 做偏好对齐训练：

- --method dpo  → TRL loss_type="sigmoid"（标准 DPO），产物 outputs/alignment-8B-dpo/
- --method ipo  → TRL loss_type="ipo"（IPO，Identity Preference Optimization），
                  产物 outputs/alignment-8B-ipo/

两种方法共用同一套数据、超参与代码路径，只有 loss_type / 产物目录 / 指标标签不同。
数据为工具决策版偏好对（convert_dpo_to_tools.py 产出）：
  dpo_pairs_tools.jsonl      训练集（1040 对）
  dpo_eval_pairs_tools.jsonl 评估集（304 对）
格式：{"prompt": [messages], "chosen": str, "rejected": str}

================================================================================
二、环境说明（不看这段跑不了）
================================================================================

【运行机器】
- 训练只能在学校 GPU 服务器上跑（见 student/docs/dpo_alignment_plan.md §二）：
  ssh school-server（10.17.1.2:30158, root），H200 MIG 2g.35gb 切片 = 33GB 显存。
- 显存结论：8B bf16 + LoRA 峰值 24–28GB（本脚本 batch=1、max_length=2560 可直接跑）；
  若卡上有他人任务占 ~5GB，可把 MAX_SEQ_LENGTH 降到 1536，或改 4-bit QLoRA（12–14GB）。

【Python 环境——必须用服务器上的 .venv】
- 必须：`.venv/bin/python`（torch 2.7.0+cu126）。系统 python3 装了 vllm 0.9.2，
  与 transformers 5.5.0 冲突，导入即崩——绝对不要用系统 python 跑本脚本。
- 依赖清单（.venv 里应已具备）：
    torch>=2.7（cu126）、unsloth、trl==0.24.x、transformers>=5.x、
    datasets、peft、bitsandbytes（adamw_8bit 优化器需要）
- 本脚本开头已内置兼容补丁（沿用 llmTuning 踩坑记录）：
    1) transformers 5.x 的 _is_package_available() 返回元组，trl 0.24.0 按 bool 处理
       会误判 mergekit 等可用 -> 这里修正回 bool；
    2) 显式禁用 trl 的 vllm availability（DPO/IPO 不用 vLLM，避开 vllm 冲突）。
- 本机（Windows 项目 venv）没有这些训练依赖，属于预期：本机只能跑 --check 数据自检
  和单元测试，训练必须上服务器。

【模型与数据上服务器】
- Qwen/Qwen3-8B 必须已在服务器 HF 本地缓存。脚本默认 HF_HUB_OFFLINE=1 纯本地加载；
  若没缓存，先联网拉一次（走镜像）：
      HF_ENDPOINT=https://hf-mirror.com huggingface-cli download Qwen/Qwen3-8B
- 把数据与脚本 scp 上服务器（保持相对结构，或用 --train-file/--eval-file 指路径）：
      scp student/backend/data/dpo/*.jsonl school-server:/root/dpo/data/
      scp student/backend/scripts/train_dpo_ipo_qwen3_8b.py school-server:/root/dpo/

【运行命令】
  # 1) 先自检（数据文件、JSON 格式、依赖、Python 版本，不需要 GPU）
  .venv/bin/python train_dpo_ipo_qwen3_8b.py --check

  # 2) 冒烟测试（5 步验证全流程，约几分钟）
  DPO_MAX_STEPS=5 .venv/bin/python -u train_dpo_ipo_qwen3_8b.py --method ipo

  # 3) 全量训练（长任务必须后台化，SSH 断开会杀进程）
  setsid nohup .venv/bin/python -u train_dpo_ipo_qwen3_8b.py --method ipo \
      > train_ipo.log 2>&1 < /dev/null &
  # DPO 同理换 --method dpo

【产物】
  outputs/alignment-8B-{dpo|ipo}/lora/          LoRA adapter + chat_template
  outputs/alignment-8B-{dpo|ipo}/metrics.json    训练/评估曲线 + 定性抽样

【注意】
- Qwen3 chat_template 的空 <think> 块（enable_thinking=false 时预填）是训练分布的
  一部分，脚本保存后会自动校验，勿手工删。
- 训练日志 grep 关键词：loss_type、rewards/margins。
================================================================================
"""

import argparse
import importlib.util
import json
import os
import sys

# ---------- 路径常量（相对脚本自身定位，服务器/本机均可直接跑） ----------
SCRIPT_PATH = os.path.abspath(__file__)
BACKEND_DIR = os.path.dirname(os.path.dirname(SCRIPT_PATH))      # student/backend/
DEFAULT_TRAIN_FILE = os.path.join(BACKEND_DIR, "data", "dpo", "dpo_pairs_tools.jsonl")
DEFAULT_EVAL_FILE = os.path.join(BACKEND_DIR, "data", "dpo", "dpo_eval_pairs_tools.jsonl")
DEFAULT_OUTPUT_ROOT = os.path.join(BACKEND_DIR, "outputs")

# ---------- 训练超参（两种方法共用，来源 llmTuning 已验证配置） ----------
MODEL_ID = "Qwen/Qwen3-8B"
MAX_SEQ_LENGTH = 2560     # 数据 total p99=1463 / max=2251，2560 覆盖全部样本
MAX_PROMPT_LENGTH = 2048  # prompt max=2055（个别长 prompt，允许接近全长）
MAX_COMPLETION_LENGTH = 1536  # completion max≈1312，不截断
LORA_R = 16
BATCH_SIZE = 1            # 33GB MIG 显存限制
GRAD_ACCUM = 4            # 有效 batch_size = 4
NUM_EPOCHS = 1            # 1040 条偏好对，1 epoch 足够，多 epoch 易过拟合
LR = 1e-5                 # LoRA-DPO/IPO 常用 5e-6 ~ 2e-5
BETA = 0.1                # DPO/IPO 正则系数（TRL 默认 0.1）

# 方法注册表：dpo → sigmoid 损失，ipo → ipo 损失
METHODS = {
    "dpo": {"loss_type": "sigmoid", "label": "DPO"},
    "ipo": {"loss_type": "ipo", "label": "IPO"},
}


def method_config(method):
    """按方法名取 {loss_type, label}，非法方法名抛 ValueError。"""
    key = str(method or "").strip().lower()
    if key not in METHODS:
        raise ValueError(
            f"未知方法 {method!r}，仅支持: {', '.join(sorted(METHODS))}"
        )
    cfg = dict(METHODS[key])
    cfg["method"] = key
    cfg["output_dir"] = os.path.join(DEFAULT_OUTPUT_ROOT, f"alignment-8B-{key}")
    return cfg


def validate_pair_file(path):
    """校验偏好对 JSONL：存在、每行 JSON、含 prompt/chosen/rejected 三键。

    返回 {"path", "exists", "count", "ok", "errors"}，errors 只保留前 5 条避免刷屏。
    """
    result = {"path": path, "exists": False, "count": 0, "ok": False, "errors": []}
    if not os.path.isfile(path):
        result["errors"].append("文件不存在")
        return result
    result["exists"] = True
    errors = []
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                count += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"L{lineno}: JSON 解析失败 ({e.msg})")
                    continue
                if not isinstance(obj, dict):
                    errors.append(f"L{lineno}: 非 JSON 对象")
                    continue
                missing = [k for k in ("prompt", "chosen", "rejected") if k not in obj]
                if missing:
                    errors.append(f"L{lineno}: 缺字段 {missing}")
    except OSError as e:
        errors.append(f"读取失败: {e}")
    result["count"] = count
    result["errors"] = errors[:5]
    result["ok"] = count > 0 and not errors
    return result


def check_environment(train_file, eval_file, output_dir):
    """环境自检（无需 GPU）：Python 版本、数据文件、训练依赖、输出目录。

    依赖用 find_spec 探测（不实际 import，快且无副作用）。
    返回 {"ok", "items": [{"name", "ok", "detail"}]}；ok = 所有项通过。
    """
    items = []

    # 1) Python 版本
    ver = sys.version_info
    py_ok = (ver.major, ver.minor) >= (3, 10)
    items.append({"name": "python", "ok": py_ok,
                  "detail": f"{ver.major}.{ver.minor}.{ver.micro}"
                            + ("" if py_ok else "（需要 >= 3.10）")})

    # 2) 数据文件
    for name, path in (("train_file", train_file), ("eval_file", eval_file)):
        v = validate_pair_file(path)
        detail = (f"{v['count']} 条样本" if v["ok"]
                  else f"{path} -> " + ("; ".join(v["errors"]) or "0 条样本"))
        items.append({"name": name, "ok": v["ok"], "detail": detail})

    # 3) 训练依赖（仅训练路径需要；--check 在本机缺依赖属预期）
    deps = ["torch", "unsloth", "trl", "transformers", "datasets", "peft",
            "bitsandbytes"]
    for dep in deps:
        try:
            found = importlib.util.find_spec(dep) is not None
        except (ImportError, ValueError):
            found = False
        items.append({"name": f"dep:{dep}", "ok": found,
                      "detail": "已安装" if found else
                                "未安装（训练须在服务器 .venv 中进行）"})

    # 4) 输出目录可创建
    parent = output_dir
    while parent and not os.path.isdir(parent):
        parent = os.path.dirname(parent)
    writable = bool(parent) and os.access(parent, os.W_OK)
    items.append({"name": "output_dir", "ok": writable,
                  "detail": f"{output_dir}（上级目录可写）" if writable else
                            f"{output_dir} 不可写"})

    return {"ok": all(it["ok"] for it in items), "items": items}


def run_training(method, train_file, eval_file, output_dir, beta, max_steps):
    """执行训练。重依赖（torch/unsloth/trl）只在此处导入，保证 --check 与单测
    在无训练依赖的机器上也能 import 本模块。"""
    cfg = method_config(method)

    # ---------- 环境变量（沿用 llmTuning 已验证配置） ----------
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")      # 纯本地缓存加载
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ["ACCELERATE_MIXED_PRECISION"] = "bf16"  # 避免 Half/BFloat16 冲突

    # ---------- 兼容性修复（同 llmTuning grpo 脚本的环境坑） ----------
    # transformers 5.x 的 _is_package_available() 返回 (bool, version) 元组，
    # trl 0.24.0 按 bool 使用 -> 误判 mergekit 可用而 import 崩溃，这里修正回 bool。
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)
    import trl.import_utils as _tri

    for _name in list(vars(_tri)):
        if _name.endswith("_available"):
            _v = getattr(_tri, _name)
            if isinstance(_v, tuple):
                setattr(_tri, _name, bool(_v[0]))
    # vllm 0.9.2 与 transformers 5.5.0 冲突，显式标记不可用（DPO/IPO 不用 vLLM）
    _tri._vllm_available = False
    _tri._vllm_ascend_available = False

    import torch
    from datasets import load_dataset
    from unsloth import FastLanguageModel
    from trl import DPOTrainer, DPOConfig

    print(f">>> 方法: {cfg['label']} (loss_type={cfg['loss_type']}), 模型: {MODEL_ID}, "
          f"LoRA r={LORA_R}, batch={BATCH_SIZE}x{GRAD_ACCUM}, epochs={NUM_EPOCHS}, "
          f"lr={LR}, beta={beta}, max_len={MAX_SEQ_LENGTH}, 输出: {output_dir}, "
          f"max_steps={max_steps}", flush=True)

    # ---------- 1. bf16 加载模型 + LoRA ----------
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_ID,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=torch.bfloat16,
        load_in_4bit=False,
        use_exact_model_name=True,   # 不映射到 unsloth 预量化变体
        local_files_only=True,       # 纯本地加载，不联网
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        lora_alpha=LORA_R,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )

    # ---------- 2. 加载偏好对数据 ----------
    raw = load_dataset("json", data_files={"train": train_file, "test": eval_file})
    # 只保留 DPO 需要的三列（source/layer/family 等元数据列会干扰 collator）。
    # trl 0.24 的 apply_chat_template 要求 chosen/rejected 也是 messages 列表，
    # 裸字符串会导致 TypeError / 空 prompt（Arrow schema 推断成 list<null> 崩溃）。
    raw = raw.map(
        lambda x: {
            "prompt": x["prompt"],
            "chosen": [{"role": "assistant", "content": x["chosen"]}],
            "rejected": [{"role": "assistant", "content": x["rejected"]}],
        },
        remove_columns=raw["train"].column_names,
        desc="selecting preference columns",
    )
    print(f">>> 训练样本: {len(raw['train'])}, 评估样本: {len(raw['test'])}", flush=True)

    # ---------- 3. 训练 ----------
    dpo_args = DPOConfig(
        output_dir=output_dir,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_ratio=0.1,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LR,
        beta=beta,
        loss_type=cfg["loss_type"],
        max_length=MAX_SEQ_LENGTH,
        max_prompt_length=MAX_PROMPT_LENGTH,
        max_completion_length=MAX_COMPLETION_LENGTH,
        fp16=False,
        bf16=True,
        logging_steps=5,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=50,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
        optim="adamw_8bit",
        seed=42,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_steps=max_steps if max_steps is not None else -1,
        remove_unused_columns=False,   # 数据集已手动选列
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=None,   # PEFT 模式：参考模型 = 关闭 adapter 的同一模型，省显存
        args=dpo_args,
        train_dataset=raw["train"],
        eval_dataset=raw["test"],
        processing_class=tokenizer,
    )

    print(f">>> 开始 {cfg['label']} 训练 ...", flush=True)
    trainer.train()

    # ---------- 4. 最终评估 + 汇总指标 ----------
    print(">>> 计算验证集最终指标 ...", flush=True)
    eval_result = trainer.evaluate()

    logs = trainer.state.log_history
    train_runtime = next(
        (e.get("train_runtime") for e in logs if "train_runtime" in e), None
    )

    def curve(key, ndigits=4):
        return [round(e[key], ndigits) for e in logs if key in e]

    metrics = {
        "model": MODEL_ID,
        "method": cfg["label"],
        "precision": "bf16 (16-bit)",
        "lora_r": LORA_R,
        "beta": beta,
        "loss_type": cfg["loss_type"],
        "learning_rate": LR,
        "num_train_epochs": NUM_EPOCHS,
        "train_samples": len(raw["train"]),
        "eval_samples": len(raw["test"]),
        "max_seq_length": MAX_SEQ_LENGTH,
        "train_runtime_sec": round(train_runtime, 1) if train_runtime else None,
        "global_step": trainer.state.global_step,
        "final_eval": {k: round(v, 4) for k, v in eval_result.items()
                       if isinstance(v, float)},
        "curves": {
            "train_loss": curve("loss"),
            "train_rewards_chosen": curve("rewards/chosen"),
            "train_rewards_rejected": curve("rewards/rejected"),
            "train_rewards_accuracies": curve("rewards/accuracies"),
            "train_rewards_margins": curve("rewards/margins"),
            "eval_loss": curve("eval_loss"),
            "eval_rewards_accuracies": curve("eval_rewards/accuracies"),
            "eval_rewards_margins": curve("eval_rewards/margins"),
        },
        "log_history": [
            {k: (round(v, 4) if isinstance(v, float) else v) for k, v in e.items()}
            for e in logs
        ],
    }

    os.makedirs(output_dir, exist_ok=True)
    metrics_path = os.path.join(output_dir, "metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    # ---------- 5. 保存 LoRA ----------
    model.save_pretrained(os.path.join(output_dir, "lora"))
    tokenizer.save_pretrained(os.path.join(output_dir, "lora"))

    # ---------- 6. 校验 chat_template：保留非思考模式的空 <think> 块 ----------
    # Qwen3 原生模板在 enable_thinking=false 时会预填空 <think> 块，
    # 该空块是训练/推理分布的一部分，必须保留，否则推理会退化。
    template_path = os.path.join(output_dir, "lora", "chat_template.jinja")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
        if "enable_thinking is defined and enable_thinking is false" in template:
            print(">>> chat_template 校验通过：保留 enable_thinking 空 <think> 块")
        else:
            print(">>> 警告：chat_template 缺少 enable_thinking 空 <think> 块，"
                  "推理可能出现退化")

    # ---------- 7. 抽样生成做定性检查 ----------
    samples = []
    for ex in [raw["test"][0], raw["test"][1], raw["test"][2]]:
        prompt_ids = tokenizer.apply_chat_template(
            ex["prompt"], tokenize=True, add_generation_prompt=True,
            return_tensors="pt",
        )
        if hasattr(prompt_ids, "input_ids"):
            prompt_ids = prompt_ids.input_ids
        prompt_ids = prompt_ids.to(model.device)
        with torch.inference_mode():
            out_ids = model.generate(
                prompt_ids, max_new_tokens=512, use_cache=True, do_sample=False,
            )
        reply = tokenizer.decode(
            out_ids[0][prompt_ids.shape[1]:], skip_special_tokens=True
        )
        samples.append({
            "prompt": ex["prompt"][-1]["content"],
            "chosen": ex["chosen"][0]["content"],
            "rejected": ex["rejected"][0]["content"],
            "model_output": reply,
        })
    metrics["sample_generations"] = samples
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(">>> 最终指标:")
    print(json.dumps(
        {k: v for k, v in metrics.items()
         if k not in ("log_history", "curves", "sample_generations")},
        ensure_ascii=False, indent=2,
    ))
    print(f">>> 指标已写入 {metrics_path}")
    print(f">>> LoRA 已保存到 {os.path.join(output_dir, 'lora')}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DPO/IPO 偏好对齐训练（Qwen3-8B + LoRA），详见模块 docstring 环境说明")
    parser.add_argument("--method", choices=sorted(METHODS), default="ipo",
                        help="训练方法：dpo（sigmoid 损失）或 ipo（默认 ipo）")
    parser.add_argument("--train-file", default=DEFAULT_TRAIN_FILE,
                        help="训练集 JSONL 路径（默认 data/dpo/dpo_pairs_tools.jsonl）")
    parser.add_argument("--eval-file", default=DEFAULT_EVAL_FILE,
                        help="评估集 JSONL 路径（默认 data/dpo/dpo_eval_pairs_tools.jsonl）")
    parser.add_argument("--output-dir", default=None,
                        help="输出目录（默认 outputs/alignment-8B-{method}）")
    parser.add_argument("--beta", type=float, default=BETA,
                        help=f"DPO/IPO 正则系数（默认 {BETA}）")
    parser.add_argument("--max-steps", type=int, default=None,
                        help="限制训练步数（冒烟测试用；也可用环境变量 DPO_MAX_STEPS）")
    parser.add_argument("--check", action="store_true",
                        help="只做环境自检（数据/依赖/路径），不加载模型不训练")
    args = parser.parse_args(argv)

    cfg = method_config(args.method)
    output_dir = args.output_dir or cfg["output_dir"]
    max_steps = args.max_steps
    if max_steps is None and "DPO_MAX_STEPS" in os.environ:
        max_steps = int(os.environ["DPO_MAX_STEPS"])

    if args.check:
        report = check_environment(args.train_file, args.eval_file, output_dir)
        for it in report["items"]:
            print(f"[{'PASS' if it['ok'] else 'FAIL'}] {it['name']}: {it['detail']}")
        print(">>> 自检结果:", "通过，可开始训练" if report["ok"] else
              "未通过——FAIL 项需在训练服务器上解决（见模块 docstring 环境说明）")
        return 0 if report["ok"] else 1

    run_training(args.method, args.train_file, args.eval_file, output_dir,
                 args.beta, max_steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
