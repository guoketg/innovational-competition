# -*- coding: utf-8 -*-
"""意图判定器四方对比评测：规则版 / NLP（TF-IDF+LR） / LLM / Jev。

回答的问题：同样 100 条标注用例，四种判定器谁的意图判断更准、谁更快。

  * ``rule`` —— ``services.request_classifier.judge_intent``（现行零依赖兜底）
  * ``nlp``  —— TF-IDF（char_wb 1-3）+ 逻辑回归，5 折分层交叉验证
  * ``llm``  —— OpenAI 兼容 chat/completions（默认 DeepSeek），JSON 输出
  * ``jev``  —— ``services.jev_judge.JevIntentJudge``（OpenRouter Decisions API）

诚实时延口径：
  * rule / nlp 为**本地进程内**调用；
  * llm / jev 为**云端 API**（含网络往返）。
  两类不可直接同轴比较，报告里分列 ``latency_local`` / ``latency_remote``。

密钥一律走环境变量，不进代码：
  * ``OPENROUTER_API_KEY`` → Jev 臂
  * ``EVAL_API_KEY`` / ``EVAL_BASE_URL`` / ``EVAL_MODEL`` → LLM 臂
  缺密钥时该臂 ``status=skipped_no_key``，不中断其余臂。

用法（Windows PowerShell，项目 venv）：
  & "venv\\Scripts\\python.exe" backend/scripts/evaluate_intent_judges.py --judges rule,nlp
  & "venv\\Scripts\\python.exe" backend/scripts/evaluate_intent_judges.py --judges all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from services.jev_judge import JevIntentJudge, resolve_api_key  # noqa: E402
from services.request_classifier import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    judge_intent,
)

INTENTS = ("learning", "tool_use", "disguised")
KINDS = ("modify", "hint", "none")
DEFAULT_CASES = BACKEND / "data" / "eval" / "intent_judges_cases.jsonl"
DEFAULT_REPORT = BACKEND / "data" / "eval" / "intent_judges_report.json"


# ────────────────────────────── 数据与指标 ──────────────────────────────


def load_cases(path: Path) -> list[dict]:
    cases = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row["expected_intent"] not in INTENTS:
                raise ValueError(f"{row['case_id']} expected_intent 非法: {row['expected_intent']}")
            if row["expected_kind"] not in KINDS:
                raise ValueError(f"{row['case_id']} expected_kind 非法: {row['expected_kind']}")
            cases.append(row)
    return cases


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def _latency_stats(samples: list[float]) -> dict:
    if not samples:
        return {}
    ordered = sorted(samples)

    def pct(q: float) -> float:
        idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return round(ordered[idx], 1)

    return {
        "n": len(ordered),
        "mean": round(sum(ordered) / len(ordered), 1),
        "p50": pct(0.50),
        "p95": pct(0.95),
    }


def compute_metrics(records: list[dict], *, latency_scope: str) -> dict:
    """records 里每条含 expected_*/pred_*/hardness/latency_ms/fallback/ok。"""
    ok = [r for r in records if r.get("ok", True)]
    n = len(ok)
    intent_hits = [r for r in ok if r["pred_intent"] == r["expected_intent"]]
    kind_hits = [r for r in ok if r["pred_kind"] == r["expected_kind"]]

    by_intent = {}
    for label in INTENTS:
        subset = [r for r in ok if r["expected_intent"] == label]
        by_intent[label] = _rate(
            sum(1 for r in subset if r["pred_intent"] == label), len(subset)
        )

    by_kind = {}
    for label in KINDS:
        subset = [r for r in ok if r["expected_kind"] == label]
        by_kind[label] = _rate(
            sum(1 for r in subset if r["pred_kind"] == label), len(subset)
        )

    hardness = {}
    for level in ("easy", "medium", "hard"):
        subset = [r for r in ok if r.get("hardness") == level]
        if subset:
            hardness[level] = {
                "n": len(subset),
                "intent_accuracy": _rate(
                    sum(1 for r in subset if r["pred_intent"] == r["expected_intent"]),
                    len(subset),
                ),
                "kind_accuracy": _rate(
                    sum(1 for r in subset if r["pred_kind"] == r["expected_kind"]),
                    len(subset),
                ),
            }

    misses = [
        {
            "case_id": r["case_id"],
            "request": r["request"][:60],
            "expected": f"{r['expected_intent']}/{r['expected_kind']}",
            "predicted": f"{r['pred_intent']}/{r['pred_kind']}",
            "hardness": r.get("hardness"),
        }
        for r in ok
        if r["pred_intent"] != r["expected_intent"] or r["pred_kind"] != r["expected_kind"]
    ]

    return {
        "n": n,
        "coverage": _rate(n, len(records)) if records else None,
        "intent_accuracy": _rate(len(intent_hits), n),
        "kind_accuracy": _rate(len(kind_hits), n),
        "intent_balanced_accuracy": (
            round(sum(by_intent.values()) / len(INTENTS), 4)
            if all(v is not None for v in by_intent.values())
            else None
        ),
        "kind_balanced_accuracy": (
            round(sum(by_kind.values()) / len(KINDS), 4)
            if all(v is not None for v in by_kind.values())
            else None
        ),
        "intent_recall_by_class": by_intent,
        "kind_recall_by_class": by_kind,
        "accuracy_by_hardness": hardness,
        "fallback_rate": _rate(sum(1 for r in ok if r.get("fallback")), n),
        "latency_scope": latency_scope,
        "latency_ms": _latency_stats([r["latency_ms"] for r in ok if r.get("latency_ms") is not None]),
        "miss_count": len(misses),
        "misses": misses[:12],
    }


# ────────────────────────────── 各判定器臂 ──────────────────────────────


def run_rule(cases: list[dict]) -> dict:
    records = []
    for case in cases:
        started = time.perf_counter()
        judgment = judge_intent(case["request"])
        latency_ms = (time.perf_counter() - started) * 1000.0
        records.append(
            {
                "case_id": case["case_id"],
                "request": case["request"],
                "hardness": case["hardness"],
                "expected_intent": case["expected_intent"],
                "expected_kind": case["expected_kind"],
                "pred_intent": judgment.choice,
                "pred_kind": judgment.kind,
                "fallback": judgment.fallback,
                "latency_ms": latency_ms,
            }
        )
    metrics = compute_metrics(records, latency_scope="local")
    metrics.update(
        {
            "status": "ok",
            "kind": "rule",
            "description": "规则版 judge_intent（零依赖兜底，纯正则 + 阈值启发式）",
            "threshold": CONFIDENCE_THRESHOLD,
            "cost_usd": 0.0,
        }
    )
    return metrics


def run_nlp(cases: list[dict], *, folds: int = 5) -> dict:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold
        from sklearn.pipeline import Pipeline
    except ImportError as exc:  # pragma: no cover
        return {"kind": "nlp", "status": f"skipped_missing_dependency:{exc}", "n": 0}

    texts = [c["request"] for c in cases]
    y_intent = [c["expected_intent"] for c in cases]
    y_kind = [c["expected_kind"] for c in cases]

    def make_model() -> Pipeline:
        return Pipeline(
            [
                ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3), min_df=1)),
                ("clf", LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")),
            ]
        )

    def cross_val(labels: list[str]) -> list[str]:
        preds = [""] * len(texts)
        splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
        for train_idx, test_idx in splitter.split(texts, labels):
            model = make_model()
            model.fit([texts[i] for i in train_idx], [labels[i] for i in train_idx])
            fold_preds = model.predict([texts[i] for i in test_idx])
            for idx, pred in zip(test_idx, fold_preds):
                preds[idx] = str(pred)
        return preds

    intent_preds = cross_val(y_intent)
    kind_preds = cross_val(y_kind)

    # 时延：全量训练后逐条预测，取单条均值（本地进程内）
    intent_model = make_model().fit(texts, y_intent)
    kind_model = make_model().fit(texts, y_kind)
    latencies = []
    for text in texts:
        started = time.perf_counter()
        intent_model.predict([text])
        kind_model.predict([text])
        latencies.append((time.perf_counter() - started) * 1000.0)

    records = [
        {
            "case_id": case["case_id"],
            "request": case["request"],
            "hardness": case["hardness"],
            "expected_intent": case["expected_intent"],
            "expected_kind": case["expected_kind"],
            "pred_intent": intent_preds[i],
            "pred_kind": kind_preds[i],
            "fallback": False,
            "latency_ms": latencies[i],
        }
        for i, case in enumerate(cases)
    ]
    metrics = compute_metrics(records, latency_scope="local")
    metrics.update(
        {
            "status": "ok",
            "kind": "nlp",
            "description": f"TF-IDF(char_wb 1-3) + 逻辑回归，{folds} 折分层交叉验证",
            "evaluation_mode": "out_of_fold_cv",
            "folds": folds,
            "cost_usd": 0.0,
            "note": "准确率为交叉验证折外预测；时延为全量训练后单条推理（不含训练时间）",
        }
    )
    return metrics


def _build_llm_prompt(case: dict) -> tuple[str, str]:
    from services.jev_judge import _QUESTIONS  # 复用 Jev 的判据文本，保证公平对比

    ctx = _QUESTIONS["context"]["criteria"]
    req = _QUESTIONS["request_kind"]["criteria"]
    system = "你是学习平台的意图判定器。只输出一个 JSON 对象，不要任何解释或多余文本。"
    user = (
        f"【学生本回合消息】\n{case['request']}\n\n"
        "请判断两件事：\n"
        "1) intent —— 消息属于哪种上下文（三选一）：\n"
        f"   learning：{ctx['learning']}\n"
        f"   tool_use：{ctx['tool_use']}\n"
        f"   disguised：{ctx['disguised']}\n"
        "2) kind —— 学生本回合是否明确提出代改/给结果的请求（三选一）：\n"
        f"   modify：{req['modify']}\n"
        f"   hint：{req['hint']}\n"
        f"   none：{req['none']}\n\n"
        '输出格式：{"intent": "learning|tool_use|disguised", "kind": "modify|hint|none"}'
    )
    return system, user


def _post_json(url: str, payload: dict, api_key: str, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_llm_json(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("```")[1] if "```" in body[3:] else body
        body = body.split("\n", 1)[-1] if body.lstrip().startswith(("json", "JSON")) else body
        body = body.strip("`").strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no json object")
    data = json.loads(body[start : end + 1])
    intent = str(data.get("intent", "")).strip()
    kind = str(data.get("kind", "")).strip()
    if intent not in INTENTS or kind not in KINDS:
        raise ValueError(f"invalid labels: {data}")
    return {"intent": intent, "kind": kind}


def run_llm(cases: list[dict], *, base_url: str, model: str, api_key: str) -> dict:
    if not api_key:
        return {
            "kind": "llm",
            "status": "skipped_no_key",
            "n": 0,
            "note": "未设置 EVAL_API_KEY，跳过 LLM 臂",
        }
    endpoint = base_url.rstrip("/") + "/chat/completions"
    records, errors, tokens = [], [], {"input": 0, "output": 0}
    for case in cases:
        system, user = _build_llm_prompt(case)
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        started = time.perf_counter()
        try:
            raw = _post_json(endpoint, payload, api_key)
            latency_ms = (time.perf_counter() - started) * 1000.0
            usage = raw.get("usage") or {}
            tokens["input"] += int(usage.get("prompt_tokens", 0))
            tokens["output"] += int(usage.get("completion_tokens", 0))
            parsed = _parse_llm_json(raw["choices"][0]["message"]["content"])
            records.append(
                {
                    "case_id": case["case_id"],
                    "request": case["request"],
                    "hardness": case["hardness"],
                    "expected_intent": case["expected_intent"],
                    "expected_kind": case["expected_kind"],
                    "pred_intent": parsed["intent"],
                    "pred_kind": parsed["kind"],
                    "fallback": False,
                    "latency_ms": latency_ms,
                    "ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001 —— 单条失败不影响整臂
            latency_ms = (time.perf_counter() - started) * 1000.0
            errors.append(
                {"case_id": case["case_id"], "error": f"{type(exc).__name__}: {exc}"[:160]}
            )
            records.append(
                {
                    "case_id": case["case_id"],
                    "request": case["request"],
                    "hardness": case["hardness"],
                    "expected_intent": case["expected_intent"],
                    "expected_kind": case["expected_kind"],
                    "pred_intent": "",
                    "pred_kind": "",
                    "fallback": True,
                    "latency_ms": latency_ms,
                    "ok": False,
                }
            )

    metrics = compute_metrics(records, latency_scope="remote")
    metrics.update(
        {
            "status": "ok" if not errors else ("partial" if any(r["ok"] for r in records) else "failed"),
            "kind": "llm",
            "description": f"OpenAI 兼容 chat/completions（{model}），JSON 输出，temperature=0",
            "model": model,
            "base_url": base_url,
            "usage_tokens": tokens,
            "cost_usd": None,
            "errors": errors[:5],
            "error_count": len(errors),
        }
    )
    return metrics


def run_jev(cases: list[dict]) -> dict:
    api_key = resolve_api_key(None)
    if not api_key:
        return {
            "kind": "jev",
            "status": "skipped_no_key",
            "n": 0,
            "note": "未设置 OPENROUTER_API_KEY，跳过 Jev 臂",
        }
    judge = JevIntentJudge(api_key=api_key, use_cache=False)
    records, api_failures, routed_hits = [], [], 0
    for case in cases:
        started = time.perf_counter()
        judgment = judge.judge(case["request"])
        latency_ms = (time.perf_counter() - started) * 1000.0
        api_failed = any(str(e).startswith("jev_fallback:") for e in judgment.evidence)
        if api_failed:
            api_failures.append({"case_id": case["case_id"], "evidence": list(judgment.evidence)})
        # 运行时的实际路由：低置信回落时按学习场景处理（不采信工具性声明）
        effective = "learning" if judgment.fallback else judgment.choice
        if effective == case["expected_intent"]:
            routed_hits += 1
        records.append(
            {
                "case_id": case["case_id"],
                "request": case["request"],
                "hardness": case["hardness"],
                "expected_intent": case["expected_intent"],
                "expected_kind": case["expected_kind"],
                "pred_intent": judgment.choice,
                "pred_kind": judgment.kind,
                "fallback": judgment.fallback,
                "latency_ms": latency_ms,
            }
        )
    metrics = compute_metrics(records, latency_scope="remote")
    metrics.update(
        {
            "status": "ok" if not api_failures else "partial",
            "kind": "jev",
            "description": f"Jev（{judge.model}，OpenRouter Decisions API，三原语原生输出）",
            "model": judge.model,
            "threshold": judge.threshold,
            "usage": judge.total_usage,
            "cost_usd": round(judge.total_usage.get("cost", 0.0), 6),
            "routed_intent_accuracy": _rate(routed_hits, len(records)),
            "routed_note": "低置信回落按学习场景路由后的意图准确率（= 运行时实际行为）",
            "api_fallback_count": len(api_failures),
            "api_fallback_cases": [e["case_id"] for e in api_failures][:10],
        }
    )
    return metrics


# ────────────────────────────── 主流程 ──────────────────────────────


def build_summary(report: dict) -> dict:
    rows = []
    for key in ("rule", "nlp", "llm", "jev"):
        arm = report["judges"].get(key)
        if not arm or arm.get("status", "").startswith("skipped"):
            continue
        latency = arm.get("latency_ms") or {}
        rows.append(
            {
                "judge": key,
                "intent_accuracy": arm.get("intent_accuracy"),
                "kind_accuracy": arm.get("kind_accuracy"),
                "latency_p50_ms": latency.get("p50"),
                "latency_p95_ms": latency.get("p95"),
                "latency_scope": arm.get("latency_scope"),
                "fallback_rate": arm.get("fallback_rate"),
                "cost_usd": arm.get("cost_usd"),
                "coverage": arm.get("coverage"),
            }
        )
    return {"rows": rows, "scatter_hint": "x=latency_p50_ms, y=intent_accuracy，按 latency_scope 分组"}


def main() -> int:
    parser = argparse.ArgumentParser(description="意图判定器四方对比评测")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--judges", default="rule,nlp", help="rule,nlp,llm,jev 或 all")
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", "https://api.deepseek.com/v1"))
    parser.add_argument("--model", default=os.getenv("EVAL_MODEL", "deepseek-chat"))
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", ""))
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    selected = {"rule", "nlp", "llm", "jev"} if args.judges == "all" else {
        item.strip() for item in args.judges.split(",") if item.strip()
    }

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metric_basis": "real_model",
        "cases_file": str(Path(args.cases)),
        "n_cases": len(cases),
        "distribution": {
            "intent": dict(Counter(c["expected_intent"] for c in cases)),
            "kind": dict(Counter(c["expected_kind"] for c in cases)),
            "hardness": dict(Counter(c["hardness"] for c in cases)),
        },
        "judges": {},
        "notes": [
            "rule / nlp 为本地进程内时延；llm / jev 为云端 API 含网络往返，横比时延须分组说明",
            "nlp 准确率为 5 折分层交叉验证折外预测，不是训练集自评",
            "标注口径按「请求轴」：学生明确开口要改=modify，问改法=hint，无请求=none；伪装工具声明=disguised",
        ],
    }

    for key, runner in (
        ("rule", lambda: run_rule(cases)),
        ("nlp", lambda: run_nlp(cases, folds=args.cv_folds)),
        ("llm", lambda: run_llm(cases, base_url=args.base_url, model=args.model, api_key=args.api_key)),
        ("jev", lambda: run_jev(cases)),
    ):
        if key not in selected:
            continue
        print(f"[evaluate] 运行 {key} 臂 ...", flush=True)
        started = time.perf_counter()
        report["judges"][key] = runner()
        elapsed = time.perf_counter() - started
        arm = report["judges"][key]
        print(
            f"[evaluate] {key}: status={arm.get('status')} "
            f"intent={arm.get('intent_accuracy')} kind={arm.get('kind_accuracy')} "
            f"耗时={elapsed:.1f}s",
            flush=True,
        )

    report["summary"] = build_summary(report)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[evaluate] 报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
