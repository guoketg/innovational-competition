"""help-seeking 行为半自动编码脚本（优化清单第 2 项）。

对 qa_history 中的学生提问做规则版自动编码（ICER 2024 help-seeking 赛道口径），
输出 CSV 供人工校准：自动列先填、人工列留空，回填后 --calibrate 算一致率与
Cohen's kappa。规则编码只是初标，最终以人工标注为准。

编码体系（help-seeking 分类）:
  direct_answer  封闭式求助：直接要答案/成品代码
  orientation    定位求助：问方向、步骤、从哪入手
  concept        概念求助：问"是什么/为什么/原理"
  debug          调试求助：贴代码/报错问哪里错
  verification   验证求助：确认自己的思路/代码对不对
  meta           策略求助：问怎么学/怎么练
  other          其他/无法归类（低置信，优先人工复核）

用法:
  python scripts/code_help_seeking.py                     # 编码全部 qa_history → CSV
  python scripts/code_help_seeking.py --limit 100         # 只编码前 100 条
  python scripts/code_help_seeking.py --summary           # 只看分布
  python scripts/code_help_seeking.py --calibrate out.csv # 人工回填后算一致率+kappa
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND / "data" / "learning_platform.db"
DEFAULT_OUT = BACKEND / "data" / "eval" / "help_seeking_codes.csv"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CODES = ["direct_answer", "orientation", "concept", "debug", "verification", "meta", "other"]
CODE_LABELS = {
    "direct_answer": "封闭式求助（要答案/成品代码）",
    "orientation": "定位求助（问方向/步骤）",
    "concept": "概念求助（是什么/为什么）",
    "debug": "调试求助（贴代码/报错）",
    "verification": "验证求助（确认思路）",
    "meta": "策略求助（怎么学/练）",
    "other": "其他/无法归类",
}

# 依次匹配，先特后泛；命中即停。
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("direct_answer", re.compile(
        r"(直接(把|给|发|来)|别问|不问思路|完整代码|全部代码|答案(是|吧|发)|帮我(写|做|改|完成)|"
        r"抄一下|给我(一份|个)?(现成|完整)|代写|替我写|一次性给)")),
    ("verification", re.compile(
        r"(这样(写|做|想|理解|解)?(对|行|可)(以)?(吗|么|吧)|我(的)?(思路|写法|理解|答案)(对|行|可)|"
        r"是(不是|吗|不是这样)|帮我看看(对|行|可)|确认(一下)?(我|这)|对(不)?对(吗|么|吧))")),
    ("debug", re.compile(
        r"(报错|错误|error|exception|traceback|运行(不|没)(过|通)|过不了|wa|段错误|segfault|"
        r"为什么(会)?(错|失败)|哪里(错|不对)|bug|测试(不过|失败)|死循环|输出不对)")),
    ("concept", re.compile(
        r"(什么是|是什么|为什么|原理|区别|作用|含义|什么意思|怎么理解|概念|"
        r"时间(复杂度|空间)|大O|算法(思想|思路|原理)|能(不能)?(解释|讲)(一下|讲))")),
    ("orientation", re.compile(
        r"(怎么(办|做|写|开始|入手)|从哪|思路|步骤|方法|如何(实现|完成|做)|"
        r"该(怎么|如何)|提示我|引导我|教我|不会写|卡(在|住)|下一(步|个))")),
    ("meta", re.compile(
        r"(怎么(学|练|复习)|学习(方法|计划|建议)|如何(提高|入门)|推荐(资料|书|题)|"
        r"练习(建议|方法)|备考|学习路线)")),
]
_CODE_FENCE = re.compile(r"```")


def classify(question: str) -> tuple[str, str]:
    """规则编码 → (code, confidence)。命中模式取首个，均未命中判 other/low。"""
    text = question or ""
    for code, pattern in _PATTERNS:
        if pattern.search(text):
            # 调试类要求贴了代码/报错，提高置信；概念+代码围栏降置信（可能在问代码含义）
            conf = "high"
            if code in ("concept", "orientation") and _CODE_FENCE.search(text):
                conf = "medium"
            return code, conf
    if _CODE_FENCE.search(text):
        return "debug", "medium"   # 贴了代码但没命中关键词，疑似调试
    return "other", "low"


def load_rows(db_path: Path, limit: int) -> list[sqlite3.Row]:
    if not db_path.exists():
        print(f"数据库不存在: {db_path}", file=sys.stderr)
        sys.exit(2)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sql = ("SELECT id, user_id, question, knowledge_tags, created_at "
           "FROM qa_history ORDER BY id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    try:
        rows = [dict(r) for r in conn.execute(sql)]
    except sqlite3.OperationalError as err:
        # 本地库尚未由后端初始化时（表结构在 docker 启动/首次建库时创建）
        print(f"读取 qa_history 失败: {err}（请先启动后端或 docker compose up 生成表结构）",
              file=sys.stderr)
        conn.close()
        sys.exit(2)
    conn.close()
    return rows


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "qa_id", "user_id", "created_at", "knowledge_tags", "question",
            "auto_code", "auto_conf", "auto_label",
            "human_code", "human_note",  # 人工回填列
        ])
        for r in rows:
            code, conf = classify(r["question"])
            writer.writerow([
                r["id"], r["user_id"], r["created_at"], r.get("knowledge_tags", ""),
                (r["question"] or "").replace("\n", " ")[:500],
                code, conf, CODE_LABELS[code],
                "", "",
            ])


def print_summary(rows: list[dict]) -> None:
    counter = Counter(classify(r["question"])[0] for r in rows)
    total = sum(counter.values())
    print(f"共 {total} 条")
    for code in CODES:
        n = counter.get(code, 0)
        print(f"  {code:<15} {n:>5}  {n / total * 100 if total else 0:5.1f}%  {CODE_LABELS[code]}")


def calibrate(csv_path: Path) -> int:
    """读回填后的 CSV，输出人工 vs 自动一致率与 Cohen's kappa。"""
    with csv_path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    pairs = [
        (r["auto_code"].strip(), r["human_code"].strip())
        for r in rows if r.get("human_code", "").strip()
    ]
    if not pairs:
        print("CSV 中 human_code 尚无回填，无法校准", file=sys.stderr)
        return 2
    n = len(pairs)
    agree = sum(1 for a, h in pairs if a == h)
    po = agree / n
    auto_dist = Counter(a for a, _ in pairs)
    hum_dist = Counter(h for _, h in pairs)
    pe = sum((auto_dist[c] / n) * (hum_dist[c] / n) for c in CODES)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    print(f"已标注 {n} 条 | 一致 {agree} 条")
    print(f"一致率 = {po:.3f} | Cohen's kappa = {kappa:.3f}")
    mismatches = Counter((a, h) for a, h in pairs if a != h)
    if mismatches:
        print("不一致对（auto → human）:")
        for (a, h), cnt in mismatches.most_common():
            print(f"  {a} → {h}: {cnt}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="help-seeking 行为半自动编码 + 人工校准")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--summary", action="store_true", help="只打印分布，不写 CSV")
    parser.add_argument("--calibrate", metavar="CSV", help="对回填后的 CSV 计算一致率与 kappa")
    args = parser.parse_args()

    if args.calibrate:
        return calibrate(Path(args.calibrate))

    rows = load_rows(Path(args.db), args.limit)
    if not rows:
        print("qa_history 无数据", file=sys.stderr)
        return 2
    if args.summary:
        print_summary(rows)
        return 0
    write_csv(rows, Path(args.out))
    print_summary(rows)
    print(f"编码 CSV: {args.out}（回填 human_code/human_note 后用 --calibrate 校准）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
