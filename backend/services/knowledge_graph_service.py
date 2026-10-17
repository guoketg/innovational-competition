"""知识图谱构建服务（课程级 · 可审核 · 可解释）

构建流程：
  1. 输入是课程级知识点清单（agent_course.COURSE_KNOWLEDGE_POINTS），与具体用户无关；
  2. LLM 第一步为每个知识点生成描述（定义 / 要点 / 易混对象）；
  3. LLM 第二步在描述（含要点与易混对象）基础上判定先修 / 相似关系，
     并为每条关系给出置信度与判断依据；
  4. 与专家先修表（data/dsa_prerequisites.json）合并：专家边权威且置信度为 1；
     AI 边按置信度分为 accepted / pending / rejected，低置信边保留可见但不参与编排；
  5. 确定性校验：未知节点、自环、重复、会让先修图成环的边全部记录为 discarded。

图谱按课程只存一份（curriculum_version = GRAPH_VERSION），避免每个用户重复调用 LLM、
也避免不同用户看到互相矛盾的 AI 边。用户对边的采纳/拒绝直接写回这份课程图谱。
"""
import json
import logging
import os
from datetime import datetime

from database import get_db
from services.ai_service import call_llm, extract_json, extract_json_object

logger = logging.getLogger(__name__)

GRAPH_VERSION = "dsa-kg-llm-v3"

# 课程参数化：默认课程固定为数据结构与算法（DSA）。
# 新增课程时只需在这里登记课程 → 图谱版本，读写与查询接口都会自动按课程取图，
# 不需要再改 service 里的 SQL 或路由。
DEFAULT_COURSE = os.getenv("KG_DEFAULT_COURSE", "dsa")
COURSE_REGISTRY = {
    "dsa": {
        "label": "数据结构与算法",
        "curriculum_version": GRAPH_VERSION,
    },
}

# 版本快照最多保留多少份（超出后删最旧的）
GRAPH_VERSION_RETENTION = int(os.getenv("KG_VERSION_RETENTION", "30"))

REL_PREREQUISITE = "prerequisite"
REL_SIMILAR = "similar"
REL_PART_OF = "part-of"

REVIEW_ACCEPTED = "accepted"
REVIEW_PENDING = "pending"
REVIEW_REJECTED = "rejected"

_LLM_ERROR_PREFIX = "LLM调用异常"

# 边置信度分档：≥ACCEPT 直接参与编排；PENDING~ACCEPT 待人工确认；<PENDING 视为不可用。
CONFIDENCE_ACCEPT = float(os.getenv("KG_EDGE_ACCEPT_CONFIDENCE", "0.75"))
CONFIDENCE_PENDING = float(os.getenv("KG_EDGE_PENDING_CONFIDENCE", "0.5"))

# 掌握度时间衰减：超过 STALE_DAYS 天没有新证据后，向 0.5 回落，DECAY_DAYS 天后完全中性。
STALE_DAYS = int(os.getenv("KG_MASTERY_STALE_DAYS", "30"))
DECAY_DAYS = int(os.getenv("KG_MASTERY_DECAY_DAYS", "30"))

DEFAULT_MASTERY_LOW = float(os.getenv("KG_MASTERY_LOW", "0.4"))
DEFAULT_MASTERY_HIGH = float(os.getenv("KG_MASTERY_HIGH", "0.7"))
UNDIAGNOSED_SCORE = float(os.getenv("KG_UNDIAGNOSED_SCORE", "0.6"))


def _normalize_nodes(nodes: list) -> list:
    """规整入参：补齐 tag/name 并按 tag 去重，其余属性（难度、认知层次等）原样保留。"""
    seen = {}
    for node in nodes or []:
        node = node or {}
        tag = str(node.get("tag") or "").strip()
        if not tag or tag in seen:
            continue
        item = {str(key): value for key, value in node.items()}
        item["tag"] = tag
        item["name"] = str(node.get("name") or tag).strip()
        seen[tag] = item
    return list(seen.values())


def _has_cycle(edges: list, node_ids: set) -> bool:
    """判断「先修」边构成的有向图是否有环。"""
    adjacency = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if edge.get("relation") != REL_PREREQUISITE:
            continue
        source, target = edge.get("source"), edge.get("target")
        if source in adjacency and target in adjacency:
            adjacency[source].append(target)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node_id: WHITE for node_id in node_ids}

    def visit(node_id: str) -> bool:
        color[node_id] = GRAY
        for nxt in adjacency[node_id]:
            if color[nxt] == GRAY:
                return True
            if color[nxt] == WHITE and visit(nxt):
                return True
        color[node_id] = BLACK
        return False

    return any(color[node_id] == WHITE and visit(node_id) for node_id in node_ids)


def _confidence(value, default: float = 0.6) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.0, min(1.0, number)), 2)


def _review_status(confidence: float) -> str:
    """置信度分档：高置信直接采纳，中置信待审核，低置信拒绝。"""
    if confidence >= CONFIDENCE_ACCEPT:
        return REVIEW_ACCEPTED
    if confidence >= CONFIDENCE_PENDING:
        return REVIEW_PENDING
    return REVIEW_REJECTED


def _expert_edges(expert_prereq: dict, node_ids: set) -> list:
    """把专家先修表（tag -> 直接前置列表）展开成边，方向：前置 → 后继。"""
    edges = []
    for tag, parents in (expert_prereq or {}).items():
        if tag not in node_ids:
            continue
        for parent in parents or []:
            if parent not in node_ids or parent == tag:
                continue
            edges.append({
                "source": parent,
                "target": tag,
                "relation": REL_PREREQUISITE,
                "reason": "课程先修表（专家维护）",
                "origin": "expert",
                "confidence": 1.0,
                "evidence": "课程先修表（专家维护）",
                "review_status": REVIEW_ACCEPTED,
            })
    return edges


def _part_of_edges(node_ids: set) -> list:
    """课程目录的包含关系边（父 → 子），与先修关系严格分开，不参与成环检测。"""
    from services import agent_course

    edges = []
    for edge in agent_course.part_of_edges():
        if edge["source"] in node_ids and edge["target"] in node_ids:
            edges.append(dict(edge))
    return edges


def _merge_llm_edges(llm_edges: list, accepted: list, node_ids: set) -> tuple:
    """把 LLM 给出的边并入。

    返回 (kept, discarded)：
      - kept：结构合法、字段完整的边（含低置信边，review_status 标明是否参与编排）；
      - discarded：未知节点 / 自环 / 重复 / 成环等被剔除的边，附 reason 供前端追溯。
    """
    existing_pairs = {(e["source"], e["target"]) for e in accepted}
    kept, discarded = [], []

    def discard(source, target, relation, reason):
        discarded.append({
            "source": source or "",
            "target": target or "",
            "relation": relation,
            "reason": reason,
        })

    for edge in llm_edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation = REL_SIMILAR if edge.get("relation") == REL_SIMILAR else REL_PREREQUISITE
        if not source or not target:
            discard(source, target, relation, "缺少起点或终点")
            continue
        if source == target:
            discard(source, target, relation, "自环")
            continue
        if source not in node_ids or target not in node_ids:
            discard(source, target, relation, "节点不在课程知识点名单内")
            continue
        if (source, target) in existing_pairs or (
            relation == REL_SIMILAR and (target, source) in existing_pairs
        ):
            discard(source, target, relation, "与已有关系重复")
            continue

        confidence = _confidence(edge.get("confidence"))
        status = _review_status(confidence)
        candidate = {
            "source": source,
            "target": target,
            "relation": relation,
            "reason": str(edge.get("reason") or "").strip()[:60],
            "origin": "llm",
            "confidence": confidence,
            "evidence": str(edge.get("evidence") or "").strip()[:80],
            "review_status": status,
        }
        if relation == REL_PREREQUISITE and status == REVIEW_ACCEPTED:
            # 只有真正参与编排的高置信边才需要保证不成环
            if _has_cycle([*accepted, *kept, candidate], node_ids):
                discard(source, target, relation, "会让先修关系成环")
                continue
        existing_pairs.add((source, target))
        kept.append(candidate)
    return kept, discarded


async def _llm_descriptions(user_id: int, nodes: list) -> list:
    """第一步：让 LLM 为每个知识点生成结构化描述（对标 EDU-GraphRAG 的描述生成）。"""
    listing = json.dumps(nodes, ensure_ascii=False)
    prompt = (
        "下面是《数据结构与算法》课程的知识点名单（tag 为唯一标识）：\n"
        f"{listing}\n\n"
        "请为每个知识点输出一条结构化描述，返回 JSON 数组，元素格式：\n"
        '{"tag": "与输入完全一致的 tag", "definition": "一句话定义，40 字内", '
        '"key_points": ["要点1", "要点2", "要点3"], '
        '"confusable": ["最容易与它混淆的其他知识点 tag"], '
        '"misconceptions": ["学生最常见的错误理解，20 字内，最多 2 条"]}\n'
        "要求：confusable 只能取自上面的 tag，没有就给空数组；禁止编造名单外的知识点。"
    )
    text = await call_llm(
        user_id,
        [
            {"role": "system", "content": "你是数据结构与算法课程的知识点建模专家，只输出 JSON，不要任何解释。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    if text.startswith(_LLM_ERROR_PREFIX):
        raise RuntimeError(text)
    return extract_json(text)


async def _llm_relations(user_id: int, nodes: list, expert_prereq: dict) -> dict:
    """第二步：在描述（含要点与易混对象）基础上判定先修 / 相似两类关系。

    与第一步串接：把 key_points / confusable 一起喂给模型，避免两阶段各说各话。
    """
    listing = json.dumps(
        [
            {
                "tag": n["tag"],
                "name": n["name"],
                "definition": n.get("definition", ""),
                "key_points": n.get("key_points") or [],
                "confusable": n.get("confusable") or [],
            }
            for n in nodes
        ],
        ensure_ascii=False,
    )
    known = json.dumps(
        [[p, t] for t, parents in (expert_prereq or {}).items() for p in (parents or [])],
        ensure_ascii=False,
    )
    prompt = (
        f"知识点名单与描述：\n{listing}\n\n"
        f"已知的专家先修关系（[[先修 tag, 后继 tag]]，权威，不要重复输出）：{known}\n\n"
        "请判断两类关系并返回 JSON 对象：\n"
        '{"prerequisite": [{"source": "先修知识点 tag", "target": "后继知识点 tag", '
        '"reason": "20 字内理由", "confidence": 0.0到1.0, "evidence": "30 字内的具体判断依据"}], '
        '"similar": [{"source": "tag", "target": "tag", "reason": "20 字内理由", "confidence": 0.0到1.0}]}\n'
        "规则：\n"
        "1. prerequisite 有方向：source 必须先于 target 学习；只补专家表未覆盖的缺失关系，禁止输出与专家表重复或相反的边；\n"
        "2. similar 无方向，表示概念相近、容易混淆、适合放在一起对比学习的一对知识点；\n"
        "3. confidence 表示你对这条关系的把握：有明确课程先后依据给 0.8 以上，"
        "只是教学经验推测给 0.5~0.7，不确定给 0.5 以下；evidence 必须引用上面的要点或易混对象，不能空泛；\n"
        "4. 只能使用名单内的 tag，禁止编造，禁止自环。"
    )
    text = await call_llm(
        user_id,
        [
            {"role": "system", "content": "你是数据结构与算法课程的课程专家，只输出 JSON，不要任何解释。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    if text.startswith(_LLM_ERROR_PREFIX):
        raise RuntimeError(text)
    return extract_json_object(text)


def _merge_descriptions(nodes: list, descriptions: list) -> list:
    """把 LLM 描述贴回节点，缺失的用占位描述兜底。"""
    by_tag = {
        str(item.get("tag") or "").strip(): item
        for item in descriptions
        if isinstance(item, dict)
    }
    merged = []
    for node in nodes:
        item = by_tag.get(node["tag"]) or {}
        key_points = [str(p).strip() for p in (item.get("key_points") or []) if str(p).strip()][:4]
        confusable = [
            str(t).strip() for t in (item.get("confusable") or [])
            if str(t).strip() and str(t).strip() != node["tag"]
        ]
        # 静态属性里的迷思概念是课程团队维护的权威版本，LLM 结果只做补充。
        misconceptions = [
            str(m).strip() for m in (node.get("misconceptions") or []) if str(m).strip()
        ]
        for value in item.get("misconceptions") or []:
            text = str(value).strip()
            if text and text not in misconceptions:
                misconceptions.append(text)
        merged.append({
            **node,
            "definition": str(item.get("definition") or "").strip()[:80],
            "key_points": key_points,
            "confusable": confusable,
            "misconceptions": misconceptions[:4],
        })
    return merged


def resolve_curriculum_version(course: str | None = None) -> str:
    """把课程名解析成图谱版本号；不传则用默认课程。

    已登记的课程按注册表映射；未登记的字符串按版本号原样使用（便于未来接入外部课程）。
    """
    key = (course or DEFAULT_COURSE or "").strip()
    if not key:
        return GRAPH_VERSION
    entry = COURSE_REGISTRY.get(key.lower())
    if entry:
        return entry["curriculum_version"]
    return key


def course_options() -> list:
    """可选课程清单，供前端下拉框展示。"""
    return [
        {"course": key, "label": value["label"], "curriculum_version": value["curriculum_version"]}
        for key, value in COURSE_REGISTRY.items()
    ]


def _ensure_version_table(conn) -> bool:
    """确保版本表存在（新环境或还没执行建表脚本时兜底）。"""
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS knowledge_graph_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id INTEGER,
                curriculum_version TEXT DEFAULT '',
                version INTEGER NOT NULL,
                change_type TEXT DEFAULT 'save',
                change_note TEXT DEFAULT '',
                created_by INTEGER,
                node_count INTEGER DEFAULT 0,
                edge_count INTEGER DEFAULT 0,
                payload TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        return True
    except Exception as exc:  # 权限不足等情况下不影响主流程
        logger.warning("[KG] 版本表不可用，本次不记录快照: %s", exc)
        return False


def _save_graph_version(conn, graph: dict, graph_id, curriculum_version: str,
                        change_type: str, change_note: str, created_by) -> None:
    """写一份整图快照，并只保留最近 GRAPH_VERSION_RETENTION 份。"""
    payload = json.dumps(graph, ensure_ascii=False)
    row = conn.execute(
        """SELECT MAX(version) AS max_version FROM knowledge_graph_versions
           WHERE curriculum_version = ?""",
        (curriculum_version,),
    ).fetchone()
    max_version = (row["max_version"] if row else None) or 0
    conn.execute(
        """INSERT INTO knowledge_graph_versions
           (graph_id, curriculum_version, version, change_type, change_note,
            created_by, node_count, edge_count, payload, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            graph_id, curriculum_version, int(max_version) + 1, change_type,
            change_note, created_by,
            int((graph.get("stats") or {}).get("nodes") or len(graph.get("nodes") or [])),
            int((graph.get("stats") or {}).get("edges") or len(graph.get("edges") or [])),
            payload, datetime.now().isoformat(),
        ),
    )
    rows = conn.execute(
        """SELECT id FROM knowledge_graph_versions
           WHERE curriculum_version = ? ORDER BY version DESC LIMIT ?""",
        (curriculum_version, GRAPH_VERSION_RETENTION),
    ).fetchall()
    keep = [int(item["id"]) for item in rows or []]
    if keep:
        placeholders = ", ".join("?" for _ in keep)
        conn.execute(
            f"""DELETE FROM knowledge_graph_versions
                WHERE curriculum_version = ? AND id NOT IN ({placeholders})""",
            (curriculum_version, *keep),
        )


def _persist(user_id: int, graph: dict, curriculum_version: str = None,
             change_type: str = "save", change_note: str = "",
             snapshot: bool = True) -> None:
    """课程级持久化：同一课程只保留一份图谱，后生成者覆盖先生成者。

    user_id 只作为「最后生成者」记录，用于满足表约束；读取时按课程版本取最新一份。
    每次写入同时留一份版本快照（可回滚），change_type 说明这次是生成 / 审核 / 回滚。
    """
    version = curriculum_version or graph.get("curriculum_version") or GRAPH_VERSION
    conn = get_db()
    graph_id = None
    try:
        graph["scope"] = "course"
        graph["curriculum_version"] = version
        now = datetime.now().isoformat()
        graph["updated_at"] = now
        row = conn.execute(
            """SELECT id FROM knowledge_graphs
               WHERE curriculum_version = ?
               ORDER BY updated_at DESC LIMIT 1""",
            (version,),
        ).fetchone()
        node_count = int((graph.get("stats") or {}).get("nodes") or len(graph.get("nodes") or []))
        edge_count = int((graph.get("stats") or {}).get("edges") or len(graph.get("edges") or []))
        if row:
            graph_id = int(row["id"])
            conn.execute(
                """UPDATE knowledge_graphs
                   SET payload = ?, node_count = ?, edge_count = ?, updated_at = ?
                   WHERE id = ?""",
                (json.dumps(graph, ensure_ascii=False), node_count, edge_count, now, graph_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO knowledge_graphs
                   (user_id, curriculum_version, payload, node_count, edge_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, version, json.dumps(graph, ensure_ascii=False),
                 node_count, edge_count, now, now),
            )
            graph_id = getattr(cursor, "lastrowid", None)
        if snapshot and _ensure_version_table(conn):
            _save_graph_version(
                conn, graph, graph_id, version,
                change_type=change_type,
                change_note=change_note,
                created_by=user_id,
            )
        conn.commit()
    finally:
        conn.close()


def _load_graph_row(where: str, params: tuple) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            f"""SELECT payload, updated_at FROM knowledge_graphs
                WHERE {where}
                ORDER BY updated_at DESC LIMIT 1""",
            params,
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        graph = json.loads(row["payload"] or "{}")
    except Exception:
        return None
    graph["updated_at"] = row["updated_at"]
    return graph


def get_course_graph(curriculum_version: str = None) -> dict | None:
    """读取课程级图谱（同课程所有用户共用一份）。"""
    version = curriculum_version or GRAPH_VERSION
    return _load_graph_row("curriculum_version = ?", (version,))


def get_knowledge_graph(user_id: int, curriculum_version: str = None) -> dict | None:
    """读取知识图谱：优先课程级图谱；没有再读当前用户自己生成的同版本图谱。"""
    version = curriculum_version or GRAPH_VERSION
    graph = get_course_graph(version)
    if graph:
        return graph
    return _load_graph_row(
        "user_id = ? AND curriculum_version = ?", (user_id, version)
    )


# ── 图查询：N 跳邻居 / 两节点间最短路径 ──────────────────────────────────

_CHANGE_TYPE_LABELS = {
    "generate": "AI 重新生成",
    "review": "人工审核关系",
    "restore": "回滚到旧版本",
    "save": "图谱保存",
}


def _nodes_of(graph: dict | None) -> dict:
    return {
        str(node.get("tag") or "").strip(): node
        for node in ((graph or {}).get("nodes") or [])
        if node.get("tag")
    }


def _build_adjacency(graph: dict | None, relations: set | None = None) -> tuple:
    """构建正向/反向邻接表：{(from, to): edge}，按关系类型过滤。"""
    out_adj, in_adj = {}, {}
    for edge in (graph or {}).get("edges") or []:
        relation = edge.get("relation") or REL_PREREQUISITE
        if relations and relation not in relations:
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        out_adj.setdefault(source, []).append((target, edge))
        in_adj.setdefault(target, []).append((source, edge))
    return out_adj, in_adj


def resolve_node(graph: dict | None, ref: str) -> str | None:
    """把用户输入的 tag / 名称解析成节点 tag；找不到返回 None。"""
    text = str(ref or "").strip()
    if not text:
        return None
    nodes = _nodes_of(graph)
    if text in nodes:
        return text
    for tag, node in nodes.items():
        if str(node.get("name") or "").strip() == text:
            return tag
    lowered = text.lower()
    for tag, node in nodes.items():
        if str(node.get("name") or "").strip().lower() == lowered:
            return tag
    matches = [
        tag for tag, node in nodes.items()
        if lowered in str(node.get("name") or "").lower()
    ]
    return matches[0] if len(matches) == 1 else None


def _node_brief(node: dict | None, tag: str) -> dict:
    node = node or {}
    return {
        "tag": tag,
        "name": node.get("name") or tag,
        "module": node.get("module") or "",
    }


def _edge_brief(edge: dict) -> dict:
    return {
        "source": edge.get("source"),
        "target": edge.get("target"),
        "relation": edge.get("relation") or REL_PREREQUISITE,
        "origin": edge.get("origin") or "expert",
        "confidence": edge.get("confidence"),
        "review_status": edge.get("review_status"),
        "reason": edge.get("reason") or "",
    }


def query_neighbors(graph: dict | None, ref: str, hops: int = 1,
                    direction: str = "both", relations: list | None = None) -> dict:
    """查询某个节点的 N 跳邻居（BFS）。

    direction: out（沿箭头）/ in（逆箭头）/ both（双向）。
    返回每层邻居与命中的边，前端可以按层高亮。
    """
    nodes = _nodes_of(graph)
    start = resolve_node(graph, ref)
    if not start:
        raise ValueError(f"图谱里找不到节点「{ref}」")
    hops = max(1, min(int(hops or 1), 5))
    relation_set = {item for item in (relations or []) if item} or None
    out_adj, in_adj = _build_adjacency(graph, relation_set)

    visited = {start: 0}
    frontier = [start]
    neighbors = []
    edges = []
    seen_edges = set()
    for depth in range(1, hops + 1):
        next_frontier = []
        for current in frontier:
            candidates = []
            if direction in ("out", "both"):
                candidates.extend((target, edge, "out") for target, edge in out_adj.get(current, []))
            if direction in ("in", "both"):
                candidates.extend((target, edge, "in") for target, edge in in_adj.get(current, []))
            for neighbor, edge, edge_direction in candidates:
                if neighbor not in nodes:
                    continue
                if neighbor in visited and visited[neighbor] <= depth:
                    continue
                visited[neighbor] = depth
                next_frontier.append(neighbor)
                neighbors.append({
                    **_node_brief(nodes.get(neighbor), neighbor),
                    "hop": depth,
                    "direction": edge_direction,
                    "via": _node_brief(nodes.get(current), current),
                    "edge": _edge_brief(edge),
                })
                key = (edge.get("source"), edge.get("target"), edge.get("relation"))
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append(_edge_brief(edge))
        frontier = next_frontier
        if not frontier:
            break

    groups = {}
    for item in neighbors:
        groups.setdefault(str(item["hop"]), []).append(item)
    return {
        "node": _node_brief(nodes.get(start), start),
        "hops": hops,
        "direction": direction if direction in ("out", "in", "both") else "both",
        "relations": sorted(relation_set) if relation_set else sorted({REL_PREREQUISITE, REL_SIMILAR, REL_PART_OF}),
        "neighbor_count": len(neighbors),
        "neighbors": neighbors,
        "groups": groups,
        "edges": edges,
    }


def query_path(graph: dict | None, source_ref: str, target_ref: str,
               direction: str = "both", relations: list | None = None,
               max_hops: int = 8) -> dict:
    """查询两个节点之间的最短路径（BFS）。

    direction=both 时不看箭头方向，只回答「两点之间怎么连起来」；
    direction=out 时只沿先修箭头走（source 是更基础的一侧）。
    """
    nodes = _nodes_of(graph)
    source = resolve_node(graph, source_ref)
    target = resolve_node(graph, target_ref)
    if not source:
        raise ValueError(f"图谱里找不到节点「{source_ref}」")
    if not target:
        raise ValueError(f"图谱里找不到节点「{target_ref}」")
    relation_set = {item for item in (relations or []) if item} or None
    out_adj, in_adj = _build_adjacency(graph, relation_set)
    max_hops = max(1, min(int(max_hops or 8), 20))

    if source == target:
        return {
            "found": True, "distance": 0, "direction": direction,
            "source": _node_brief(nodes.get(source), source),
            "target": _node_brief(nodes.get(target), target),
            "nodes": [_node_brief(nodes.get(source), source)],
            "steps": [],
        }

    # BFS 记录父节点与经过的边
    parent = {source: None}
    frontier = [source]
    found = False
    for _ in range(max_hops):
        next_frontier = []
        for current in frontier:
            candidates = []
            if direction in ("out", "both"):
                candidates.extend((nxt, edge, "out") for nxt, edge in out_adj.get(current, []))
            if direction in ("in", "both"):
                candidates.extend((nxt, edge, "in") for nxt, edge in in_adj.get(current, []))
            for neighbor, edge, edge_direction in candidates:
                if neighbor in parent or neighbor not in nodes:
                    continue
                parent[neighbor] = (current, edge, edge_direction)
                if neighbor == target:
                    found = True
                    break
                next_frontier.append(neighbor)
            if found:
                break
        if found or not next_frontier:
            break
        frontier = next_frontier

    if not found:
        return {
            "found": False, "distance": None, "direction": direction,
            "source": _node_brief(nodes.get(source), source),
            "target": _node_brief(nodes.get(target), target),
            "nodes": [], "steps": [],
            "message": f"在 {max_hops} 跳以内没有找到这两个知识点之间的路径",
        }

    chain = [target]
    steps = []
    cursor = target
    while parent.get(cursor):
        previous, edge, edge_direction = parent[cursor]
        steps.append({
            "from": _node_brief(nodes.get(previous), previous),
            "to": _node_brief(nodes.get(cursor), cursor),
            "direction": edge_direction,
            "edge": _edge_brief(edge),
        })
        chain.append(previous)
        cursor = previous
    chain.reverse()
    steps.reverse()
    return {
        "found": True,
        "distance": len(steps),
        "direction": direction,
        "source": _node_brief(nodes.get(source), source),
        "target": _node_brief(nodes.get(target), target),
        "nodes": [_node_brief(nodes.get(tag), tag) for tag in chain],
        "steps": steps,
    }


def list_graph_versions(curriculum_version: str = None, limit: int = 20) -> dict:
    """列出版本快照（不含整图内容，列表接口保持轻量）。"""
    version = curriculum_version or GRAPH_VERSION
    limit = max(1, min(int(limit or 20), 100))
    conn = get_db()
    try:
        _ensure_version_table(conn)
        rows = conn.execute(
            """SELECT id, version, change_type, change_note, created_by,
                      node_count, edge_count, created_at
               FROM knowledge_graph_versions
               WHERE curriculum_version = ?
               ORDER BY version DESC LIMIT ?""",
            (version, limit),
        ).fetchall()
        conn.commit()
    finally:
        conn.close()
    items = []
    max_version = int(rows[0]["version"]) if rows else None
    for row in rows or []:
        change_type = row["change_type"] or "save"
        items.append({
            "id": int(row["id"]),
            "version": int(row["version"]),
            "change_type": change_type,
            "change_type_label": _CHANGE_TYPE_LABELS.get(change_type, change_type),
            "change_note": row["change_note"] or "",
            "created_by": row["created_by"],
            "node_count": row["node_count"],
            "edge_count": row["edge_count"],
            "created_at": row["created_at"],
            "is_current": max_version is not None and int(row["version"]) == max_version,
        })
    return {
        "curriculum_version": version,
        "total": len(items),
        "retention": GRAPH_VERSION_RETENTION,
        "versions": items,
    }


def restore_graph_version(user_id: int, version_id: int, note: str = "") -> dict:
    """把图谱回滚到某个快照：整图写回课程图谱，并记一条 restore 快照。"""
    conn = get_db()
    try:
        _ensure_version_table(conn)
        row = conn.execute(
            """SELECT id, curriculum_version, version, payload
               FROM knowledge_graph_versions WHERE id = ?""",
            (version_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("找不到这个版本快照，可能已被清理")
    try:
        graph = json.loads(row["payload"] or "{}")
    except Exception:
        raise ValueError("这个版本快照内容损坏，无法恢复")
    if not graph.get("nodes"):
        raise ValueError("这个版本快照没有可用的图谱内容")
    curriculum_version = row["curriculum_version"] or GRAPH_VERSION
    graph["curriculum_version"] = curriculum_version
    source_version = int(row["version"])
    _persist(
        user_id, graph, curriculum_version=curriculum_version,
        change_type="restore",
        change_note=note or f"回滚到 V{source_version}",
    )
    graph["restored_from"] = source_version
    return graph


def _would_create_cycle(prereq_map: dict, source: str, target: str) -> bool:
    """判断在 prereq_map 中加入 target -> source 的先修依赖后是否成环。"""
    stack = [source]
    seen = set()
    while stack:
        current = stack.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(prereq_map.get(current, []) or [])
    return False


def _edge_is_effective(edge: dict) -> bool:
    """AI 先修边是否参与路径编排：显式拒绝/待审核的不参与；老图无字段按采纳处理。"""
    status = edge.get("review_status")
    if status in (REVIEW_REJECTED, REVIEW_PENDING):
        return False
    if status is None:
        # 兼容旧图谱：没有审核字段时按置信度判断（无置信度视为专家级可信）
        confidence = edge.get("confidence")
        if confidence is None:
            return True
        return _confidence(confidence) >= CONFIDENCE_ACCEPT
    return True


def effective_prerequisite_map(graph: dict | None, expert_prereq: dict | None = None) -> tuple:
    """把「专家先修表」与「AI 图谱先修边」合并成路径编排真正使用的先修表。

    规则：
    - 专家先修表权威，原样保留（只保留图谱里存在的节点）；
    - AI 图谱只补专家表没有覆盖的缺失先修边；
    - 只采纳 review_status 不为 rejected/pending 的高置信边；
    - 加入前做环检测，会让先修关系成环的 AI 边直接丢弃。

    返回 (prereq_map, added_edges)：
      prereq_map = {后继 tag: [直接前置 tag, ...]}
      added_edges = 被采纳的 AI 先修边（含 source / target / reason / confidence）
    """
    expert = expert_prereq or {}
    nodes = (graph or {}).get("nodes") or []
    node_ids = {str(n.get("tag") or "").strip() for n in nodes if n.get("tag")}
    if not node_ids:
        node_ids = set(expert) | {p for parents in expert.values() for p in (parents or [])}

    merged = {tag: [] for tag in node_ids}
    for tag, parents in expert.items():
        if tag not in node_ids:
            continue
        for parent in parents or []:
            if parent in node_ids and parent != tag and parent not in merged[tag]:
                merged[tag].append(parent)

    added = []
    for edge in (graph or {}).get("edges") or []:
        if edge.get("relation") != REL_PREREQUISITE:
            continue
        if not _edge_is_effective(edge):
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        if source not in node_ids or target not in node_ids:
            continue
        if source in merged.get(target, []):
            continue
        if _would_create_cycle(merged, source, target):
            logger.info("[KG] 合并时丢弃成环先修边 %s -> %s", source, target)
            continue
        merged[target].append(source)
        added.append({
            "source": source,
            "target": target,
            "reason": edge.get("reason") or "",
            "origin": edge.get("origin") or "llm",
            "confidence": edge.get("confidence"),
            "evidence": edge.get("evidence") or "",
        })
    return merged, added


def review_edge(graph: dict, source: str, target: str, relation: str,
                action: str) -> dict:
    """人工审核一条 AI 边：action = accept / reject。

    采纳先修边前会再做一次环检测，避免人工操作把先修关系变成环。
    返回被修改的边。
    """
    if action not in ("accept", "reject"):
        raise ValueError("action 只能是 accept 或 reject")
    relation = REL_SIMILAR if relation == REL_SIMILAR else REL_PREREQUISITE

    edge = next(
        (
            item for item in (graph or {}).get("edges") or []
            if item.get("source") == source
            and item.get("target") == target
            and (item.get("relation") or REL_PREREQUISITE) == relation
        ),
        None,
    )
    if edge is None:
        raise ValueError("找不到这条关系，请刷新图谱后重试")
    if edge.get("origin") == "expert":
        raise ValueError("专家先修边由课程维护，不能在这里修改")

    if action == "accept" and relation == REL_PREREQUISITE:
        pending = {tag: [] for tag in node_name_index(graph)}
        for item in graph.get("edges") or []:
            if item.get("relation") != REL_PREREQUISITE or item is edge:
                continue
            if item.get("origin") != "expert" and not _edge_is_effective(item):
                continue
            pending.setdefault(item.get("target"), []).append(item.get("source"))
        if _would_create_cycle(pending, source, target):
            raise ValueError("采纳这条先修关系会形成循环依赖，请先拒绝环上的其他边")

    edge["review_status"] = REVIEW_ACCEPTED if action == "accept" else REVIEW_REJECTED
    edge["reviewed_at"] = datetime.now().isoformat()

    # 审核后同步统计，避免前端看到的待审核数量停留在生成时
    stats = graph.setdefault("stats", {})
    edges = graph.get("edges") or []
    stats["pending_edges"] = sum(1 for item in edges if item.get("review_status") == REVIEW_PENDING)
    stats["rejected_edges"] = sum(1 for item in edges if item.get("review_status") == REVIEW_REJECTED)
    stats["accepted_ai_edges"] = sum(
        1 for item in edges
        if item.get("origin") == "llm" and item.get("review_status") == REVIEW_ACCEPTED
    )
    return edge


def _decayed_mastery(tag: str, mastery: dict, mastery_meta: dict, now: datetime) -> tuple:
    """返回 (有效掌握度, 距上次证据天数)。超过 STALE_DAYS 后向 0.5 衰减。"""
    score = (mastery or {}).get(tag)
    if score is None:
        return None, None
    score = float(score)
    meta = (mastery_meta or {}).get(tag) or {}
    last = meta.get("last_activity_at") or meta.get("updated_at")
    if not last:
        return score, None
    try:
        stamp = datetime.fromisoformat(str(last).replace("Z", ""))
    except (TypeError, ValueError):
        return score, None
    days = max(0, (now - stamp).days)
    if days <= STALE_DAYS:
        return score, days
    ratio = min(1.0, (days - STALE_DAYS) / max(DECAY_DAYS, 1))
    return round(score + (0.5 - score) * ratio, 4), days


def _mastery_band(score, mastery_low: float, mastery_high: float) -> str:
    if score is None:
        return "unknown"
    if score >= mastery_high:
        return "high"
    if score >= mastery_low:
        return "medium"
    return "low"


def propagate_readiness(graph: dict | None, prereq_map: dict, mastery: dict,
                        mastery_low: float = None, mastery_high: float = None,
                        mastery_meta: dict = None, now: datetime = None) -> dict:
    """沿先修边向下传播「就绪度」：前置没打牢，后继即使自己分高也不能快进。

    与旧版相比：
    - 未诊断的前置不再假装 0.5：标记 undiagnosed，用中性值参与但不判成 blocker；
    - 前置按权重汇总（专家边 1.0，AI 边 0.5+0.5*置信度），并用「最弱项 65% + 加权均值 35%」
      替代等权 min，避免一个刚及格的先修把整条链路判死；
    - 掌握度带时间衰减，很久没练的知识会向 0.5 回落；
    - 返回节点自身掌握度与前置明细，供前端解释「为什么锁/为什么能学」。

    返回 {tag: {state, score, own_mastery, own_band, undiagnosed, weak_self,
                direct_blockers, blocked_by, root_blockers, parents[]}}
    """
    mastery_low = DEFAULT_MASTERY_LOW if mastery_low is None else mastery_low
    mastery_high = DEFAULT_MASTERY_HIGH if mastery_high is None else mastery_high
    now = now or datetime.now()

    node_ids = {str(n.get("tag") or "").strip() for n in ((graph or {}).get("nodes") or []) if n.get("tag")}
    tags = set(node_ids)
    for tag, parents in (prereq_map or {}).items():
        tags.add(tag)
        tags.update(p or "" for p in (parents or []))

    edge_meta = {}
    for edge in (graph or {}).get("edges") or []:
        if edge.get("relation") != REL_PREREQUISITE:
            continue
        edge_meta[(edge.get("source"), edge.get("target"))] = edge

    memo = {}

    def evaluate(tag: str, stack: frozenset) -> dict:
        if tag in memo:
            return memo[tag]
        own_mastery, own_days = _decayed_mastery(tag, mastery, mastery_meta, now)
        own_band = _mastery_band(own_mastery, mastery_low, mastery_high)
        own_info = {
            "own_mastery": round(own_mastery, 3) if own_mastery is not None else None,
            "own_band": own_band,
            "undiagnosed": own_mastery is None,
            "weak_self": own_mastery is not None and own_mastery < mastery_low,
            "stale_days": own_days,
        }
        if tag in stack:  # 环保护：依赖表异常时按已就绪处理，避免死循环
            return {"state": "ready", "score": 1.0, "direct_blockers": [],
                    "blocked_by": [], "root_blockers": [], "parents": [],
                    **own_info}

        parents = [p for p in (prereq_map.get(tag) or []) if p in tags]
        if not parents:
            result = {
                "state": "ready",
                "score": 1.0,
                "direct_blockers": [],
                "blocked_by": [],
                "root_blockers": [],
                "parents": [],
                **own_info,
            }
            memo[tag] = result
            return result

        direct_blockers, blocked_by, root_blockers = [], [], []
        parent_scores, weights, parent_details = [], [], []
        undiagnosed_count = 0

        for parent in parents:
            parent_result = evaluate(parent, stack | {tag})
            parent_mastery, stale_days = _decayed_mastery(parent, mastery, mastery_meta, now)
            undiagnosed = parent_mastery is None
            effective = UNDIAGNOSED_SCORE if undiagnosed else parent_mastery
            if undiagnosed:
                undiagnosed_count += 1

            edge = edge_meta.get((parent, tag)) or {}
            if not edge or edge.get("origin") == "expert":
                weight = 1.0
            else:
                weight = 0.5 + 0.5 * _confidence(edge.get("confidence"), 1.0)

            parent_scores.append(effective * parent_result["score"])
            weights.append(weight)
            parent_details.append({
                "tag": parent,
                "name": str((edge_meta.get((parent, tag)) or {}).get("name") or parent),
                "mastery": round(parent_mastery, 3) if parent_mastery is not None else None,
                "effective_mastery": round(effective, 3),
                "state": parent_result["state"],
                "undiagnosed": undiagnosed,
                "stale_days": stale_days,
                "weight": round(weight, 2),
                "origin": edge.get("origin") or "expert",
                "confidence": edge.get("confidence"),
                "evidence": edge.get("evidence") or "",
            })

            if not undiagnosed and parent_mastery < mastery_low:
                direct_blockers.append(parent)
                root_blockers.append(parent)
            if parent_result["state"] == "blocked":
                blocked_by.append(parent)
                for blocker in parent_result.get("root_blockers") or []:
                    if blocker not in root_blockers:
                        root_blockers.append(blocker)

        if undiagnosed_count == len(parents):
            # 所有前置都没有练习证据：给中性分，既不判 blocked，也不假装已就绪
            score = UNDIAGNOSED_SCORE
        else:
            weight_sum = sum(weights) or 1.0
            weighted_avg = sum(s * w for s, w in zip(parent_scores, weights)) / weight_sum
            score = round(0.65 * min(parent_scores) + 0.35 * weighted_avg, 3)

        if direct_blockers or blocked_by:
            state = "blocked"
        elif score < mastery_high:
            state = "learning"
        else:
            state = "ready"

        result = {
            "state": state,
            "score": score,
            "direct_blockers": list(dict.fromkeys(direct_blockers)),
            "blocked_by": list(dict.fromkeys(blocked_by)),
            "root_blockers": list(dict.fromkeys(root_blockers)),
            "parents": parent_details,
            **own_info,
        }
        memo[tag] = result
        return result

    return {tag: evaluate(tag, frozenset()) for tag in sorted(tags) if tag}


def similar_index(graph: dict | None) -> dict:
    """把相似边整理成 {tag: [{tag, name, reason}]}，供「对比学习」提示使用。"""
    names = {
        str(n.get("tag") or "").strip(): str(n.get("name") or n.get("tag") or "").strip()
        for n in ((graph or {}).get("nodes") or [])
        if n.get("tag")
    }
    index = {}

    def add(source: str, target: str, reason: str):
        bucket = index.setdefault(source, [])
        if all(item["tag"] != target for item in bucket):
            bucket.append({"tag": target, "name": names.get(target, target), "reason": reason})

    for edge in (graph or {}).get("edges") or []:
        if edge.get("relation") != REL_SIMILAR:
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        add(source, target, edge.get("reason") or "")
        add(target, source, edge.get("reason") or "")
    return index


def node_name_index(graph: dict | None) -> dict:
    """tag -> 展示名，用于把阻塞原因翻译成用户能看懂的名字。"""
    return {
        str(n.get("tag") or "").strip(): str(n.get("name") or n.get("tag") or "").strip()
        for n in ((graph or {}).get("nodes") or [])
        if n.get("tag")
    }


def build_skeleton_graph(nodes: list, expert_prereq: dict) -> dict:
    """不调用 LLM 时的降级骨架：专家先修边 + 课程目录包含边，无描述与相似边。"""
    node_list = _normalize_nodes(nodes)
    node_ids = {n["tag"] for n in node_list}
    expert = _expert_edges(expert_prereq, node_ids)
    part_of = _part_of_edges(node_ids)
    edges = [*expert, *part_of]
    return {
        "curriculum_version": GRAPH_VERSION,
        "generated_by": "expert",
        "generated_at": datetime.now().isoformat(),
        "scope": "course",
        "nodes": [
            {**n, "definition": n.get("definition") or "",
             "key_points": n.get("key_points") or [],
             "confusable": n.get("confusable") or [],
             "misconceptions": n.get("misconceptions") or []}
            for n in node_list
        ],
        "edges": edges,
        "discarded_edges": [],
        "stats": {
            "nodes": len(node_list),
            "edges": len(edges),
            "prerequisite": len(expert),
            "similar": 0,
            "part_of": len(part_of),
            "llm_nodes": 0,
            "pending_edges": 0,
            "rejected_edges": 0,
        },
        "notice": "当前是专家先修骨架，还没有 AI 生成的描述与相似关系。",
    }


async def generate_knowledge_graph(user_id: int, nodes: list, expert_prereq: dict | None = None) -> dict:
    """调用 LLM 生成课程级知识图谱并持久化。

    返回结构：
      {curriculum_version, generated_by, generated_at, scope, nodes[], edges[],
       discarded_edges[], stats{}, notice}
    """
    node_list = _normalize_nodes(nodes)
    if not node_list:
        raise ValueError("知识点名单为空，无法构建知识图谱")

    node_ids = {n["tag"] for n in node_list}
    expert = _expert_edges(expert_prereq or {}, node_ids)

    descriptions = await _llm_descriptions(user_id, node_list)
    described = _merge_descriptions(node_list, descriptions)

    relations = await _llm_relations(user_id, described, expert_prereq or {})
    raw_edges = []
    for item in relations.get("prerequisite") or []:
        if isinstance(item, dict):
            raw_edges.append({**item, "relation": REL_PREREQUISITE})
    for item in relations.get("similar") or []:
        if isinstance(item, dict):
            raw_edges.append({**item, "relation": REL_SIMILAR})

    llm_edges, discarded = _merge_llm_edges(raw_edges, expert, node_ids)
    part_of = _part_of_edges(node_ids)
    edges = [*expert, *part_of, *llm_edges]

    generated = sum(1 for n in described if n.get("definition"))
    pending = sum(1 for e in llm_edges if e.get("review_status") == REVIEW_PENDING)
    rejected = sum(1 for e in llm_edges if e.get("review_status") == REVIEW_REJECTED)
    graph = {
        "curriculum_version": GRAPH_VERSION,
        "generated_by": "llm",
        "generated_at": datetime.now().isoformat(),
        "scope": "course",
        "nodes": described,
        "edges": edges,
        "discarded_edges": discarded,
        "stats": {
            "nodes": len(described),
            "edges": len(edges),
            "prerequisite": sum(1 for e in edges if e["relation"] == REL_PREREQUISITE),
            "similar": sum(1 for e in edges if e["relation"] == REL_SIMILAR),
            "part_of": sum(1 for e in edges if e["relation"] == REL_PART_OF),
            "llm_nodes": generated,
            "pending_edges": pending,
            "rejected_edges": rejected,
            "discarded_edges": len(discarded),
        },
        "notice": f"AI 已为 {generated}/{len(described)} 个知识点生成描述，并推断出 "
                  f"{len(llm_edges)} 条补充关系（其中 {pending} 条待你确认、{rejected} 条置信度不足；"
                  f"专家先修表保持不变）。",
    }
    _persist(user_id, graph, change_type="generate", change_note="AI 重新生成知识图谱")
    return graph
