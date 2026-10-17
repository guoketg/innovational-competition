"""GraphRAG：用课程知识图谱给答疑补充「这个知识点是什么、先学什么、你掌握得怎样」。

设计取舍（不额外调用大模型、零额外费用）：
- 检索不走向量库，而是用图谱节点名 + 课程术语别名做匹配；
- 匹配命中的节点，把定义 / 要点 / 易混对象 / 直接前置 / 学生本人的掌握度
  拼成一段 prompt，注入答疑的 system prompt；
- 同时返回结构化的 references，前端可以显示「参考知识点」，学生能看见
  这条回答到底依据了图谱里的哪些内容。

别名表只覆盖本课程 11 个知识点。图谱节点自身的中文名会动态并入候选，
所以后续新增知识点时，只要名字出现在问题里也能命中。
"""

import re

from services import agent_course, knowledge_graph_service, knowledge_tracking

# 课程术语别名：学生口语里常见的说法 -> 课程知识点 tag。
# 长别名优先匹配，"堆排序" 不会被 "堆" 抢先命中。
_ALIASES = {
    "dsa-dsa-linear-data-structures": [
        "线性结构", "线性表", "顺序表", "数组", "动态数组", "链表", "单链表",
        "双向链表", "循环链表", "栈", "队列", "stack", "queue", "linked list",
    ],
    "dsa-binary-search-tree-insert": [
        "二分搜索树", "二叉搜索树", "二叉查找树", "排序二叉树", "bst",
        "bst插入", "bst查找", "树的插入", "树的查找",
    ],
    "dsa-binary-search-traverse": [
        "中序遍历", "层序遍历", "层次遍历", "二叉树遍历", "前序遍历", "后序遍历",
        "inorder", "level order",
    ],
    "dsa-heap-shift-up": [
        "堆", "二叉堆", "优先队列", "上浮", "下沉", "大根堆", "小根堆", "heapify",
        "priority queue",
    ],
    "dsa-heap-sort": [
        "堆排序", "heapsort", "heap sort", "建堆",
    ],
    "dsa-graph-theory-deep": [
        "图的表示", "邻接表", "邻接矩阵", "深度优先", "深度优先遍历", "dfs",
        "图的遍历", "递归遍历图",
    ],
    "dsa-union-find-compress": [
        "并查集", "路径压缩", "按秩合并", "按大小合并", "连通分量", "union find",
        "disjoint set",
    ],
    "dsa-graph-theory-short-path": [
        "广度优先", "广度优先遍历", "bfs", "最短路径", "dijkstra", "无权图最短路",
        "队列实现bfs",
    ],
    "dsa-dsa-basic-algorithm": [
        "算法工具箱", "统一入口", "算法入口", "算法分发", "分发器", "算法调度",
    ],
    "dsa-merge-sort": [
        "归并排序", "归并", "分治", "merge sort", "合并有序数组", "性能基准",
        "排序性能",
    ],
    "dsa-dsa-hash-table": [
        "哈希表", "散列表", "哈希函数", "散列函数", "哈希冲突", "冲突处理",
        "拉链法", "开放寻址", "lru", "lru缓存", "缓存淘汰", "hash table", "hashmap",
    ],
}

# 单字/两字别名容易误伤，给一个较低的命中分；越长的别名越可信。
_MIN_ALIAS_LENGTH = 1
_MIN_SCORE = 0.45


def _graph_nodes(graph: dict | None) -> list:
    return [n for n in ((graph or {}).get("nodes") or []) if n.get("tag")]


def _fallback_graph() -> dict:
    """没有 AI 图谱时用「专家先修骨架」，保证 GraphRAG 仍能工作。"""
    return knowledge_graph_service.build_skeleton_graph(
        agent_course.course_knowledge_points(),
        agent_course._load_prerequisites(),
    )


def _load_graph(user_id: int | None) -> tuple:
    """读取图谱：课程级 AI 图谱 > 用户图谱 > 专家骨架。"""
    graph = None
    if user_id is not None:
        try:
            graph = knowledge_graph_service.get_knowledge_graph(user_id)
        except Exception:
            graph = None
    if graph and _graph_nodes(graph):
        return graph, graph.get("generated_by") or "llm"
    return _fallback_graph(), "expert"


def _alias_candidates(graph: dict | None) -> list:
    """(alias, tag, base_score) 列表：静态别名 + 图谱节点名 + 节点名里的短语。"""
    pairs = []
    seen = set()

    def add(alias: str, tag: str, base: float):
        text = str(alias or "").strip().lower()
        if len(text) < _MIN_ALIAS_LENGTH or (text, tag) in seen:
            return
        seen.add((text, tag))
        pairs.append((text, tag, base))

    for tag, aliases in _ALIASES.items():
        for alias in aliases:
            add(alias, tag, 1.0 if len(alias) >= 4 else 0.7 if len(alias) >= 2 else _MIN_SCORE)

    for node in _graph_nodes(graph):
        tag = node["tag"]
        name = str(node.get("name") or "").strip()
        if not name:
            continue
        add(name, tag, 1.0)
        # 「二分搜索树：插入与查找」这类名字，拆成可单独命中的短语
        for part in re.split(r"[：:/｜|、，,（）()]|与|和", name):
            part = part.strip()
            if len(part) >= 2:
                add(part, tag, 0.9)
    return pairs


def _match_spans(text: str, candidates: list) -> list:
    """找出所有别名出现位置，长别名占位优先，避免「堆排序」又被「堆」算一次。"""
    lower = text.lower()
    spans = []
    for alias, tag, base in candidates:
        start = lower.find(alias)
        while start != -1:
            spans.append({
                "start": start,
                "end": start + len(alias),
                "alias": alias,
                "tag": tag,
                "score": base,
            })
            start = lower.find(alias, start + 1)

    # 长别名优先占位；相同跨度时保留分数高的
    spans.sort(key=lambda item: (-(item["end"] - item["start"]), -item["score"], item["start"]))
    occupied = [False] * len(text)
    kept = []
    for span in spans:
        if any(occupied[span["start"]:span["end"]]):
            continue
        for index in range(span["start"], span["end"]):
            occupied[index] = True
        kept.append(span)
    return kept


def match_nodes(question: str, limit: int = 3, graph: dict | None = None) -> list:
    """按问题文本匹配图谱节点，返回 [{tag, name, matched_alias, score}]。"""
    text = str(question or "").strip()
    if not text:
        return []
    graph = graph or _fallback_graph()
    names = knowledge_graph_service.node_name_index(graph)
    candidates = _alias_candidates(graph)

    hits = {}
    for span in _match_spans(text, candidates):
        bucket = hits.setdefault(span["tag"], {
            "tag": span["tag"],
            "name": names.get(span["tag"], span["tag"]),
            "matched_alias": span["alias"],
            "score": span["score"],
            "hits": 0,
        })
        bucket["hits"] += 1
        if span["score"] > bucket["score"]:
            bucket["score"] = span["score"]
            bucket["matched_alias"] = span["alias"]

    ranked = sorted(
        hits.values(),
        key=lambda item: (-item["score"], -item["hits"], item["name"]),
    )
    for item in ranked:
        # 同一知识点被多个别名命中，说明问题确实在谈它
        item["score"] = round(min(1.0, item["score"] + 0.05 * (item["hits"] - 1)), 2)
    return ranked[:max(1, limit)]


def _prerequisite_chain(tag: str, prereq_map: dict, names: dict, depth: int = 1) -> list:
    """直接前置（默认只看一层），用于提示「先补什么」。"""
    result = []
    for parent in (prereq_map.get(tag) or [])[:4]:
        result.append({"tag": parent, "name": names.get(parent, parent)})
        if depth > 1:
            for item in _prerequisite_chain(parent, prereq_map, names, depth - 1):
                if all(existing["tag"] != item["tag"] for existing in result):
                    result.append(item)
    return result


def _format_mastery(profile: dict | None) -> str:
    if not profile or profile.get("score") is None:
        return "还没有练习证据"
    text = f"{round(float(profile['score']) * 100)}%"
    if profile.get("confidence_label"):
        text += f"（证据 {profile.get('evidence_count') or 0} 次，{profile['confidence_label']}）"
    return text


def build_graph_context(user_id: int | None, question: str, limit: int = 3,
                        graph: dict | None = None) -> dict:
    """构造 GraphRAG 上下文。

    返回 {available, prompt, references, graph_version, graph_source}：
      - prompt：直接拼到答疑 system prompt 后面；
      - references：前端「参考知识点」卡片用的结构化数据。
    """
    graph, source = (graph, graph.get("generated_by") or "llm") if graph else _load_graph(user_id)
    matches = match_nodes(question, limit=limit, graph=graph)
    if not matches:
        return {
            "available": False,
            "prompt": "",
            "references": [],
            "graph_version": graph.get("curriculum_version"),
            "graph_source": source,
        }

    nodes = {node["tag"]: node for node in _graph_nodes(graph)}
    names = knowledge_graph_service.node_name_index(graph)
    prereq_map, _added = knowledge_graph_service.effective_prerequisite_map(
        graph, agent_course._load_prerequisites()
    )
    similar = knowledge_graph_service.similar_index(graph)
    profiles = {}
    if user_id is not None:
        try:
            profiles = knowledge_tracking.mastery_detail_by_knowledge(user_id)
        except Exception:
            profiles = {}

    references = []
    lines = []
    for index, match in enumerate(matches, start=1):
        tag = match["tag"]
        node = nodes.get(tag) or {}
        profile = profiles.get(tag) or {}
        definition = str(node.get("definition") or "").strip()
        key_points = [str(p).strip() for p in (node.get("key_points") or []) if str(p).strip()][:4]
        confusable = [
            {"tag": item["tag"], "name": item["name"]}
            for item in (similar.get(tag) or [])
            if item.get("tag") in names
        ][:3]
        prerequisites = _prerequisite_chain(tag, prereq_map, names)
        mastery_text = _format_mastery(profile)

        block = [f"{index}. {match['name']}（命中词：{match['matched_alias']}）"]
        if definition:
            block.append(f"   定义：{definition}")
        if key_points:
            block.append(f"   要点：{'；'.join(key_points)}")
        if confusable:
            block.append(f"   易混：{'、'.join(item['name'] for item in confusable)}")
        if prerequisites:
            block.append(f"   直接前置：{'、'.join(item['name'] for item in prerequisites)}")
        block.append(f"   该生掌握度：{mastery_text}")
        lines.append("\n".join(block))

        references.append({
            "tag": tag,
            "name": match["name"],
            "matched_alias": match["matched_alias"],
            "score": match["score"],
            "definition": definition,
            "key_points": key_points,
            "confusable": confusable,
            "prerequisites": prerequisites,
            "mastery": profile.get("score"),
            "mastery_confidence": profile.get("confidence"),
            "mastery_confidence_label": profile.get("confidence_label"),
            "mastery_evidence": profile.get("evidence_count"),
        })

    prompt = (
        "【知识图谱参考（课程图谱检索结果，优先按这里的概念口径作答）】\n"
        + "\n".join(lines)
        + "\n回答要求：\n"
        "1. 术语含义与上面的定义保持一致；讲算法时覆盖对应要点，不要只给结论；\n"
        "2. 若学生的前置知识点掌握度偏低（低于 60%），先用一两句话补前置，再讲当前问题；\n"
        "3. 不要主动罗列这张表，也不要提到「图谱」这个词；只在必要处自然融入。"
    )
    return {
        "available": True,
        "prompt": prompt,
        "references": references,
        "graph_version": graph.get("curriculum_version"),
        "graph_source": source,
    }


def identify_tags(text: str, limit: int = 3) -> list:
    """用图谱匹配识别问题涉及的知识点 tag；没命中返回空列表。"""
    try:
        return [item["tag"] for item in match_nodes(text, limit=limit)]
    except Exception:
        return []


def graph_reference_brief(references: list) -> list:
    """给前端/会话元数据用的精简结构，避免把长文本反复存储。"""
    brief = []
    for item in references or []:
        brief.append({
            "tag": item.get("tag"),
            "name": item.get("name"),
            "matched_alias": item.get("matched_alias"),
            "definition": item.get("definition") or "",
            "key_points": (item.get("key_points") or [])[:3],
            "confusable": [entry.get("name") for entry in item.get("confusable") or []],
            "prerequisites": [entry.get("name") for entry in item.get("prerequisites") or []],
            "mastery": item.get("mastery"),
            "mastery_confidence_label": item.get("mastery_confidence_label"),
            "mastery_evidence": item.get("mastery_evidence"),
        })
    return brief
