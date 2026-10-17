"""同一输入多次生成知识图谱边，写入快照供图谱测评计算稳定性。

用法（必须使用项目虚拟环境）：
    & "F:\\code\\MyPython\\computer-cross-education\\tiaozhanbei\\venv\\Scripts\\python.exe" `
        backend/scripts/kg_stability_probe.py --user-id 1 --runs 3

前提：该用户已在「个人中心」配置可用的 LLM API Key。
脚本只写快照文件，不改动数据库里的课程图谱。
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from services import agent_course  # noqa: E402
from services import knowledge_graph_service as kg  # noqa: E402

SNAPSHOT_DIR = os.path.join(BACKEND_DIR, "data", "eval", "kg_snapshots")


def _prerequisite_pairs(relations: dict, node_ids: set) -> list:
    pairs = []
    seen = set()
    for item in (relations or {}).get("prerequisite") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        if source not in node_ids or target not in node_ids:
            continue
        pair = (source, target)
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append([source, target])
    return pairs


def _jaccard(left: list, right: list) -> float:
    a = {tuple(item) for item in left}
    b = {tuple(item) for item in right}
    union = a | b
    return round(len(a & b) / len(union), 3) if union else 1.0


async def probe(user_id: int, runs: int) -> None:
    nodes = agent_course.course_knowledge_points()
    expert = agent_course._load_prerequisites()
    node_ids = {item["tag"] for item in nodes}

    print(f"知识点 {len(nodes)} 个，运行 {runs} 次；先生成一次描述作为固定输入……")
    descriptions = await kg._llm_descriptions(user_id, nodes)
    described = kg._merge_descriptions(nodes, descriptions)

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshots = []
    for index in range(1, runs + 1):
        print(f"第 {index}/{runs} 次生成关系……")
        relations = await kg._llm_relations(user_id, described, expert)
        pairs = _prerequisite_pairs(relations, node_ids)
        payload = {
            "generated_at": datetime.now().isoformat(),
            "user_id": user_id,
            "run": index,
            "pairs": pairs,
        }
        path = os.path.join(SNAPSHOT_DIR, f"kg-{stamp}-run{index}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        snapshots.append(pairs)
        print(f"  写出 {len(pairs)} 条先修边 -> {path}")

    print("\n两两 Jaccard 相似度：")
    for i in range(len(snapshots)):
        for j in range(i + 1, len(snapshots)):
            print(f"  run{i + 1} vs run{j + 1}: {_jaccard(snapshots[i], snapshots[j])}")
    print("\n完成。刷新「图谱测评」即可看到稳定性抽检结果。")


def main() -> None:
    parser = argparse.ArgumentParser(description="知识图谱边生成稳定性抽检")
    parser.add_argument("--user-id", type=int, default=1, help="使用哪个用户的 LLM 配置（默认 1）")
    parser.add_argument("--runs", type=int, default=3, help="重复生成次数（默认 3）")
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs 至少为 2，否则无法比较稳定性")
    try:
        asyncio.run(probe(args.user_id, args.runs))
    except RuntimeError as exc:
        print(f"生成失败：{exc}")
        print("请先在「个人中心 → AI大模型配置」里填写可用的 LLM API Key。")
        sys.exit(1)


if __name__ == "__main__":
    main()
