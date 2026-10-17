"""知识图谱测评服务。

从四个维度给课程级知识图谱打分，输出可直接展示给用户、也可写进答辩材料的报告：

1. 结构健康：孤立点、悬挂边（两端不在名单内）、自环、重复边、先修环；
2. 边质量：以独立金标准边集为参照，计算 strict / judged 精确率、召回率、F1
   与双人标注 Cohen's kappa，并统计 AI 边重复、反向、人工审核结果和多次生成稳定性；
3. 路径影响：分别模拟基础薄弱 / 有一定基础 / 较为熟练三类学生，
   对比「不用图谱」「只用专家骨架」「完整图谱」三种编排结果，
   统计被前置拦下的项目、补先修任务、顺序变化与 Kendall τ；
4. 证据覆盖：每个知识点是否有实训项目、快速测评题、教程与 AI 描述。

设计原则：
- 所有指标都能从现有数据算出来，不编造「模型准确率」；
- 没有 AI 图谱时如实说明「AI 边质量不可评估」，而不是给满分；
- 分数只是汇总，明细里每一项都写清楚依据，方便老师追问时逐条解释。
"""
import glob
import json
import os
from collections import Counter
from datetime import datetime

from services import agent_course
from services import knowledge_graph_service as kg


WORKSPACE_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_CYCLE_SAMPLES = 5
GOLD_PATH = os.path.join(WORKSPACE_BACKEND, "data", "eval", "knowledge_graph_gold.json")
SNAPSHOT_DIR = os.path.join(WORKSPACE_BACKEND, "data", "eval", "kg_snapshots")


# ===== 基础工具 =====

def _node_index(graph: dict) -> dict:
    return {
        str(node.get("tag") or "").strip(): node
        for node in (graph or {}).get("nodes") or []
        if node.get("tag")
    }


def _expert_pairs(expert_prereq: dict, node_ids: set) -> set:
    """把专家先修表展开成 (前置, 后继) 集合，只保留图谱里存在的节点。"""
    pairs = set()
    for target, parents in (expert_prereq or {}).items():
        if target not in node_ids:
            continue
        for source in parents or []:
            if source in node_ids and source != target:
                pairs.add((source, target))
    return pairs


def _f1(precision: float, recall: float):
    if precision is None or recall is None:
        return None
    if precision + recall <= 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 3)


def _cohen_kappa(double_labels: list):
    """双人标注一致性。输入 [(pair, a, b)]，返回 (kappa, 原始一致率)。

    只有两位标注者都填过的边才参与计算；没有任何双标边时返回 (None, None)。
    """
    total = len(double_labels)
    if not total:
        return None, None
    agree = sum(1 for _, a, b in double_labels if int(bool(a)) == int(bool(b)))
    rate_a = sum(1 for _, a, _ in double_labels if bool(a)) / total
    rate_b = sum(1 for _, _, b in double_labels if bool(b)) / total
    expected = rate_a * rate_b + (1 - rate_a) * (1 - rate_b)
    observed = agree / total
    if expected >= 1:
        return 1.0, round(observed, 3)
    return round((observed - expected) / (1 - expected), 3), round(observed, 3)


def _load_gold_standard() -> dict:
    """读取独立金标准边集；文件缺失或格式错误时返回不可用状态，不编造指标。"""
    empty = {
        "available": False,
        "version": None,
        "created_at": None,
        "annotators": [],
        "labels": {},
        "positives": set(),
        "negatives": set(),
        "core_positives": set(),
        "extended_positives": set(),
        "double_labels": [],
        "unresolved_disagreements": 0,
        "kappa": None,
        "kappa_status": "missing",
        "agreement": None,
        "status": "unavailable",
        "detail": "未找到独立金标准边集，边质量只能使用代理指标。",
    }
    try:
        with open(GOLD_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return empty

    labels = {}
    positives, negatives, core, extended = set(), set(), set(), set()
    double_labels = []
    unresolved = 0
    for item in data.get("labels") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        pair = (source, target)
        a = item.get("annotator_a")
        b = item.get("annotator_b")
        adjudicated = item.get("adjudicated")
        if a is not None and b is not None:
            double_labels.append((pair, a, b))
        if adjudicated is not None:
            gold = int(bool(adjudicated))
        elif a is not None and b is not None:
            if int(bool(a)) != int(bool(b)):
                unresolved += 1
                continue
            gold = int(bool(a))
        elif a is not None:
            gold = int(bool(a))
        elif b is not None:
            gold = int(bool(b))
        else:
            continue
        scope = str(item.get("scope") or "core").strip()
        labels[pair] = {"gold": gold, "scope": scope}
        if gold:
            positives.add(pair)
            (extended if scope == "extended" else core).add(pair)
        else:
            negatives.add(pair)

    kappa, agreement = _cohen_kappa(double_labels)
    annotators = data.get("annotators") or []
    second_filled = any(
        str(item.get("id") or "").upper() == "B" and item.get("status") == "filled"
        for item in annotators
        if isinstance(item, dict)
    )
    return {
        "available": bool(labels),
        "version": data.get("version"),
        "created_at": data.get("created_at"),
        "annotators": annotators,
        "labels": labels,
        "positives": positives,
        "negatives": negatives,
        "core_positives": core,
        "extended_positives": extended,
        "double_labels": double_labels,
        "unresolved_disagreements": unresolved,
        "kappa": kappa,
        "kappa_status": "ready" if kappa is not None else "pending_second_annotator",
        "agreement": agreement,
        "status": "double_annotated" if second_filled and kappa is not None else "single_annotator",
        "detail": data.get("disclaimer") or "",
    }


def _stability_report() -> dict:
    """读取多次生成快照，计算两两 Jaccard 相似度；不足 2 次时如实显示未抽检。"""
    files = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "*.json")))
    runs = []
    for path in files[-12:]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        pairs = set()
        for item in data.get("pairs") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                source = str(item[0] or "").strip()
                target = str(item[1] or "").strip()
                if source and target and source != target:
                    pairs.add((source, target))
        if pairs:
            runs.append({
                "file": os.path.basename(path),
                "generated_at": data.get("generated_at"),
                "pairs": pairs,
            })

    if len(runs) < 2:
        return {
            "status": "not_sampled",
            "runs": len(runs),
            "mean_jaccard": None,
            "min_jaccard": None,
            "max_jaccard": None,
            "comparisons": [],
            "snapshot_dir": "backend/data/eval/kg_snapshots",
            "detail": "还没有至少 2 次真实生成快照。配置 LLM Key 后运行 backend/scripts/kg_stability_probe.py，"
                      "再刷新测评即可看到稳定性。",
        }

    comparisons = []
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            left, right = runs[i]["pairs"], runs[j]["pairs"]
            union = left | right
            jaccard = round(len(left & right) / len(union), 3) if union else 1.0
            comparisons.append({
                "run_a": runs[i]["file"],
                "run_b": runs[j]["file"],
                "jaccard": jaccard,
            })
    values = [item["jaccard"] for item in comparisons]
    return {
        "status": "sampled",
        "runs": len(runs),
        "mean_jaccard": round(sum(values) / len(values), 3),
        "min_jaccard": min(values),
        "max_jaccard": max(values),
        "comparisons": comparisons,
        "snapshot_dir": "backend/data/eval/kg_snapshots",
        "detail": f"已抽检 {len(runs)} 次生成，两两 Jaccard 相似度均值 {round(sum(values) / len(values) * 100)}%。",
    }


def _gold_metrics(gold: dict, ai_pairs: set, merged_pairs: set,
                  expert_pairs: set, node_ids: set) -> dict:
    """把 AI 边与独立金标准逐条对照，计算 strict / judged 两套 P/R/F1。"""
    if not gold.get("available"):
        return {
            "available": False,
            "version": gold.get("version"),
            "status": gold.get("status"),
            "status_label": "不可用",
            "labels_total": 0,
            "positive_total": 0,
            "negative_total": 0,
            "core_positive_total": 0,
            "extended_positive_total": 0,
            "novel_positive_total": 0,
            "expert_overlap_positive_total": 0,
            "graph_coverage": None,
            "graph_core_coverage": None,
            "graph_extended_coverage": None,
            "graph_novel_coverage": None,
            "ai_labeled": 0,
            "ai_unlabeled": len(ai_pairs),
            "ai_positive_hits": 0,
            "ai_negative_hits": 0,
            "strict_precision": None,
            "judged_precision": None,
            "ai_recall_core": None,
            "ai_recall_novel": None,
            "strict_f1": None,
            "judged_f1": None,
            "kappa": None,
            "kappa_status": "missing",
            "agreement": None,
            "double_labeled": 0,
            "unresolved_disagreements": 0,
            "annotators": [],
            "detail": gold.get("detail") or "独立金标准不可用。",
        }

    positives = {p for p in gold["positives"] if p[0] in node_ids and p[1] in node_ids}
    negatives = {p for p in gold["negatives"] if p[0] in node_ids and p[1] in node_ids}
    core = {p for p in gold["core_positives"] if p[0] in node_ids and p[1] in node_ids}
    extended = {p for p in gold["extended_positives"] if p[0] in node_ids and p[1] in node_ids}
    novel_positives = positives - expert_pairs
    expert_overlap = positives & expert_pairs

    ai_pos_hits = ai_pairs & positives
    ai_neg_hits = ai_pairs & negatives
    ai_labeled = ai_pos_hits | ai_neg_hits

    strict_precision = round(len(ai_pos_hits) / len(ai_pairs), 3) if ai_pairs else None
    judged_denominator = len(ai_pos_hits) + len(ai_neg_hits)
    judged_precision = (
        round(len(ai_pos_hits) / judged_denominator, 3) if judged_denominator else None
    )
    ai_recall_core = round(len(ai_pairs & core) / len(core), 3) if core else None
    ai_recall_novel = (
        round(len(ai_pairs & novel_positives) / len(novel_positives), 3)
        if novel_positives else None
    )
    graph_coverage = (
        round(len(merged_pairs & positives) / len(positives), 3) if positives else None
    )
    graph_core_coverage = (
        round(len(merged_pairs & core) / len(core), 3) if core else None
    )
    graph_extended_coverage = (
        round(len(merged_pairs & extended) / len(extended), 3) if extended else None
    )
    graph_novel_coverage = (
        round(len(merged_pairs & novel_positives) / len(novel_positives), 3)
        if novel_positives else None
    )

    recall_for_f1 = ai_recall_novel if novel_positives else ai_recall_core
    return {
        "available": True,
        "version": gold.get("version"),
        "status": gold.get("status"),
        "status_label": "双人标注" if gold.get("status") == "double_annotated" else "单人初标",
        "labels_total": len(gold["labels"]),
        "positive_total": len(positives),
        "negative_total": len(negatives),
        "core_positive_total": len(core),
        "extended_positive_total": len(extended),
        "novel_positive_total": len(novel_positives),
        "expert_overlap_positive_total": len(expert_overlap),
        "graph_coverage": graph_coverage,
        "graph_core_coverage": graph_core_coverage,
        "graph_extended_coverage": graph_extended_coverage,
        "graph_novel_coverage": graph_novel_coverage,
        "ai_labeled": len(ai_labeled),
        "ai_unlabeled": len(ai_pairs) - len(ai_labeled),
        "ai_positive_hits": len(ai_pos_hits),
        "ai_negative_hits": len(ai_neg_hits),
        "strict_precision": strict_precision,
        "judged_precision": judged_precision,
        "ai_recall_core": ai_recall_core,
        "ai_recall_novel": ai_recall_novel,
        "strict_f1": _f1(strict_precision, recall_for_f1),
        "judged_f1": _f1(judged_precision, recall_for_f1),
        "kappa": gold.get("kappa"),
        "kappa_status": gold.get("kappa_status"),
        "agreement": gold.get("agreement"),
        "double_labeled": len(gold["double_labels"]),
        "unresolved_disagreements": gold.get("unresolved_disagreements", 0),
        "annotators": gold.get("annotators") or [],
        "detail": gold.get("detail") or "",
    }



def _find_cycles(prereq_map: dict) -> list:
    """找出先修图中的环，返回环路径样本（最多 MAX_CYCLE_SAMPLES 条）。"""
    adjacency = {}
    for target, parents in (prereq_map or {}).items():
        for parent in parents or []:
            adjacency.setdefault(parent, []).append(target)

    cycles, seen_cycles = [], set()
    visiting, visited = set(), set()
    stack = []

    def walk(node):
        if len(cycles) >= MAX_CYCLE_SAMPLES:
            return
        visiting.add(node)
        stack.append(node)
        for nxt in adjacency.get(node, []):
            if nxt in visiting:
                start = stack.index(nxt)
                cycle = tuple(stack[start:] + [nxt])
                key = frozenset(cycle)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(list(cycle))
            elif nxt not in visited:
                walk(nxt)
        stack.pop()
        visiting.discard(node)
        visited.add(node)

    for node in list(adjacency):
        if node not in visited:
            walk(node)
    return cycles


def _kendall_tau(order_a: list, order_b: list) -> float:
    """两个任务顺序的一致性：1 完全一致，-1 完全相反。只比较两边都出现的任务。"""
    present = set(order_b)
    items = [item for item in order_a if item in present]
    n = len(items)
    if n < 2:
        return 1.0
    rank_b = {item: index for index, item in enumerate(order_b)}
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            if rank_b[items[i]] < rank_b[items[j]]:
                concordant += 1
            elif rank_b[items[i]] > rank_b[items[j]]:
                discordant += 1
    total = n * (n - 1) / 2
    return round((concordant - discordant) / total, 3)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 1)


def _order_of(result: dict) -> list:
    return [
        task.get("topic") or task.get("knowledge") or ""
        for phase in (result or {}).get("phases") or []
        for task in phase.get("tasks") or []
    ]


def _changed_positions(order_a: list, order_b: list) -> int:
    index_b = {item: index for index, item in enumerate(order_b)}
    return sum(
        1 for index, item in enumerate(order_a)
        if item in index_b and index_b[item] != index
    )


# ===== 1. 结构健康 =====

def _evaluate_structure(graph: dict, expert_prereq: dict) -> dict:
    nodes = (graph or {}).get("nodes") or []
    edges = (graph or {}).get("edges") or []
    node_ids = set(_node_index(graph))

    degree = {tag: 0 for tag in node_ids}
    dangling, self_loops, duplicates = [], [], []
    seen_pairs = set()
    adjacency = {tag: [] for tag in node_ids}

    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation = edge.get("relation") or kg.REL_PREREQUISITE
        if not source or not target:
            dangling.append({"source": source, "target": target, "reason": "缺少起点或终点"})
            continue
        if source not in node_ids or target not in node_ids:
            dangling.append({
                "source": source, "target": target,
                "reason": "端点不在课程知识点名单内",
            })
            continue
        if source == target:
            self_loops.append({"source": source, "target": target})
            continue
        key = (source, target, relation)
        if key in seen_pairs:
            duplicates.append({"source": source, "target": target, "relation": relation})
            continue
        seen_pairs.add(key)
        degree[source] += 1
        degree[target] += 1
        if relation == kg.REL_PREREQUISITE:
            adjacency[source].append(target)

    isolated = [tag for tag, count in degree.items() if count == 0]
    cycles = _find_cycles(adjacency)

    described = [node for node in nodes if str(node.get("definition") or "").strip()]
    description_coverage = round(len(described) / len(nodes), 3) if nodes else 0.0

    score = 100.0
    score -= 15 * len(cycles)
    score -= 6 * len(dangling)
    score -= 5 * len(isolated)
    score -= 4 * len(self_loops)
    score -= 2 * len(duplicates)
    if graph.get("generated_by") == "llm" and description_coverage < 0.8:
        score -= (0.8 - description_coverage) * 50

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "prerequisite": sum(1 for e in edges if (e.get("relation") or "") == kg.REL_PREREQUISITE),
        "similar": sum(1 for e in edges if e.get("relation") == kg.REL_SIMILAR),
        "part_of": sum(1 for e in edges if e.get("relation") == kg.REL_PART_OF),
        "isolated_nodes": isolated,
        "dangling_edges": dangling,
        "self_loops": self_loops,
        "duplicate_edges": duplicates,
        "cycles": cycles,
        "has_cycle": bool(cycles),
        "description_coverage": description_coverage,
        "generated_by": graph.get("generated_by") or "expert",
        "score": _clamp(score),
    }


# ===== 2. 边质量 =====

def _evaluate_edge_quality(graph: dict, expert_prereq: dict, merged_map: dict) -> dict:
    node_ids = set(_node_index(graph))
    expert_pairs = _expert_pairs(expert_prereq, node_ids)
    edges = (graph or {}).get("edges") or []
    ai_edges = [
        edge for edge in edges
        if edge.get("origin") == "llm" and edge.get("relation") == kg.REL_PREREQUISITE
    ]
    ai_pairs = {
        (str(e.get("source") or "").strip(), str(e.get("target") or "").strip())
        for e in ai_edges
    }

    duplicates = ai_pairs & expert_pairs
    reversed_pairs = {pair for pair in ai_pairs if (pair[1], pair[0]) in expert_pairs}
    novel = ai_pairs - duplicates - reversed_pairs

    review = Counter()
    for edge in ai_edges:
        review[str(edge.get("review_status") or kg.REVIEW_PENDING)] += 1
    accepted = review.get(kg.REVIEW_ACCEPTED, 0)
    rejected = review.get(kg.REVIEW_REJECTED, 0)
    reviewed = accepted + rejected
    accept_rate = round(accepted / reviewed, 3) if reviewed else None

    merged_pairs = {
        (str(source).strip(), str(target).strip())
        for target, parents in (merged_map or {}).items()
        for source in parents or []
    }
    expert_retention = (
        round(len(merged_pairs & expert_pairs) / len(expert_pairs), 3)
        if expert_pairs else 1.0
    )

    # 独立金标准：strict / judged 两套精确率 + 新增正例召回 + 图谱覆盖率 + kappa
    gold = _gold_metrics(_load_gold_standard(), ai_pairs, merged_pairs, expert_pairs, node_ids)
    stability = _stability_report()

    # 自动可核对的 AI 边只有「重复专家边」和「方向与专家边相反」两类，
    # 作为金标准缺失时的兜底代理指标。
    checkable = len(duplicates) + len(reversed_pairs)
    auto_precision = (
        round(len(duplicates) / checkable, 3) if checkable else None
    )

    precision, precision_source = None, None
    if gold["judged_precision"] is not None:
        precision, precision_source = gold["judged_precision"], "gold_judged"
    elif gold["strict_precision"] is not None:
        # judged 无法计算（金标准没覆盖任何 AI 边）时，用保守下界 strict
        precision, precision_source = gold["strict_precision"], "gold_strict"
    elif auto_precision is not None:
        precision, precision_source = auto_precision, "expert_reference"
    elif accept_rate is not None:
        precision, precision_source = accept_rate, "human_review"

    if gold["ai_recall_novel"] is not None:
        recall, recall_source = gold["ai_recall_novel"], "gold_novel"
    elif gold["ai_recall_core"] is not None:
        recall, recall_source = gold["ai_recall_core"], "gold_core"
    else:
        recall, recall_source = expert_retention, "expert_retention"

    f1 = _f1(precision, recall)

    if not ai_edges:
        score = None
        detail = "当前只有专家先修骨架，没有 AI 生成的关系，边质量无法评估。"
    else:
        base = precision if precision is not None else 0.6
        score = _clamp(100 * (0.65 * base + 0.35 * recall))
        if gold["available"]:
            detail = (
                f"AI 共提出 {len(ai_edges)} 条先修关系；独立金标准（{gold['version']}，"
                f"{gold['status_label']}）标注了 {gold['labels_total']} 条边，其中 "
                f"{gold['ai_labeled']} 条 AI 边得到判定（命中正例 {gold['ai_positive_hits']} 条、"
                f"命中负例 {gold['ai_negative_hits']} 条），{gold['ai_unlabeled']} 条未被金标准覆盖。"
                f"strict 精确率 {round((gold['strict_precision'] or 0) * 100)}%（未覆盖按错误计），"
                f"judged 精确率 {round((gold['judged_precision'] or 0) * 100)}%，"
                f"新增正例召回 {round((gold['ai_recall_novel'] or 0) * 100)}%，"
                f"图谱对金标准正例的整体覆盖率 {round((gold['graph_coverage'] or 0) * 100)}%。"
            )
        else:
            detail = (
                f"AI 共提出 {len(ai_edges)} 条先修关系：{len(duplicates)} 条与专家表重复，"
                f"{len(reversed_pairs)} 条方向与专家表相反，{len(novel)} 条是专家表未覆盖的新主张；"
                f"人工已审核 {reviewed} 条（采纳 {accepted} 条、拒绝 {rejected} 条）。"
            )

    if gold["available"]:
        method_note = (
            "精确率以独立金标准边集为参照：strict 把未被金标准覆盖的 AI 边按错误计，"
            "是保守下界；judged 只统计已被标注的 AI 边，更接近真实精确率。"
            "召回率优先看专家表未覆盖的金标准正例（novel），避免 AI 被要求避开专家边导致召回失真；"
            "kappa 只在两位标注者都填过的边上计算，缺第二位标注时如实显示待补。"
        )
    else:
        method_note = (
            "未找到独立金标准边集，只能用代理指标："
            "把「专家边保留率」当作召回率，把「与专家冲突的比例」或「人工审核采纳率」当作精确率。"
            "这两项不是严格的准确率，建议补上金标准后再对外引用。"
        )

    return {
        "applicable": bool(ai_edges),
        "reference_edges": len(expert_pairs),
        "expert_retention": expert_retention,
        "ai_edges": len(ai_edges),
        "novel_claims": len(novel),
        "duplicate_of_expert": len(duplicates),
        "reversed_conflicts": len(reversed_pairs),
        "review": {
            "accepted": accepted,
            "pending": review.get(kg.REVIEW_PENDING, 0),
            "rejected": rejected,
            "reviewed": reviewed,
            "accept_rate": accept_rate,
        },
        "precision": precision,
        "precision_source": precision_source,
        "recall": recall,
        "recall_source": recall_source,
        "f1": f1,
        "gold": gold,
        "stability": stability,
        "score": score,
        "detail": detail,
        "method_note": method_note,
    }


# ===== 3. 路径影响 =====

_PERSONAS = [
    {
        "key": "weak", "name": "基础薄弱", "level": "beginner",
        "mode": "补弱优先",
        "targets": [
            "dsa-dsa-linear-data-structures",
            "dsa-binary-search-tree-insert",
            "dsa-heap-sort",
        ],
        "weekly_hours": 5, "deadline_weeks": 6,
    },
    {
        "key": "medium", "name": "有一定基础", "level": "intermediate",
        "mode": "均衡",
        "targets": [
            "dsa-binary-search-traverse",
            "dsa-graph-theory-deep",
            "dsa-merge-sort",
        ],
        "weekly_hours": 8, "deadline_weeks": 6,
    },
    {
        "key": "strong", "name": "较为熟练", "level": "advanced",
        "mode": "省时优先",
        "targets": [
            "dsa-graph-theory-short-path",
            "dsa-dsa-hash-table",
            "dsa-dsa-dynamic-programming",
        ],
        "weekly_hours": 10, "deadline_weeks": 4,
    },
]

_PROFILE_VALUES = {
    # 按课程知识点顺序取值，保证每次测评结果可复现
    "weak": [0.25, 0.22, 0.24, 0.26, 0.28, 0.25, 0.24, 0.27, 0.30, 0.26, 0.23],
    "medium": [0.55, 0.35, 0.62, 0.45, 0.38, 0.58, 0.36, 0.52, 0.60, 0.34, 0.48],
    "strong": [0.82, 0.78, 0.85, 0.74, 0.68, 0.80, 0.72, 0.76, 0.83, 0.66, 0.70],
}


def _persona_mastery(key: str) -> dict:
    tags = [item["tag"] for item in agent_course.course_knowledge_points()]
    values = _PROFILE_VALUES.get(key) or []
    return {
        tag: values[index] if index < len(values) else 0.5
        for index, tag in enumerate(tags)
    }


def _variant_contexts(graph: dict, expert: dict, mastery: dict) -> dict:
    """构造三种编排共用的先修表与图谱上下文。"""
    try:
        from services.teaching_policy_service import MASTERY_HIGH, MASTERY_LOW
    except Exception:
        MASTERY_HIGH, MASTERY_LOW = 0.7, 0.4

    expert_map = {item["tag"]: [] for item in agent_course.course_knowledge_points()}
    for target, parents in (expert or {}).items():
        if target in expert_map:
            expert_map[target] = [p for p in parents or [] if p in expert_map and p != target]

    known_tags = set(kg.node_name_index(graph)) or {
        item["tag"] for item in agent_course.course_knowledge_points()
    }
    skeleton_graph = {
        "nodes": [
            {"tag": item["tag"], "name": item["name"], "definition": "", "key_points": [], "confusable": []}
            for item in agent_course.course_knowledge_points()
        ],
        "edges": [
            {
                "source": source, "target": target,
                "relation": kg.REL_PREREQUISITE, "origin": "expert",
                "confidence": 1.0, "review_status": kg.REVIEW_ACCEPTED,
            }
            for (source, target) in sorted(_expert_pairs(expert, known_tags))
        ],
    }
    skeleton_context = {
        "has_graph": True,
        "graph": skeleton_graph,
        "source": "expert",
        "added_edges": [],
        "readiness": kg.propagate_readiness(
            skeleton_graph, expert_map, mastery, MASTERY_LOW, MASTERY_HIGH
        ),
        "similar": {},
        "names": kg.node_name_index(skeleton_graph),
    }

    merged_map, added_edges = kg.effective_prerequisite_map(graph, expert)
    full_context = {
        "has_graph": True,
        "graph": graph,
        "source": graph.get("generated_by") or "llm",
        "added_edges": added_edges,
        "readiness": kg.propagate_readiness(
            graph, merged_map, mastery, MASTERY_LOW, MASTERY_HIGH
        ),
        "similar": kg.similar_index(graph),
        "names": kg.node_name_index(graph),
    }
    return {
        "expert_map": expert_map,
        "merged_map": merged_map,
        "skeleton_context": skeleton_context,
        "full_context": full_context,
    }


def _plan_variants(graph: dict, expert: dict, persona: dict) -> dict:
    """同一份掌握度下跑三种编排：不用图谱 / 专家骨架 / 完整图谱。"""
    all_tracks = [track["name"] for track in agent_course.COURSE_TRACKS]
    mastery = _persona_mastery(persona["key"])
    profile = {
        "level": persona["level"],
        "level_label": persona["name"],
        "source": "evaluation",
        "mastery": mastery,
    }
    contexts = _variant_contexts(graph, expert, mastery)

    baseline = agent_course.plan_course_path(all_tracks, profile, prereq_map=expert)
    skeleton = agent_course.plan_course_path(
        all_tracks, profile,
        prereq_map=contexts["expert_map"],
        graph_context=contexts["skeleton_context"],
    )
    full = agent_course.plan_course_path(
        all_tracks, profile,
        prereq_map=contexts["merged_map"],
        graph_context=contexts["full_context"],
    )
    return {
        "mastery": mastery,
        "contexts": contexts,
        "baseline": baseline,
        "skeleton": skeleton,
        "full": full,
    }


def _plan_knowledge_variants(graph: dict, expert: dict, persona: dict, contexts: dict) -> dict:
    """同一份掌握度下，用真实知识点规划器跑三种编排。"""
    mastery = _persona_mastery(persona["key"])
    weekly_hours = persona.get("weekly_hours") or 6
    deadline_weeks = persona.get("deadline_weeks") or 8
    budget_minutes = int(weekly_hours * 60 * deadline_weeks)
    profile = {
        "level": persona["level"],
        "level_label": persona["name"],
        "source": "evaluation",
        "mastery": mastery,
        "target_tags": list(persona.get("targets") or []),
        "time_budget": {
            "budget_minutes": budget_minutes,
            "weekly_hours": weekly_hours,
            "deadline_weeks": deadline_weeks,
            "source": "evaluation",
        },
        "preferences": {"mode": persona.get("mode") or ""},
    }
    baseline = agent_course.plan_knowledge_path(
        mastery=mastery, prereq_map=expert, level_profile=profile
    )
    skeleton = agent_course.plan_knowledge_path(
        mastery=mastery, prereq_map=contexts["expert_map"],
        graph_context=contexts["skeleton_context"], level_profile=profile,
    )
    full = agent_course.plan_knowledge_path(
        mastery=mastery, prereq_map=contexts["merged_map"],
        graph_context=contexts["full_context"], level_profile=profile,
    )
    return {
        "budget_minutes": budget_minutes,
        "weekly_hours": weekly_hours,
        "deadline_weeks": deadline_weeks,
        "baseline": baseline,
        "skeleton": skeleton,
        "full": full,
    }


def _knowledge_summary(plan: dict, prereq_map: dict, target_tags: list,
                       budget_minutes: int) -> dict:
    """从知识点路线的真实输出里算五类质量指标。"""
    units = (plan or {}).get("units") or []
    remaining = [unit for unit in units if unit.get("status") != "done"]
    order = [unit["tag"] for unit in remaining]
    position = {tag: index for index, tag in enumerate(order)}

    pairs = [
        (parent, target)
        for target, parents in (prereq_map or {}).items()
        for parent in parents or []
        if parent in position and target in position and parent != target
    ]
    violations = sum(1 for parent, target in pairs if position[parent] > position[target])
    violation_rate = violations / len(pairs) if pairs else 0.0

    target_set = set(target_tags or [])
    covered = {
        unit["tag"] for unit in units
        if unit.get("status") == "done" and unit["tag"] in target_set
    }
    budget = int(budget_minutes or 0)
    cumulative = 0
    for unit in remaining:
        cumulative += unit.get("estimated_minutes") or 0
        if budget and cumulative > budget:
            break
        if unit["tag"] in target_set:
            covered.add(unit["tag"])
    target_coverage = len(covered) / len(target_set) if target_set else 1.0

    difficulties = [
        unit.get("difficulty") for unit in remaining
        if isinstance(unit.get("difficulty"), (int, float))
    ]
    jumps = [
        abs(difficulties[index] - difficulties[index - 1])
        for index in range(1, len(difficulties))
    ]
    avg_jump = sum(jumps) / len(jumps) if jumps else 0.0
    smoothness = max(0.0, min(1.0, 1 - avg_jump / 4))

    remaining_minutes = sum(unit.get("estimated_minutes") or 0 for unit in remaining)
    if budget:
        time_fit = min(1.0, budget / remaining_minutes) if remaining_minutes else 1.0
        over_budget = max(0, remaining_minutes - budget)
    else:
        time_fit = 1.0
        over_budget = 0

    return {
        "remaining_units": len(remaining),
        "estimated_minutes": remaining_minutes,
        "budget_minutes": budget,
        "over_budget_minutes": over_budget,
        "prerequisite_pairs": len(pairs),
        "prerequisite_violations": violations,
        "prerequisite_violation_rate": round(violation_rate, 3),
        "target_total": len(target_set),
        "target_covered": len(covered),
        "target_coverage": round(target_coverage, 3),
        "difficulty_avg_jump": round(avg_jump, 2),
        "difficulty_smoothness": round(smoothness, 3),
        "time_fit": round(time_fit, 3),
    }


_KNOWLEDGE_METRIC_KEYS = (
    "prerequisite_violation_rate",
    "target_coverage",
    "difficulty_smoothness",
    "time_fit",
)


def _average_knowledge(rows: list, variant: str) -> dict:
    if not rows:
        return {}
    return {
        key: round(sum((row[variant] or {}).get(key) or 0 for row in rows) / len(rows), 3)
        for key in _KNOWLEDGE_METRIC_KEYS
    }


def _knowledge_quality(metrics: dict) -> float:
    """把五项指标压成一个 0~100 的质量分。"""
    violation_score = max(0.0, 1 - float(metrics.get("prerequisite_violation_rate") or 0))
    coverage = float(metrics.get("target_coverage") or 0)
    smoothness = float(metrics.get("difficulty_smoothness") or 0)
    time_fit = float(metrics.get("time_fit") or 0)
    return round(
        100 * (0.40 * violation_score + 0.30 * coverage + 0.15 * smoothness + 0.15 * time_fit),
        1,
    )


def _summarize_plan(result: dict) -> dict:
    op = ((result or {}).get("applied_operators") or {}).get("graph") or {}
    tasks = [
        task
        for phase in (result or {}).get("phases") or []
        for task in phase.get("tasks") or []
    ]
    return {
        "order": _order_of(result),
        "blocked": len(op.get("readiness_blocked") or []),
        "skip_blocked": len(op.get("skip_blocked") or []),
        "remedial_focus": len(op.get("remedial_links") or []),
        "remedial_inserted": len(op.get("remedial_inserted") or []),
        "skippable": sum(1 for task in tasks if task.get("skippable")),
        "merged_edges": len(op.get("merged_edge_samples") or []) if op.get("merged_edges") else 0,
    }


def _evaluate_path_impact(graph: dict, expert: dict) -> dict:
    profiles = []
    knowledge_profiles = []
    knowledge_orders = {}
    blocked_total = remedial_total = changed_total = 0
    taus = []

    for persona in _PERSONAS:
        plans = _plan_variants(graph, expert, persona)
        baseline = _summarize_plan(plans["baseline"])
        skeleton = _summarize_plan(plans["skeleton"])
        full = _summarize_plan(plans["full"])

        tau = _kendall_tau(baseline["order"], full["order"])
        changed = _changed_positions(baseline["order"], full["order"])
        ai_changed = _changed_positions(skeleton["order"], full["order"])

        blocked_total += full["blocked"]
        remedial_total += full["remedial_focus"] + full["remedial_inserted"]
        changed_total += changed
        taus.append(tau)

        profiles.append({
            "key": persona["key"],
            "name": persona["name"],
            "mastery": plans["mastery"],
            "baseline": {
                "skippable": baseline["skippable"],
                "blocked": 0,
                "remedial_focus": 0,
            },
            "with_graph": {
                "blocked": full["blocked"],
                "skip_blocked": full["skip_blocked"],
                "remedial_focus": full["remedial_focus"],
                "remedial_inserted": full["remedial_inserted"],
                "skippable": full["skippable"],
            },
            "skeleton": {
                "blocked": skeleton["blocked"],
                "remedial_focus": skeleton["remedial_focus"],
                "skippable": skeleton["skippable"],
            },
            "changed_positions": changed,
            "ai_edge_changed_positions": ai_changed,
            "kendall_tau": tau,
            "summary": (
                f"{persona['name']}：图谱拦下 {full['blocked']} 个前置未达标的项目，"
                f"标出 {full['remedial_focus']} 个补先修重点，顺序变化 {changed} 处，"
                f"与不用图谱的顺序一致性 τ={tau}。"
            ),
        })

        # 知识点级路径：用真实规划器输出计算质量指标
        contexts = plans["contexts"]
        knowledge_plans = _plan_knowledge_variants(graph, expert, persona, contexts)
        targets = list(persona.get("targets") or [])
        budget = knowledge_plans["budget_minutes"]
        knowledge = {
            "baseline": _knowledge_summary(knowledge_plans["baseline"], expert, targets, budget),
            "skeleton": _knowledge_summary(
                knowledge_plans["skeleton"], contexts["expert_map"], targets, budget
            ),
            "full": _knowledge_summary(
                knowledge_plans["full"], contexts["merged_map"], targets, budget
            ),
        }
        knowledge_orders[persona["key"]] = [
            unit["tag"]
            for unit in (knowledge_plans["full"].get("units") or [])
            if unit.get("status") != "done"
        ]
        round3 = lambda value: round(value, 3)
        knowledge_profiles.append({
            "key": persona["key"],
            "name": persona["name"],
            "weekly_hours": knowledge_plans["weekly_hours"],
            "deadline_weeks": knowledge_plans["deadline_weeks"],
            "budget_minutes": budget,
            "targets": [
                {"tag": tag, "name": agent_course.course_point_names().get(tag) or tag}
                for tag in targets
            ],
            "baseline": knowledge["baseline"],
            "skeleton": knowledge["skeleton"],
            "full": knowledge["full"],
            "delta": {
                # 违规率下降记为正数，其余指标上升记为正数
                "prerequisite_violation_rate": round3(
                    knowledge["baseline"]["prerequisite_violation_rate"]
                    - knowledge["full"]["prerequisite_violation_rate"]
                ),
                "target_coverage": round3(
                    knowledge["full"]["target_coverage"]
                    - knowledge["baseline"]["target_coverage"]
                ),
                "difficulty_smoothness": round3(
                    knowledge["full"]["difficulty_smoothness"]
                    - knowledge["baseline"]["difficulty_smoothness"]
                ),
                "time_fit": round3(
                    knowledge["full"]["time_fit"] - knowledge["baseline"]["time_fit"]
                ),
            },
            "summary": (
                f"{persona['name']}：先修违规率 "
                f"{round(knowledge['full']['prerequisite_violation_rate'] * 100)}%，"
                f"预算内覆盖目标 {knowledge['full']['target_covered']}/"
                f"{knowledge['full']['target_total']}，"
                f"难度平滑度 {round(knowledge['full']['difficulty_smoothness'] * 100)}%，"
                f"时长贴合度 {round(knowledge['full']['time_fit'] * 100)}%。"
            ),
        })

    divergence_pairs = []
    for index, first in enumerate(knowledge_profiles):
        for second in knowledge_profiles[index + 1:]:
            tau = _kendall_tau(
                knowledge_orders.get(first["key"]) or [],
                knowledge_orders.get(second["key"]) or [],
            )
            divergence_pairs.append({
                "a": first["name"],
                "b": second["name"],
                "tau": tau,
                "difference": round(1 - tau, 3),
            })
    average_difference = (
        round(sum(pair["difference"] for pair in divergence_pairs) / len(divergence_pairs), 3)
        if divergence_pairs else 0.0
    )

    knowledge_metrics = {
        "variants": {
            "baseline": "不用图谱",
            "skeleton": "专家骨架",
            "full": "完整图谱",
        },
        "by_profile": knowledge_profiles,
        "average": {
            "baseline": _average_knowledge(knowledge_profiles, "baseline"),
            "skeleton": _average_knowledge(knowledge_profiles, "skeleton"),
            "full": _average_knowledge(knowledge_profiles, "full"),
        },
        "divergence": {
            "pairs": divergence_pairs,
            "average_difference": average_difference,
        },
        "method_note": (
            "五项指标都由真实知识点规划器 plan_knowledge_path 的输出计算，"
            "三类学生是按固定掌握度模拟的画像，不是真实学生数据；"
            "真实学生对照实验（前后测/随机分组）仍需线下采集，见进度表 V8。"
        ),
    }

    avg_tau = round(sum(taus) / len(taus), 3) if taus else 1.0
    full_average = knowledge_metrics["average"]["full"]
    quality = _knowledge_quality(full_average)
    score = 0.0
    score += 20 if profiles else 0
    score += 10 if blocked_total > 0 else 0
    score += 10 if remedial_total > 0 else 0
    score += 10 if changed_total > 0 else 0
    score += round(quality * 0.5, 1)

    return {
        "profiles": profiles,
        "knowledge_metrics": knowledge_metrics,
        "blocked_total": blocked_total,
        "remedial_total": remedial_total,
        "changed_positions_total": changed_total,
        "avg_kendall_tau": avg_tau,
        "knowledge_quality": quality,
        "score": _clamp(score),
        "detail": (
            f"模拟 3 类学生：图谱共拦下 {blocked_total} 个前置未达标的项目，"
            f"标出 {remedial_total} 个补先修重点，平均顺序一致性 τ={avg_tau}。"
            f"知识点路线平均先修违规率 "
            f"{round(full_average.get('prerequisite_violation_rate', 0) * 100)}%，"
            f"预算内目标覆盖率 "
            f"{round(full_average.get('target_coverage', 0) * 100)}%，"
            f"难度平滑度 {round(full_average.get('difficulty_smoothness', 0) * 100)}%，"
            f"时长贴合度 {round(full_average.get('time_fit', 0) * 100)}%，"
            f"三类学生路线平均差异度 {round(average_difference * 100)}%。"
            + ("" if changed_total else " 当前图谱没有改变任何项目顺序，说明先修约束与课程原顺序一致。")
        ),
    }


# ===== 4. 证据覆盖 =====

def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _quick_quiz_counts() -> Counter:
    data = _load_json(os.path.join(WORKSPACE_BACKEND, "data", "quick_quiz_dsa.json"), {})
    return Counter(
        item.get("knowledge_tag")
        for item in data.get("questions") or []
        if item.get("knowledge_tag")
    )


def _tutorial_counts() -> Counter:
    data = _load_json(os.path.join(WORKSPACE_BACKEND, "data", "dsa_tutorial_seed.json"), [])
    if not isinstance(data, list):
        return Counter()
    return Counter(
        item.get("knowledge_tag")
        for item in data
        if isinstance(item, dict) and item.get("knowledge_tag")
    )


def _evaluate_coverage(graph: dict) -> dict:
    nodes = _node_index(graph)
    projects = agent_course.project_index()
    quiz_counts = _quick_quiz_counts()
    tutorial_counts = _tutorial_counts()
    similar = kg.similar_index(graph)

    per_node = []
    with_project = with_quiz = with_tutorial = with_description = 0
    for tag, node in nodes.items():
        project_count = len(projects.get(tag) or [])
        quiz_count = quiz_counts.get(tag, 0)
        tutorial_count = tutorial_counts.get(tag, 0)
        has_description = bool(str(node.get("definition") or "").strip())
        with_project += 1 if project_count else 0
        with_quiz += 1 if quiz_count else 0
        with_tutorial += 1 if tutorial_count else 0
        with_description += 1 if has_description else 0
        per_node.append({
            "tag": tag,
            "name": node.get("name") or tag,
            "projects": project_count,
            "quiz_questions": quiz_count,
            "tutorial_docs": tutorial_count,
            "has_description": has_description,
            "similar_count": len(similar.get(tag) or []),
            "confusable_count": len(node.get("confusable") or []),
        })

    total = len(nodes) or 1
    project_rate = with_project / total
    quiz_rate = with_quiz / total
    tutorial_rate = with_tutorial / total
    description_rate = with_description / total
    score = 100 * (
        0.30 * project_rate + 0.30 * quiz_rate + 0.20 * tutorial_rate + 0.20 * description_rate
    )
    fully_covered = sum(
        1 for item in per_node
        if item["projects"] and item["quiz_questions"] and item["tutorial_docs"] and item["has_description"]
    )

    return {
        "nodes": len(nodes),
        "fully_covered": fully_covered,
        "with_projects": with_project,
        "with_quiz": with_quiz,
        "with_tutorial": with_tutorial,
        "with_description": with_description,
        "project_rate": round(project_rate, 3),
        "quiz_rate": round(quiz_rate, 3),
        "tutorial_rate": round(tutorial_rate, 3),
        "description_rate": round(description_rate, 3),
        "per_node": sorted(per_node, key=lambda item: item["tag"]),
        "score": _clamp(score),
        "detail": (
            f"{len(nodes)} 个知识点中，{with_project} 个有实训项目、{with_quiz} 个有快速测评题、"
            f"{with_tutorial} 个有教程、{with_description} 个有 AI 描述；"
            f"四项齐全的有 {fully_covered} 个。"
        ),
    }


# ===== 汇总 =====

def _build_checks(structure: dict, edge: dict, impact: dict, coverage: dict) -> list:
    checks = [
        {
            "key": "no_cycle",
            "label": "先修关系无环",
            "status": "fail" if structure["has_cycle"] else "pass",
            "value": f"{len(structure['cycles'])} 个环",
            "detail": "存在环形依赖会导致路径无法排序。" if structure["has_cycle"] else "先修关系可以正常拓扑排序。",
        },
        {
            "key": "no_dangling",
            "label": "先修边两端都在知识点名单内",
            "status": "fail" if structure["dangling_edges"] else "pass",
            "value": f"{len(structure['dangling_edges'])} 条悬挂边",
            "detail": "悬挂边指向不存在的知识点，会被路径编排忽略。" if structure["dangling_edges"] else "所有先修边都能落到具体知识点。",
        },
        {
            "key": "no_isolated",
            "label": "没有孤立知识点",
            "status": "warn" if structure["isolated_nodes"] else "pass",
            "value": f"{len(structure['isolated_nodes'])} 个孤立点",
            "detail": "孤立点既不依赖别人，也没有后继，图谱无法为它提供上下文。" if structure["isolated_nodes"] else "每个知识点都至少与一条关系相连。",
        },
        {
            "key": "expert_retention",
            "label": "专家先修边完整保留",
            "status": "pass" if edge["expert_retention"] >= 0.999 else "fail",
            "value": f"{round(edge['expert_retention'] * 100)}%",
            "detail": f"专家维护的 {edge['reference_edges']} 条先修边中，有 {round(edge['expert_retention'] * edge['reference_edges'])} 条进入实际编排。",
        },
    ]

    if edge["applicable"]:
        pending = edge["review"]["pending"]
        checks.append({
            "key": "edge_review",
            "label": "AI 关系已处理",
            "status": "warn" if pending else "pass",
            "value": f"{pending} 条待审核",
            "detail": "待审核的 AI 边不参与路径编排，确认后才会生效。" if pending else "AI 边都已采纳或拒绝。",
        })
    else:
        checks.append({
            "key": "edge_review",
            "label": "AI 关系已生成",
            "status": "warn",
            "value": "尚未生成",
            "detail": "当前只有专家先修骨架，可以点击「生成知识图谱」让 AI 补充描述与关系。",
        })

    gold = edge.get("gold") or {}
    if not gold.get("available"):
        checks.append({
            "key": "edge_gold_standard",
            "label": "AI 边有独立金标准对照",
            "status": "warn",
            "value": "未找到金标准",
            "detail": "没有独立金标准边集时，精确率只能用代理指标，不能当作真实准确率对外引用。",
        })
    elif gold.get("status") == "double_annotated" and gold.get("kappa") is not None:
        kappa = gold["kappa"]
        checks.append({
            "key": "edge_gold_standard",
            "label": "AI 边有独立金标准对照",
            "status": "pass" if kappa >= 0.6 else "warn" if kappa >= 0.4 else "fail",
            "value": f"双人标注 {gold.get('labels_total')} 条，kappa {kappa}",
            "detail": "两位标注者独立标注，一致性越高，金标准越可信。" if kappa >= 0.6
                      else "两位标注者一致性偏低，建议先复核有分歧的边再对外引用指标。",
        })
    else:
        checks.append({
            "key": "edge_gold_standard",
            "label": "AI 边有独立金标准对照",
            "status": "warn",
            "value": f"单人初标 {gold.get('labels_total')} 条，kappa 待补",
            "detail": "当前只有标注者 A 的初标结果，第二位教师尚未独立标注，双人一致性（kappa）无法计算。",
        })

    stability = edge.get("stability") or {}
    if stability.get("status") != "sampled":
        checks.append({
            "key": "edge_generation_stability",
            "label": "同一输入多次生成稳定",
            "status": "warn",
            "value": "未抽检",
            "detail": stability.get("detail") or "还没有至少 2 次真实生成快照。",
        })
    else:
        mean = float(stability.get("mean_jaccard") or 0)
        checks.append({
            "key": "edge_generation_stability",
            "label": "同一输入多次生成稳定",
            "status": "pass" if mean >= 0.8 else "warn" if mean >= 0.6 else "fail",
            "value": f"{stability.get('runs')} 次生成，Jaccard 均值 {round(mean * 100)}%",
            "detail": "多次生成的关系重叠度高，说明结果稳定。" if mean >= 0.8
                      else "多次生成的关系差异较大，说明结果对随机性敏感，重要边需要人工确认。",
        })

    checks.append({
        "key": "path_integration",
        "label": "图谱真正影响编排",
        "status": "pass" if impact["changed_positions_total"] or impact["blocked_total"] else "warn",
        "value": f"拦截 {impact['blocked_total']} 次 / 顺序变化 {impact['changed_positions_total']} 处",
        "detail": "图谱已进入路径编排，能拦住前置没打牢的项目。" if (impact["blocked_total"] or impact["changed_positions_total"]) else "图谱没有改变编排结果，需要检查先修关系是否与课程原顺序完全一致。",
    })

    knowledge_full = (((impact.get("knowledge_metrics") or {}).get("average") or {}).get("full") or {})
    if knowledge_full:
        violation = float(knowledge_full.get("prerequisite_violation_rate") or 0)
        checks.append({
            "key": "path_prerequisite_order",
            "label": "学习顺序遵守先修关系",
            "status": "pass" if violation <= 0.02 else "warn" if violation <= 0.10 else "fail",
            "value": f"违规率 {round(violation * 100)}%",
            "detail": "知识点路线里，前面的知识点都被排在它依赖的知识点之后。" if violation <= 0.02 else "有知识点排在了它依赖的知识点之前，学生可能因基础不够而卡住。",
        })
        coverage_rate = float(knowledge_full.get("target_coverage") or 0)
        covered = round(coverage_rate * 100)
        checks.append({
            "key": "path_target_coverage",
            "label": "时间预算内能学到目标知识点",
            "status": "pass" if coverage_rate >= 0.8 else "warn" if coverage_rate >= 0.5 else "fail",
            "value": f"覆盖 {covered}%",
            "detail": "按模拟学生的每周投入，目标知识点都能在计划时间内学到。" if coverage_rate >= 0.8 else "部分目标知识点排在预算之外，需要延长周期或减少目标。",
        })
        time_fit = float(knowledge_full.get("time_fit") or 0)
        checks.append({
            "key": "path_time_fit",
            "label": "计划总时长贴合时间预算",
            "status": "pass" if time_fit >= 0.999 else "warn",
            "value": f"贴合度 {round(time_fit * 100)}%",
            "detail": "路线总时长没有超过预算。" if time_fit >= 0.999 else "路线总时长超过预算，实际学习时可能需要压缩内容。",
        })

    checks.append({
        "key": "quiz_coverage",
        "label": "知识点有测评题",
        "status": "pass" if coverage["with_quiz"] == coverage["nodes"] else "warn",
        "value": f"{coverage['with_quiz']}/{coverage['nodes']} 个",
        "detail": "没有测评题的知识点无法收集掌握度证据，图谱只能保持「未诊断」。" if coverage["with_quiz"] < coverage["nodes"] else "每个知识点都有可用于诊断的题目。",
    })
    return checks


def _grade(score: float) -> str:
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 60:
        return "合格"
    return "待改进"


def _headline(has_graph: bool, structure: dict, edge: dict, coverage: dict) -> str:
    if not has_graph:
        return "当前显示的是专家先修骨架：结构完整，但还没有 AI 生成的描述与关系，也没有收到人工审核记录。"
    parts = [f"图谱包含 {structure['nodes']} 个知识点、{structure['edges']} 条关系"]
    if edge["applicable"]:
        parts.append(
            f"AI 提出 {edge['ai_edges']} 条先修关系，其中 {edge['review']['pending']} 条待审核"
        )
    if coverage["with_quiz"] < coverage["nodes"]:
        parts.append(f"{coverage['nodes'] - coverage['with_quiz']} 个知识点还没有测评题")
    return "；".join(parts) + "。"


def evaluate_knowledge_graph(user_id: int = None, graph: dict = None) -> dict:
    """生成完整的图谱测评报告。

    Args:
        user_id: 当前用户；用于读取课程级图谱（不传时按骨架评估）。
        graph: 直接传入图谱（测试或复用已有对象时使用）。
    """
    expert = agent_course._load_prerequisites()
    if graph is None:
        graph = kg.get_knowledge_graph(user_id) if user_id is not None else None
        has_graph = bool(graph)
        if not graph:
            graph = kg.build_skeleton_graph(agent_course.course_knowledge_points(), expert)
    else:
        has_graph = True

    node_ids = set(_node_index(graph))
    merged_map, added_edges = kg.effective_prerequisite_map(graph, expert)

    structure = _evaluate_structure(graph, expert)
    edge = _evaluate_edge_quality(graph, expert, merged_map)
    impact = _evaluate_path_impact(graph, expert)
    coverage = _evaluate_coverage(graph)
    checks = _build_checks(structure, edge, impact, coverage)

    dimensions = [
        ("structure", "结构健康", 25, structure["score"]),
        ("edge_quality", "边质量", 25, edge["score"]),
        ("path_impact", "路径影响", 30, impact["score"]),
        ("coverage", "证据覆盖", 20, coverage["score"]),
    ]
    applicable = [(weight, score) for _, _, weight, score in dimensions if score is not None]
    weight_sum = sum(weight for weight, _ in applicable) or 1
    total = sum(weight * score for weight, score in applicable) / weight_sum

    recommendations = []
    if structure["has_cycle"]:
        recommendations.append("先修图存在环：先拒绝环上的 AI 边，再重新生成路径。")
    if structure["isolated_nodes"]:
        recommendations.append(f"{len(structure['isolated_nodes'])} 个知识点没有任何关系，建议补充先修或相似关系。")
    if not has_graph or not edge["applicable"]:
        recommendations.append("先生成一次 AI 知识图谱，才能评估 AI 描述与关系质量。")
    if edge["applicable"] and edge["review"]["pending"]:
        recommendations.append(f"{edge['review']['pending']} 条 AI 关系待审核，审核后重新测评会更新边质量。")
    if edge["applicable"] and edge["reversed_conflicts"]:
        recommendations.append(f"{edge['reversed_conflicts']} 条 AI 边方向与专家表相反，建议人工拒绝。")
    gold = edge.get("gold") or {}
    if not gold.get("available"):
        recommendations.append("缺少独立金标准边集，AI 边精确率只能用代理指标；补齐后才能真正对外报告准确率。")
    elif gold.get("status") != "double_annotated":
        recommendations.append("金标准目前只有一位标注者，建议请第二位课程教师独立标注，再计算双人一致性 kappa。")
    if (edge.get("stability") or {}).get("status") != "sampled":
        recommendations.append("同一输入多次生成的稳定性还没抽检；配置 LLM Key 后运行 kg_stability_probe.py 生成快照。")
    if coverage["with_quiz"] < coverage["nodes"]:
        recommendations.append(
            f"{coverage['nodes'] - coverage['with_quiz']} 个知识点缺少测评题，掌握度会长期停留在「未诊断」。"
        )
    if not recommendations:
        recommendations.append("各项指标正常，继续保持对 AI 边的人工审核即可。")

    return {
        "generated_at": datetime.now().isoformat(),
        "graph_version": graph.get("curriculum_version") or kg.GRAPH_VERSION,
        "graph_updated_at": graph.get("updated_at") or graph.get("generated_at"),
        "has_graph": has_graph,
        "generated_by": graph.get("generated_by") or "expert",
        "node_count": len(node_ids),
        "edge_count": len(graph.get("edges") or []),
        "merged_edges": len(added_edges),
        "summary": {
            "score": round(total, 1),
            "grade": _grade(total),
            "headline": _headline(has_graph, structure, edge, coverage),
            "dimensions": [
                {
                    "key": key,
                    "label": label,
                    "weight": weight,
                    "score": score,
                }
                for key, label, weight, score in dimensions
            ],
            "checks": checks,
        },
        "structure": structure,
        "edge_quality": edge,
        "path_impact": impact,
        "coverage": coverage,
        "recommendations": recommendations,
    }
