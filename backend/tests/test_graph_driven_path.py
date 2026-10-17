"""知识图谱驱动学习路径的单元测试：先修边合并、就绪度传播、补先修与跳过拦截。"""
import asyncio
import json
import unittest
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import AsyncMock

from services import knowledge_graph_service as kg
from services import learning_service as ls
from services.agent_course import (
    COURSE_KNOWLEDGE_POINTS,
    COURSE_TRACKS,
    course_point_names,
    plan_course_path,
    project_index,
)


LINEAR = "dsa-dsa-linear-data-structures"
INTRO = "dsa-dsa-intro"


def _graph(nodes, edges):
    return {
        "graph_version": "test",
        "nodes": [{"tag": tag, "name": tag} for tag in nodes],
        "edges": edges,
    }


class EffectivePrerequisiteTests(unittest.TestCase):
    def test_merges_llm_edges_and_drops_invalid_ones(self):
        graph = _graph(
            ["a", "b", "c"],
            [
                {"source": "a", "target": "c", "relation": "prerequisite"},
                {"source": "c", "target": "a", "relation": "prerequisite"},  # 成环
                {"source": "x", "target": "b", "relation": "prerequisite"},  # 未知节点
                {"source": "b", "target": "b", "relation": "prerequisite"},  # 自环
                {"source": "a", "target": "b", "relation": "similar"},       # 非先修
            ],
        )
        merged, added = kg.effective_prerequisite_map(graph, {"b": ["a"]})

        self.assertEqual(merged["b"], ["a"])
        self.assertEqual(merged["c"], ["a"])
        self.assertEqual(merged["a"], [])
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["target"], "c")

    def test_without_graph_uses_expert_table(self):
        merged, added = kg.effective_prerequisite_map(None, {"b": ["a"]})
        self.assertEqual(merged["b"], ["a"])
        self.assertEqual(added, [])


class ReadinessPropagationTests(unittest.TestCase):
    def test_weak_prerequisite_blocks_descendants(self):
        prereq = {"b": ["a"], "c": ["b"]}
        mastery = {"a": 0.2, "b": 0.9}
        result = kg.propagate_readiness(None, prereq, mastery)

        self.assertEqual(result["a"]["state"], "ready")
        self.assertEqual(result["b"]["state"], "blocked")
        self.assertEqual(result["b"]["direct_blockers"], ["a"])
        self.assertEqual(result["c"]["state"], "blocked")
        self.assertEqual(result["c"]["blocked_by"], ["b"])
        self.assertIn("a", result["c"]["root_blockers"])
        self.assertLess(result["c"]["score"], 0.4)

    def test_mastered_chain_is_ready(self):
        result = kg.propagate_readiness(None, {"b": ["a"]}, {"a": 0.9, "b": 0.9})
        self.assertEqual(result["b"]["state"], "ready")
        self.assertEqual(result["b"]["root_blockers"], [])


class SimilarIndexTests(unittest.TestCase):
    def test_similar_edges_are_bidirectional(self):
        graph = _graph(
            ["a", "b"],
            [{"source": "a", "target": "b", "relation": "similar", "reason": "都用到指针"}],
        )
        index = kg.similar_index(graph)
        self.assertEqual(index["a"][0]["tag"], "b")
        self.assertEqual(index["b"][0]["tag"], "a")
        self.assertEqual(index["a"][0]["reason"], "都用到指针")


class GraphDrivenPlanTests(unittest.TestCase):
    def _plan(self, graph_context, mastery):
        return plan_course_path(
            [COURSE_TRACKS[0]["name"]],
            {"mastery": mastery, "level_label": "有一定基础", "source": "mastery"},
            "标准",
            prereq_map={LINEAR: [INTRO]},
            graph_context=graph_context,
        )

    def test_blocked_prerequisite_inserts_remedial_and_blocks_skip(self):
        graph_context = {
            "has_graph": True,
            "source": "llm",
            "added_edges": [{"source": INTRO, "target": LINEAR}],
            "readiness": {
                LINEAR: {
                    "state": "blocked",
                    "score": 0.18,
                    "direct_blockers": [INTRO],
                    "blocked_by": [],
                    "root_blockers": [INTRO],
                },
            },
            "similar": {},
            "names": {INTRO: "算法入门"},
        }
        path = self._plan(graph_context, {LINEAR: 0.9})

        topics = [task["topic"] for task in path["phases"][0]["tasks"]]
        self.assertTrue(any(topic == "补先修：算法入门" for topic in topics))

        linear_tasks = [
            task for task in path["phases"][0]["tasks"]
            if task.get("knowledge") == LINEAR
        ]
        self.assertTrue(all(task["skippable"] is False for task in linear_tasks))
        self.assertTrue(all(task.get("graph_gated") for task in linear_tasks))

        operator = path["applied_operators"]["graph"]
        self.assertTrue(operator["applied"])
        self.assertEqual(len(operator["remedial_inserted"]), 1)
        self.assertGreaterEqual(len(operator["skip_blocked"]), 1)
        self.assertFalse(operator["readiness_blocked"][0]["blockers"] == [])

        summary = path["personalization_summary"]
        self.assertIn("补先修任务", summary)
        self.assertIn("前置没掌握", summary)

    def test_no_graph_keeps_expert_behaviour(self):
        path = self._plan({}, {LINEAR: 0.9})
        operator = path["applied_operators"]["graph"]
        self.assertFalse(operator["applied"])
        self.assertEqual(operator["remedial_inserted"], [])
        self.assertFalse(any(
            task["topic"].startswith("补先修")
            for task in path["phases"][0]["tasks"]
        ))
        self.assertTrue(any(
            task["skippable"] for task in path["phases"][0]["tasks"]
        ))


class CourseKnowledgePointTests(unittest.TestCase):
    def test_course_points_cover_projects(self):
        tags = [item["tag"] for item in COURSE_KNOWLEDGE_POINTS]
        self.assertEqual(len(tags), len(set(tags)))
        project_tags = {
            task["knowledge"] for track in COURSE_TRACKS for task in track["tasks"]
        }
        # 图谱节点是 44 个课程知识点，实训项目对应的 11 个核心节点必须全部包含在内
        self.assertTrue(project_tags.issubset(set(tags)))

    def test_node_names_are_canonical_not_first_project(self):
        names = course_point_names()
        self.assertNotEqual(names[LINEAR], "项目1：实现顺序表插入")
        self.assertIn("线性结构", names[LINEAR])

    def test_project_index_keeps_all_projects_of_shared_point(self):
        linear = project_index()[LINEAR]
        self.assertEqual(len(linear), 3)
        self.assertEqual([item["lab_id"] for item in linear], ["1-1", "1-2", "1-3"])
        self.assertTrue(all(item["module_id"] == 1 for item in linear))

    def test_project_index_respects_selected_tracks(self):
        index = project_index([COURSE_TRACKS[0]["name"]])
        self.assertIn(LINEAR, index)
        self.assertNotIn("dsa-heap-sort", index)


class EdgeConfidenceTests(unittest.TestCase):
    def test_confidence_buckets(self):
        self.assertEqual(kg._review_status(0.9), kg.REVIEW_ACCEPTED)
        self.assertEqual(kg._review_status(0.6), kg.REVIEW_PENDING)
        self.assertEqual(kg._review_status(0.2), kg.REVIEW_REJECTED)

    def test_llm_edges_carry_status_and_discard_reasons(self):
        node_ids = {"a", "b", "c"}
        expert = [{
            "source": "a", "target": "b", "relation": "prerequisite",
            "origin": "expert", "confidence": 1.0, "review_status": kg.REVIEW_ACCEPTED,
        }]
        kept, discarded = kg._merge_llm_edges(
            [
                {"source": "b", "target": "c", "relation": "prerequisite",
                 "confidence": 0.9, "evidence": "c 依赖 b"},
                {"source": "c", "target": "a", "relation": "prerequisite", "confidence": 0.8},
                {"source": "a", "target": "b", "relation": "prerequisite", "confidence": 0.9},
                {"source": "a", "target": "a", "relation": "prerequisite", "confidence": 0.9},
                {"source": "x", "target": "a", "relation": "prerequisite", "confidence": 0.9},
                {"source": "a", "target": "c", "relation": "similar", "confidence": 0.4},
            ],
            expert,
            node_ids,
        )

        self.assertEqual(len(kept), 2)
        accepted = [item for item in kept if item["review_status"] == kg.REVIEW_ACCEPTED]
        self.assertEqual(len(accepted), 1)
        self.assertEqual((accepted[0]["source"], accepted[0]["target"]), ("b", "c"))
        self.assertEqual(accepted[0]["evidence"], "c 依赖 b")

        similar = [item for item in kept if item["relation"] == "similar"][0]
        self.assertEqual(similar["review_status"], kg.REVIEW_REJECTED)

        reasons = {item["reason"] for item in discarded}
        self.assertEqual(reasons, {
            "会让先修关系成环",
            "与已有关系重复",
            "自环",
            "节点不在课程知识点名单内",
        })

    def test_pending_and_rejected_edges_do_not_drive_path(self):
        graph = _graph(
            ["a", "b", "c"],
            [
                {"source": "a", "target": "b", "relation": "prerequisite",
                 "origin": "llm", "confidence": 0.6, "review_status": kg.REVIEW_PENDING},
                {"source": "b", "target": "c", "relation": "prerequisite",
                 "origin": "llm", "confidence": 0.9, "review_status": kg.REVIEW_ACCEPTED},
            ],
        )
        merged, added = kg.effective_prerequisite_map(graph, {})
        self.assertEqual(merged["b"], [])
        self.assertEqual(merged["c"], ["b"])
        self.assertEqual(len(added), 1)

    def test_legacy_graph_without_review_status_uses_confidence(self):
        low = _graph(
            ["a", "b"],
            [{"source": "a", "target": "b", "relation": "prerequisite", "confidence": 0.6}],
        )
        merged, _ = kg.effective_prerequisite_map(low, {})
        self.assertEqual(merged["b"], [])


class ReviewEdgeTests(unittest.TestCase):
    def _graph_with_pending(self):
        return {
            "nodes": [
                {"tag": "a", "name": "A"},
                {"tag": "b", "name": "B"},
                {"tag": "c", "name": "C"},
            ],
            "edges": [
                {"source": "a", "target": "b", "relation": "prerequisite",
                 "origin": "expert", "confidence": 1.0, "review_status": kg.REVIEW_ACCEPTED},
                {"source": "b", "target": "c", "relation": "prerequisite",
                 "origin": "llm", "confidence": 0.6, "review_status": kg.REVIEW_PENDING},
            ],
            "stats": {"pending_edges": 1},
        }

    def test_accept_pending_edge_updates_stats_and_path(self):
        graph = self._graph_with_pending()
        edge = kg.review_edge(graph, "b", "c", "prerequisite", "accept")

        self.assertEqual(edge["review_status"], kg.REVIEW_ACCEPTED)
        self.assertTrue(edge.get("reviewed_at"))
        self.assertEqual(graph["stats"]["pending_edges"], 0)
        self.assertEqual(graph["stats"]["accepted_ai_edges"], 1)

        merged, added = kg.effective_prerequisite_map(graph, {"b": ["a"]})
        self.assertEqual(merged["c"], ["b"])
        self.assertEqual(len(added), 1)

    def test_reject_edge_removes_it_from_path(self):
        graph = self._graph_with_pending()
        kg.review_edge(graph, "b", "c", "prerequisite", "reject")

        self.assertEqual(graph["stats"]["rejected_edges"], 1)
        merged, added = kg.effective_prerequisite_map(graph, {"b": ["a"]})
        self.assertEqual(merged["c"], [])
        self.assertEqual(added, [])

    def test_expert_edge_cannot_be_reviewed(self):
        with self.assertRaises(ValueError):
            kg.review_edge(self._graph_with_pending(), "a", "b", "prerequisite", "reject")

    def test_accept_cycle_is_refused(self):
        graph = {
            "nodes": [{"tag": "a", "name": "A"}, {"tag": "b", "name": "B"}],
            "edges": [
                {"source": "a", "target": "b", "relation": "prerequisite",
                 "origin": "expert", "confidence": 1.0, "review_status": kg.REVIEW_ACCEPTED},
                {"source": "b", "target": "a", "relation": "prerequisite",
                 "origin": "llm", "confidence": 0.6, "review_status": kg.REVIEW_PENDING},
            ],
        }
        with self.assertRaises(ValueError) as ctx:
            kg.review_edge(graph, "b", "a", "prerequisite", "accept")
        self.assertIn("循环", str(ctx.exception))

    def test_missing_edge_and_invalid_action(self):
        graph = self._graph_with_pending()
        with self.assertRaises(ValueError):
            kg.review_edge(graph, "a", "c", "prerequisite", "accept")
        with self.assertRaises(ValueError):
            kg.review_edge(graph, "b", "c", "prerequisite", "maybe")


class ReadinessDiagnosticsTests(unittest.TestCase):
    def test_undiagnosed_prerequisite_is_neutral_not_blocker(self):
        result = kg.propagate_readiness(None, {"b": ["a"]}, {})

        self.assertTrue(result["a"]["undiagnosed"])
        self.assertNotEqual(result["b"]["state"], "blocked")
        self.assertEqual(result["b"]["direct_blockers"], [])
        parent = result["b"]["parents"][0]
        self.assertTrue(parent["undiagnosed"])
        self.assertEqual(parent["effective_mastery"], kg.UNDIAGNOSED_SCORE)
        self.assertEqual(result["b"]["score"], kg.UNDIAGNOSED_SCORE)

    def test_stale_mastery_decays_toward_neutral(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        meta = {"a": {"last_activity_at": (now - timedelta(days=90)).isoformat()}}
        result = kg.propagate_readiness(
            None, {"b": ["a"]}, {"a": 0.95}, mastery_meta=meta, now=now
        )

        parent = result["b"]["parents"][0]
        self.assertEqual(parent["stale_days"], 90)
        self.assertAlmostEqual(parent["mastery"], 0.5, places=3)
        self.assertEqual(result["b"]["state"], "learning")

    def test_recent_mastery_is_not_decayed(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        meta = {"a": {"last_activity_at": (now - timedelta(days=3)).isoformat()}}
        result = kg.propagate_readiness(
            None, {"b": ["a"]}, {"a": 0.95}, mastery_meta=meta, now=now
        )
        self.assertAlmostEqual(result["b"]["parents"][0]["mastery"], 0.95, places=3)


class TwoStageGenerationTests(unittest.TestCase):
    def test_descriptions_attach_key_points_and_filter_confusable(self):
        merged = kg._merge_descriptions(
            [{"tag": "a", "name": "A"}, {"tag": "b", "name": "B"}],
            [{"tag": "a", "definition": "定义 A", "key_points": ["p1", "p2"],
              "confusable": ["a", "b"]}],
        )
        self.assertEqual(merged[0]["definition"], "定义 A")
        self.assertEqual(merged[0]["key_points"], ["p1", "p2"])
        self.assertEqual(merged[0]["confusable"], ["b"])
        self.assertEqual(merged[1]["definition"], "")
        self.assertEqual(merged[1]["key_points"], [])

    def test_relation_prompt_carries_previous_stage_fields(self):
        captured = []

        async def fake_call(user_id, messages, **kwargs):
            captured.append(messages[-1]["content"])
            return json.dumps({"prerequisite": [], "similar": []})

        nodes = [
            {"tag": "a", "name": "A", "definition": "定义 A",
             "key_points": ["要点甲"], "confusable": ["b"]},
            {"tag": "b", "name": "B", "definition": "", "key_points": [], "confusable": []},
        ]
        with mock.patch.object(kg, "call_llm", fake_call):
            asyncio.run(kg._llm_relations(1, nodes, {}))

        prompt = captured[0]
        self.assertIn("要点甲", prompt)
        self.assertIn('"confusable": ["b"]', prompt)

    def test_skeleton_graph_is_course_scoped_with_discard_field(self):
        graph = kg.build_skeleton_graph(
            [{"tag": "a", "name": "A"}, {"tag": "b", "name": "B"}],
            {"b": ["a"]},
        )
        self.assertEqual(graph["scope"], "course")
        self.assertEqual(graph["discarded_edges"], [])
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["edges"][0]["origin"], "expert")


class RemedialReuseTests(unittest.TestCase):
    def test_existing_project_is_reused_instead_of_duplicate_task(self):
        target = "dsa-binary-search-tree-insert"
        tracks = [COURSE_TRACKS[0]["name"], COURSE_TRACKS[1]["name"]]
        graph_context = {
            "has_graph": True,
            "source": "llm",
            "added_edges": [],
            "readiness": {
                target: {
                    "state": "blocked",
                    "score": 0.2,
                    "direct_blockers": [LINEAR],
                    "blocked_by": [],
                    "root_blockers": [LINEAR],
                },
            },
            "similar": {},
            "names": {LINEAR: "线性结构：顺序表 / 链表 / 栈"},
        }
        path = plan_course_path(
            tracks,
            {"mastery": {target: 0.9}, "level_label": "有一定基础", "source": "mastery"},
            "标准",
            prereq_map={target: [LINEAR]},
            graph_context=graph_context,
        )

        all_topics = [task["topic"] for phase in path["phases"] for task in phase["tasks"]]
        self.assertFalse(any(topic.startswith("补先修") for topic in all_topics))

        linear_tasks = [task for task in path["phases"][0]["tasks"]
                        if task.get("knowledge") == LINEAR]
        self.assertTrue(linear_tasks)
        self.assertTrue(all(task.get("remedial_focus") for task in linear_tasks))
        self.assertTrue(all(task.get("remedial_for") for task in linear_tasks))

        links = path["applied_operators"]["graph"]["remedial_links"]
        self.assertTrue(links)
        self.assertEqual(links[0]["blocker"], LINEAR)
        self.assertTrue(links[0]["lab_id"])

        bst_tasks = [task for task in path["phases"][1]["tasks"]
                     if task.get("knowledge") == target]
        self.assertTrue(bst_tasks)
        self.assertTrue(all(task["skippable"] is False for task in bst_tasks))
        self.assertTrue(all(task.get("graph_gated") for task in bst_tasks))


class PathNeedsApplyTests(unittest.TestCase):
    def _roadmap(self, applied_at, current_at, applied=True):
        path = {
            "updated_at": "2026-01-01T00:00:00",
            "path_data": {
                "curriculum_version": "agent-project-path-v2",
                "learning_depth": "标准",
                "phases": [{
                    "name": COURSE_TRACKS[0]["name"],
                    "description": "",
                    "tasks": [{
                        "day": 1,
                        "topic": "项目1：实现顺序表插入",
                        "knowledge": LINEAR,
                        "lab_id": "1-1",
                        "module_id": 1,
                        "duration": "45分钟",
                    }],
                }],
                "applied_operators": {
                    "graph": {"applied": applied, "graph_updated_at": applied_at},
                },
            },
            "progress": {"completed_tasks": {}, "current_day": 1, "overall_progress": 0},
        }
        graph_context = {
            "has_graph": True,
            "graph": {
                "updated_at": current_at,
                "stats": {},
                "edges": [],
                "discarded_edges": [],
            },
            "source": "llm",
            "prereq_map": {},
            "added_edges": [],
            "readiness": {},
            "similar": {},
            "names": {},
        }
        with mock.patch.object(ls, "get_learning_path", AsyncMock(return_value=path)), \
                mock.patch.object(ls, "_mastery_detail_by_knowledge", return_value={}), \
                mock.patch.object(ls, "_build_graph_context", return_value=graph_context):
            return asyncio.run(ls.build_learning_roadmap(1))

    def test_graph_updated_after_path_requires_apply(self):
        roadmap = self._roadmap("old", "new")
        self.assertTrue(roadmap["graph"]["path_needs_apply"])
        self.assertIn("重排", roadmap["graph"]["needs_apply_reason"])

    def test_same_graph_version_needs_no_apply(self):
        roadmap = self._roadmap("same", "same")
        self.assertFalse(roadmap["graph"]["path_needs_apply"])

    def test_path_never_applied_graph_requires_apply(self):
        roadmap = self._roadmap(None, "new", applied=False)
        self.assertTrue(roadmap["graph"]["path_needs_apply"])


class TaskIdentityTests(unittest.TestCase):
    def test_identity_is_stable_across_day_changes(self):
        first = {"day": 3, "knowledge": LINEAR, "lab_id": "1-1",
                 "topic": "项目1：实现顺序表插入"}
        moved = {**first, "day": 9}
        self.assertEqual(ls._task_identity(first), ls._task_identity(moved))
        self.assertNotEqual(
            ls._task_identity(first),
            ls._task_identity({**first, "lab_id": "1-2"}),
        )


if __name__ == "__main__":
    unittest.main()
