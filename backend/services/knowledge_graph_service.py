"""知识图谱构建服务（技术方案.md §5.8 第二版：知识图谱·网状视图）

借鉴 KnowLP（AAAI 2026，arXiv 2506.22303）EDU-GraphRAG 的「自适应构建知识点结构图」思路，
做产品化裁剪后的实现：

  1. 输入只有「知识点名单」（tag + 名称），不依赖教材 PDF / 外部语料；
  2. LLM 为每个知识点生成结构化描述（定义 / 要点 / 易混对象）；
  3. LLM 在描述基础上判定两类关系：先修 prerequisite、相似 similar；
  4. 与专家先修表（data/dsa_prerequisites.json）合并：专家边权威、不被 LLM 覆盖，
     LLM 只补「专家表未覆盖」的缺失先修边与全部相似边；
  5. 确定性校验：剔除未知节点、自环、会让先修图成环的边。

如实边界：这里是「LLM 依据知识点名与描述推断关系」，**不是** GraphRAG 检索建图，
**不做**强化学习训练、**不做**认知诊断（与 §5.7 的措辞红线保持一致）。
"""
import json
import logging
from datetime import datetime

from database import get_db
from services.ai_service import call_llm, extract_json, extract_json_object

logger = logging.getLogger(__name__)

GRAPH_VERSION = "dsa-kg-llm-v1"

REL_PREREQUISITE = "prerequisite"
REL_SIMILAR = "similar"

_LLM_ERROR_PREFIX = "LLM调用异常"


def _normalize_nodes(nodes: list) -> list:
    """把入参规整成 [{tag, name}]，丢掉缺 tag 的项并按 tag 去重。"""
    seen = {}
    for node in nodes or []:
        tag = str((node or {}).get("tag") or "").strip()
        if not tag or tag in seen:
            continue
        seen[tag] = {"tag": tag, "name": str((node or {}).get("name") or tag).strip()}
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
            })
    return edges


def _merge_llm_edges(llm_edges: list, accepted: list, node_ids: set) -> list:
    """把 LLM 给出的边并入：未知节点 / 自环 / 重复丢弃，成环的先修边丢弃。"""
    existing_pairs = {(e["source"], e["target"]) for e in accepted}
    result = []
    for edge in llm_edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation = REL_SIMILAR if edge.get("relation") == REL_SIMILAR else REL_PREREQUISITE
        if not source or not target or source == target:
            continue
        if source not in node_ids or target not in node_ids:
            continue
        if (source, target) in existing_pairs:
            continue
        candidate = {
            "source": source,
            "target": target,
            "relation": relation,
            "reason": str(edge.get("reason") or "").strip()[:60],
            "origin": "llm",
        }
        if relation == REL_PREREQUISITE:
            if _has_cycle([*accepted, *result, candidate], node_ids):
                logger.info("[KG] 丢弃成环的 LLM 先修边 %s -> %s", source, target)
                continue
        elif (target, source) in existing_pairs:
            continue
        existing_pairs.add((source, target))
        result.append(candidate)
    return result


async def _llm_descriptions(user_id: int, nodes: list) -> list:
    """第一步：让 LLM 为每个知识点生成结构化描述（对标 EDU-GraphRAG 的描述生成）。"""
    listing = json.dumps(nodes, ensure_ascii=False)
    prompt = (
        "下面是《数据结构与算法》课程的知识点名单（tag 为唯一标识）：\n"
        f"{listing}\n\n"
        "请为每个知识点输出一条结构化描述，返回 JSON 数组，元素格式：\n"
        '{"tag": "与输入完全一致的 tag", "definition": "一句话定义，40 字内", '
        '"key_points": ["要点1", "要点2", "要点3"], "confusable": ["最容易与它混淆的其他知识点 tag"]}\n'
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
    """第二步：让 LLM 在描述基础上判定先修 / 相似两类关系。"""
    listing = json.dumps(
        [{"tag": n["tag"], "name": n["name"], "definition": n.get("definition", "")} for n in nodes],
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
        '{"prerequisite": [{"source": "先修知识点 tag", "target": "后继知识点 tag", "reason": "20 字内理由"}], '
        '"similar": [{"source": "tag", "target": "tag", "reason": "20 字内理由"}]}\n'
        "规则：\n"
        "1. prerequisite 有方向：source 必须先于 target 学习；只补专家表未覆盖的缺失关系，禁止输出与专家表重复或相反的边；\n"
        "2. similar 无方向，表示概念相近、容易混淆、适合放在一起对比学习的一对知识点；\n"
        "3. 只能使用名单内的 tag，禁止编造，禁止自环。"
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
        merged.append({
            **node,
            "definition": str(item.get("definition") or "").strip()[:80],
            "key_points": key_points,
            "confusable": confusable,
        })
    return merged


def _persist(user_id: int, graph: dict) -> None:
    conn = get_db()
    try:
        payload = json.dumps(graph, ensure_ascii=False)
        now = datetime.now().isoformat()
        row = conn.execute(
            "SELECT id FROM knowledge_graphs WHERE user_id = ? AND curriculum_version = ?",
            (user_id, GRAPH_VERSION),
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE knowledge_graphs
                   SET payload = ?, node_count = ?, edge_count = ?, updated_at = ?
                   WHERE id = ?""",
                (payload, graph["stats"]["nodes"], graph["stats"]["edges"], now, row["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO knowledge_graphs
                   (user_id, curriculum_version, payload, node_count, edge_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, GRAPH_VERSION, payload,
                 graph["stats"]["nodes"], graph["stats"]["edges"], now, now),
            )
        conn.commit()
    finally:
        conn.close()


def get_knowledge_graph(user_id: int) -> dict | None:
    """读取已持久化的知识图谱（未生成过返回 None）。"""
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT payload, updated_at FROM knowledge_graphs
               WHERE user_id = ? AND curriculum_version = ?""",
            (user_id, GRAPH_VERSION),
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


def build_skeleton_graph(nodes: list, expert_prereq: dict) -> dict:
    """不调用 LLM 时的降级骨架：只有专家先修边，无描述与相似边。"""
    node_list = _normalize_nodes(nodes)
    node_ids = {n["tag"] for n in node_list}
    edges = _expert_edges(expert_prereq, node_ids)
    return {
        "curriculum_version": GRAPH_VERSION,
        "generated_by": "expert",
        "generated_at": datetime.now().isoformat(),
        "nodes": [{**n, "definition": "", "key_points": [], "confusable": []} for n in node_list],
        "edges": edges,
        "stats": {
            "nodes": len(node_list),
            "edges": len(edges),
            "prerequisite": len(edges),
            "similar": 0,
            "llm_nodes": 0,
        },
        "notice": "当前是专家先修骨架，还没有 AI 生成的描述与相似关系。",
    }


async def generate_knowledge_graph(user_id: int, nodes: list, expert_prereq: dict | None = None) -> dict:
    """调用 LLM 生成知识图谱并持久化。

    返回结构：
      {curriculum_version, generated_by, generated_at, nodes[], edges[], stats{}, notice}
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

    llm_edges = _merge_llm_edges(raw_edges, expert, node_ids)
    edges = [*expert, *llm_edges]

    generated = sum(1 for n in described if n.get("definition"))
    graph = {
        "curriculum_version": GRAPH_VERSION,
        "generated_by": "llm",
        "generated_at": datetime.now().isoformat(),
        "nodes": described,
        "edges": edges,
        "stats": {
            "nodes": len(described),
            "edges": len(edges),
            "prerequisite": sum(1 for e in edges if e["relation"] == REL_PREREQUISITE),
            "similar": sum(1 for e in edges if e["relation"] == REL_SIMILAR),
            "llm_nodes": generated,
        },
        "notice": f"AI 已为 {generated}/{len(described)} 个知识点生成描述，并推断出 "
                  f"{sum(1 for e in edges if e['origin'] == 'llm')} 条补充关系（专家先修表保持不变）。",
    }
    _persist(user_id, graph)
    return graph
