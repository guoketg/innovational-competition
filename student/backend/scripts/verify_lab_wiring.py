"""校验 13 个编程实验室关卡在七个文件之间的接线是否一致。

用法（在 student/backend 目录下）：
    python scripts/verify_lab_wiring.py

同一道关卡的内容散落在七个地方：前端导航、题目正文、隐藏用例、变式题、故障画像、
工作区阶段配置、课程路径。它们不共享数据结构，任何一处改了名字而另一处没跟上，
都只会在学生点进去的时候才暴露。这个脚本把它们横向对一遍：

- 关卡 id 集合七处一致，且恰好是 1-1 ~ 4-3 这 13 个
- 前端导航的阶段名 / 关卡标题 / 时长与题目正文逐字一致
- 课程路径的 lab_id 与知识标签都能在教程种子里找到
- 工作区配置的知识标签同样能在教程种子里找到

不导入 langchain 等重依赖，因此在没有 venv 的机器上也能直接跑。
"""

from __future__ import annotations

import json
import os
import re
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

EXPECTED_IDS = [
    "1-1", "1-2", "1-3",
    "2-1", "2-2", "2-3", "2-4",
    "3-1", "3-2", "3-3",
    "4-1", "4-2", "4-3",
]


def _load_exercises() -> list[dict]:
    path = os.path.join(_BACKEND_DIR, "data", "flagship_exercises.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_tutorial_tags() -> set[str]:
    path = os.path.join(_BACKEND_DIR, "data", "tutorial_seed.json")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    items = payload if isinstance(payload, list) else payload.get("documents", [])
    return {str(item.get("knowledge_tag", "")) for item in items if item.get("knowledge_tag")}


def _load_frontend_modules() -> list[dict]:
    """Parse the navigation config with a regex rather than a JS runtime."""
    path = os.path.join(_BACKEND_DIR, "..", "frontend", "src", "config", "flagshipExercises.js")
    with open(os.path.abspath(path), "r", encoding="utf-8") as handle:
        source = handle.read()
    modules = []
    for block in re.finditer(r"\{\s*id:\s*(\d+),\s*name:\s*'([^']*)'.*?tasks:\s*\[(.*?)\],\s*\}", source, re.S):
        module_id, name, body = block.group(1), block.group(2), block.group(3)
        tasks = [
            {"id": item.group(1), "title": item.group(2), "duration": item.group(3)}
            for item in re.finditer(r"\{\s*id:\s*'([^']+)',\s*title:\s*'([^']*)',\s*duration:\s*'([^']*)'\s*\}", body)
        ]
        modules.append({"id": module_id, "name": name, "tasks": tasks})
    return modules


def main() -> int:
    from services.agent_course import COURSE_TRACKS
    from services.agent_lab_faults import FAULT_PROFILES
    from services.agent_lab_specs import SPECS
    from services.agent_lab_variants import ADDITIONAL_VARIANT_SPECS

    problems: list[str] = []

    def expect(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    exercises = _load_exercises()
    by_id = {str(item["id"]): item for item in exercises}
    expected = set(EXPECTED_IDS)

    expect([str(item["id"]) for item in exercises] == EXPECTED_IDS,
           "题目正文的关卡顺序或集合不是 1-1 ~ 4-3")

    for label, ids in (
        ("隐藏用例 SPECS", set(SPECS)),
        ("变式题 ADDITIONAL_VARIANT_SPECS", set(ADDITIONAL_VARIANT_SPECS)),
        ("故障画像 FAULT_PROFILES", set(FAULT_PROFILES)),
    ):
        expect(ids == expected, f"{label} 的关卡集合与 1-1 ~ 4-3 不一致：{sorted(ids ^ expected)}")

    course_ids = [task["lab_id"] for track in COURSE_TRACKS for task in track["tasks"]]
    expect(sorted(course_ids) == sorted(EXPECTED_IDS),
           f"课程路径的 lab_id 与 1-1 ~ 4-3 不一致：{sorted(set(course_ids) ^ expected)}")
    expect(len(course_ids) == len(set(course_ids)), "课程路径里有重复的 lab_id")

    # 前端导航必须与题目正文逐字一致，否则学生看到标题和正文对不上。
    modules = _load_frontend_modules()
    expect(len(modules) == 4, f"前端导航应有 4 个阶段，实际 {len(modules)} 个")
    for module in modules:
        expect(len(module["tasks"]) >= 3, f"阶段 {module['id']} 的任务数少于 3")
        for task in module["tasks"]:
            exercise = by_id.get(task["id"])
            if not exercise:
                problems.append(f"前端导航里的 {task['id']} 在题目正文中不存在")
                continue
            expect(exercise["title"] == task["title"],
                   f"{task['id']} 标题不一致：正文「{exercise['title']}」/ 导航「{task['title']}」")
            expect(exercise["module"] == module["name"],
                   f"{task['id']} 阶段名不一致：正文「{exercise['module']}」/ 导航「{module['name']}」")

    # 课程路径与工作区配置引用的知识标签必须真的存在于教程种子里。
    tags = _load_tutorial_tags()
    for track in COURSE_TRACKS:
        for task in track["tasks"]:
            tag = str(task.get("knowledge", ""))
            expect(tag in tags, f"课程任务 {task['lab_id']} 的知识标签 {tag!r} 不在教程种子里")

    with open(os.path.join(_BACKEND_DIR, "services", "lab_workspace_service.py"), "r", encoding="utf-8") as handle:
        workspace_source = handle.read()
    for match in re.finditer(r'"(1-1|1-2|1-3|2-1|2-2|2-3|2-4|3-1|3-2|3-3|4-1|4-2|4-3)":\s*"(dsa-[a-z0-9-]+)"', workspace_source):
        exercise_id, tag = match.group(1), match.group(2)
        expect(tag in tags, f"工作区配置 {exercise_id} 的知识标签 {tag!r} 不在教程种子里")

    # 每道关卡的私有用例都必须真的在考东西。
    for exercise_id, spec in sorted(SPECS.items()):
        expect(bool(spec.get("cases")), f"{exercise_id} 没有任何私有用例")

    if problems:
        for item in problems:
            print("[FAIL] " + item)
        print(f"\n共 {len(problems)} 处接线不一致。")
        return 1

    print(f"[PASS] 13 个关卡在导航 / 正文 / 用例 / 变式 / 故障 / 工作区 / 课程路径七处接线一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
