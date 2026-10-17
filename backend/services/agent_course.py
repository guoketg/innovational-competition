"""项目制数据结构课程蓝图。

学习路径、教程资料与编程实验通过 material/lab_id 显式绑定，避免再次退化成
只罗列知识概念的课程目录。四个阶段依次为线性结构、树与堆、图与并查集、
算法工具箱工程化。
"""

import json

COURSE_TRACKS = [
    {
        "name": "起步：线性结构与基础容器",
        "description": "从虚拟环境开始，亲手实现顺序表插入、单链表反转与栈求值，并把它们累积成你自己的算法工具箱。",
        "tasks": [
            {
                "topic": "项目1：实现顺序表插入",
                "knowledge": "dsa-dsa-linear-data-structures",
                "framework": "Python 标准库",
                "deliverable": "可复用的 array_insert() 函数",
                "duration": "45分钟",
                "action": "创建虚拟环境与项目骨架，用列表实现按索引插入并补全索引边界校验",
                "resource": "引导教程 + 编程实验 1-1",
                "check": "能解释插入元素时下标后移的代价，并正确拒绝越界与非整数索引",
                "lab_id": "1-1",
                "module_id": 1,
            },
            {
                "topic": "项目2：反转单链表",
                "knowledge": "dsa-dsa-linear-data-structures",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 reverse_list()",
                "duration": "60分钟",
                "action": "用节点字典表示单链表，逐节点调转 next 方向，并校验节点结构",
                "resource": "引导教程 + 编程实验 1-2",
                "check": "能说明链表为什么必须顺序访问，且反转后原链表保持不变",
                "lab_id": "1-2",
                "module_id": 1,
            },
            {
                "topic": "项目3：用栈求值逆波兰表达式",
                "knowledge": "dsa-dsa-linear-data-structures",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 eval_rpn()",
                "duration": "60分钟",
                "action": "用列表当栈实现后缀表达式求值，处理左右操作数顺序、除零与向零截断",
                "resource": "引导教程 + 编程实验 1-3",
                "check": "能解释栈的后进先出如何消除括号，并正确处理非法表达式",
                "lab_id": "1-3",
                "module_id": 1,
            },
        ],
    },
    {
        "name": "进阶：树与堆",
        "description": "用二分搜索树把查找从「逐个比对」压缩到树高，再理解堆如何用数组表示完全二叉树——排序与优先队列都建立在它上面。",
        "tasks": [
            {
                "topic": "项目4：二分搜索树：插入与查找",
                "knowledge": "dsa-binary-search-tree-insert",
                "framework": "Python 标准库",
                "deliverable": "可复用的 bst_insert() 与 bst_search()",
                "duration": "90分钟",
                "action": "用三元素列表表示二叉树，先校验「左小右大」不变式，再实现递归插入与单路径查找",
                "resource": "引导教程 + 编程实验 2-1",
                "check": "能解释为什么 BST 查找只需走一条路径，并正确拒绝重复值",
                "lab_id": "2-1",
                "module_id": 2,
            },
            {
                "topic": "项目5：二分搜索树：中序与层序遍历",
                "knowledge": "dsa-binary-search-traverse",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 bst_inorder() 与 bst_level_order()",
                "duration": "75分钟",
                "action": "实现中序递归遍历验证有序性，再用两层列表滚动实现层序遍历",
                "resource": "引导教程 + 编程实验 2-2",
                "check": "能说明中序为什么在 BST 上恰好升序，并正确输出按层的列表",
                "lab_id": "2-2",
                "module_id": 2,
            },
            {
                "topic": "项目6：堆的上浮与下沉",
                "knowledge": "dsa-heap-shift-up",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 heap_shift_up() 与 heap_shift_down()",
                "duration": "90分钟",
                "action": "推导下标 i 的父节点与子节点公式，分别实现向上的单点修复与带 size 边界的向下修复",
                "resource": "引导教程 + 编程实验 2-3",
                "check": "能说清 size 参数在堆排序中的作用，并保证不越界访问子节点",
                "lab_id": "2-3",
                "module_id": 2,
            },
            {
                "topic": "项目7：堆排序",
                "knowledge": "dsa-heap-sort",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 heap_sort()",
                "duration": "75分钟",
                "action": "先自底向上下沉建堆，再反复交换堆顶与末尾并缩小堆的范围",
                "resource": "引导教程 + 编程实验 2-4",
                "check": "能解释为什么从 n//2-1 开始建堆就足够，并验证结果严格升序",
                "lab_id": "2-4",
                "module_id": 2,
            },
        ],
    },
    {
        "name": "高级：图与并查集",
        "description": "先为图选定一种表示方式，再掌握两类基本武器：遍历回答「能不能走到」，并查集回答「是不是一组」。",
        "tasks": [
            {
                "topic": "项目8：图的邻接表表示与深度优先遍历",
                "knowledge": "dsa-graph-theory-deep",
                "framework": "Python 标准库",
                "deliverable": "可复用的 build_adjacency() 与 dfs_order()",
                "duration": "90分钟",
                "action": "用列表的列表建无向图邻接表（双向登记、去重、排序），再用显式栈做深度优先遍历",
                "resource": "引导教程 + 编程实验 3-1",
                "check": "能解释为什么必须记录已访问集合，并保证只走完起点所在的连通分量",
                "lab_id": "3-1",
                "module_id": 3,
            },
            {
                "topic": "项目9：并查集与路径压缩",
                "knowledge": "dsa-union-find-compress",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 uf_find_root()、uf_compress() 与 count_components()",
                "duration": "90分钟",
                "action": "用 parent[i]==i 表示根，实现爬根查找、路径压缩与按 size 合并，并统计连通分量",
                "resource": "引导教程 + 编程实验 3-2",
                "check": "能说明路径压缩把后续查找摊还到近乎一步，并区分「压缩返回新数组」与「原地修改」",
                "lab_id": "3-2",
                "module_id": 3,
            },
            {
                "topic": "项目10：广度优先遍历与最短路径",
                "knowledge": "dsa-graph-theory-short-path",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 bfs_shortest_path()",
                "duration": "75分钟",
                "action": "用队列按层推进，记录每个节点的前驱，命中终点后回溯出最短路径",
                "resource": "引导教程 + 编程实验 3-3",
                "check": "能解释无权图上 BFS 首次到达即最短，并正确处理不可达与起终点相同的情形",
                "lab_id": "3-3",
                "module_id": 3,
            },
        ],
    },
    {
        "name": "工程：算法工具箱工程化",
        "description": "把前三阶段写完的散装函数收拢成有统一入口的工具箱，再用排序与缓存两个场景把复杂度从口号变成可验证的工程判断。",
        "tasks": [
            {
                "topic": "项目11：把前三阶段函数收拢成 toolbox 包",
                "knowledge": "dsa-dsa-basic-algorithm",
                "framework": "Python 标准库",
                "deliverable": "带统一入口的 toolbox（5 个算法 + 名称分发）",
                "duration": "90分钟",
                "action": "把阶段一到三的函数搬进同一文件，用注册表把「名称 → 函数」集中管理，再实现调用与清单两个接口",
                "resource": "引导教程 + 编程实验 4-1",
                "check": "未知名称与非法参数都被拒绝，被调用函数自身抛出的异常能原样透传",
                "lab_id": "4-1",
                "module_id": 4,
            },
            {
                "topic": "项目12：排序算法的性能基准与复杂度验证",
                "knowledge": "dsa-merge-sort",
                "framework": "Python 标准库",
                "deliverable": "在算法工具箱中加入 merge_sorted()、merge_sort() 与 is_sorted_ascending()",
                "duration": "90分钟",
                "action": "实现归并的两个有序段合并与递归分治，并写出可复用的有序性断言工具",
                "resource": "引导教程 + 编程实验 4-2",
                "check": "能对比堆排序与归并排序的时间与空间代价，并用断言验证排序结果",
                "lab_id": "4-2",
                "module_id": 4,
            },
            {
                "topic": "毕业项目：缓存与查找：LRU / 哈希表",
                "knowledge": "dsa-dsa-hash-table",
                "framework": "Python 标准库",
                "deliverable": "可复用的 lru_simulate() 与 two_sum()",
                "duration": "120分钟",
                "action": "用哈希表加顺序维护 LRU 缓存的新鲜度与淘汰，并把两数之和从两重循环降到一次遍历",
                "resource": "引导教程 + 编程实验 4-3",
                "check": "能说明哈希表用一次计算换掉整轮遍历的代价与前提，并正确实现淘汰策略",
                "lab_id": "4-3",
                "module_id": 4,
            },
        ],
    },
]

TRACK_NAMES = [track["name"] for track in COURSE_TRACKS]

CURRICULUM_VERSION_V1 = "agent-project-path-v1"
CURRICULUM_VERSION = "agent-project-path-v2"

LEVEL_LABELS = {
    "beginner": "基础薄弱",
    "intermediate": "有一定基础",
    "advanced": "较为熟练",
}

DEPTH_LEVELS = {
    "快速": "精简",
    "标准": "标准",
    "深入": "深入",
}


def _parse_minutes(duration) -> int:
    """把「45分钟」这类时长文本转成分钟数，解析失败时按 60 分钟兜底。"""
    try:
        return int(str(duration).replace("分钟", "").strip())
    except (TypeError, ValueError):
        return 60


def _load_prerequisites() -> dict:
    """读取知识点先修依赖表；读取失败时退化为空表（保持课程原有顺序）。"""
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dsa_prerequisites.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("prerequisites", {}) or {}
    except Exception:
        return {}


def _mastery_thresholds() -> tuple:
    """与教学策略服务保持同一套掌握度阈值。"""
    try:
        from services.teaching_policy_service import MASTERY_HIGH, MASTERY_LOW
        return MASTERY_HIGH, MASTERY_LOW
    except Exception:
        return 0.7, 0.4


def _reorder_phase_tasks(tasks: list, prereq_map: dict, mastery: dict) -> list:
    """阶段内重排：先满足先修依赖，同一批可学的任务里薄弱项优先、已掌握项后置。

    同阶段允许出现相同 knowledge 的多个项目（如阶段一的三个线性结构项目），
    因此按任务下标建图，而不是按知识点建图。
    """
    mastery_high, mastery_low = _mastery_thresholds()

    count = len(tasks)
    indegree = [0] * count
    children = [[] for _ in range(count)]

    for child_index, task in enumerate(tasks):
        parents = set()
        for prerequisite in prereq_map.get(task.get("knowledge"), []):
            for parent_index, other in enumerate(tasks):
                if parent_index != child_index and other.get("knowledge") == prerequisite:
                    parents.add(parent_index)
        indegree[child_index] = len(parents)
        for parent_index in parents:
            children[parent_index].append(child_index)

    def priority(index: int) -> tuple:
        score = mastery.get(tasks[index].get("knowledge"))
        if score is None:
            rank = 1
        elif score < mastery_low:
            rank = 0
        elif score >= mastery_high:
            rank = 2
        else:
            rank = 1
        return (rank, index)

    ready = sorted([i for i in range(count) if indegree[i] == 0], key=priority)
    ordered = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort(key=priority)

    # 依赖表若成环，未排出的任务按课程原顺序补齐，保证结果确定。
    ordered.extend(i for i in range(count) if i not in ordered)
    return [tasks[i] for i in ordered]


def _build_personalization_summary(level_profile: dict, total_minutes: int, skipped: list,
                                   reordered_phases: int, learning_depth: str) -> str:
    """生成一句用户能直接看懂的话，说明这条路径为什么这样排。"""
    source = level_profile.get("source")
    label = level_profile.get("level_label") or LEVEL_LABELS.get(level_profile.get("level"), "有一定基础")
    parts = []

    if source == "diagnostic":
        rate = level_profile.get("correct_rate")
        if rate is None:
            parts.append(f"根据你的测评结果，判断你目前属于「{label}」。")
        else:
            parts.append(f"根据你的测评结果（正确率 {round(float(rate) * 100)}%），判断你目前属于「{label}」。")
    elif source == "mastery":
        parts.append(f"根据你已有的练习记录，判断你目前属于「{label}」。")
    elif source == "legacy":
        parts.append("这条路线是早期生成的固定骨架，还没有按你的水平调整；点「重新生成」即可获得个性化版本。")
    else:
        parts.append(f"你跳过了测评，先按注册信息估计为「{label}」，这份安排会随着你的练习记录自动校正。")

    if skipped:
        parts.append(f"其中 {len(skipped)} 个已掌握的项目被标记为「可快速过」，任务保留但学时压缩。")
    weak_count = len(level_profile.get("weak_tags") or [])
    if weak_count:
        parts.append(f"检测到 {weak_count} 个薄弱知识点，相关项目已尽量往前排。")
    if reordered_phases:
        parts.append(f"有 {reordered_phases} 个阶段调整了项目顺序。")
    parts.append(f"按「{learning_depth}」深度，预计总学时约 {total_minutes} 分钟。")
    return "".join(parts)


def plan_course_path(selected_tracks: list[str], level_profile: dict = None,
                     learning_depth: str = "标准") -> dict:
    """按学生水平编排项目制学习路径（v2）。

    骨架保持不变（4 阶段 12 个项目），只调整三件事：
    - skip：已掌握的项目标记为可快速过，压缩学时但不删除任务；
    - reorder：阶段内按先修依赖 + 薄弱项优先重排；
    - depth：把学习深度标注到每个任务上。
    """
    level_profile = level_profile or {}
    mastery = level_profile.get("mastery") or {}
    mastered_tags = set(level_profile.get("mastered_tags") or [])
    weak_tags = set(level_profile.get("weak_tags") or [])
    mastery_high, _ = _mastery_thresholds()
    prereq_map = _load_prerequisites()
    depth_level = DEPTH_LEVELS.get(learning_depth, learning_depth or "标准")

    selected = set(selected_tracks)
    phases = []
    day = 1
    total_minutes = 0
    skipped_topics = []
    reordered_phases = 0

    for track in COURSE_TRACKS:
        if track["name"] not in selected:
            continue

        source_tasks = [dict(task) for task in track["tasks"]]
        ordered_tasks = _reorder_phase_tasks(source_tasks, prereq_map, mastery)
        if [task["topic"] for task in ordered_tasks] != [task["topic"] for task in source_tasks]:
            reordered_phases += 1

        tasks = []
        for source in ordered_tasks:
            knowledge = source.get("knowledge")
            score = mastery.get(knowledge)
            if score is None and knowledge in mastered_tags:
                score = 1.0
            if score is None and knowledge in weak_tags:
                score = 0.0

            task = {"day": day, **source}
            task["depth_level"] = depth_level
            base_minutes = _parse_minutes(source.get("duration"))

            if score is not None and score >= mastery_high:
                compressed = max(15, int(round(base_minutes * 0.5)))
                task["skippable"] = True
                task["skip_reason"] = f"掌握度 {round(score * 100)}%，可以快速过一遍"
                task["original_duration"] = source.get("duration")
                task["duration"] = f"{compressed}分钟"
                base_minutes = compressed
                skipped_topics.append(source.get("topic"))
            else:
                task["skippable"] = False

            total_minutes += base_minutes
            tasks.append(task)
            day += 1

        phases.append({
            "name": track["name"],
            "description": track["description"],
            "tasks": tasks,
        })

    return {
        "curriculum_version": CURRICULUM_VERSION,
        "phases": phases,
        "estimated_total_days": day - 1,
        "estimated_total_minutes": total_minutes,
        "learning_depth": learning_depth,
        "depth_level": depth_level,
        "level_profile": level_profile,
        "applied_operators": {
            "skip": {
                "applied": bool(skipped_topics),
                "count": len(skipped_topics),
                "topics": skipped_topics,
            },
            "reorder": {
                "applied": reordered_phases > 0,
                "phase_count": reordered_phases,
            },
            "depth": {"level": depth_level},
        },
        "personalization_summary": _build_personalization_summary(
            level_profile, total_minutes, skipped_topics, reordered_phases, learning_depth
        ),
        "weekly_goals": [
            "每次学习都运行代码，保存一次可复现结果",
            "先完成最小版本，再补边界、错误处理和测试",
            "每周至少完成一次代码解释或故障修复",
        ],
        "key_milestones": [
            "能手写顺序表插入、链表反转与栈求值",
            "能手写二分搜索树的插入查找与两种遍历",
            "能手写堆的上浮下沉与堆排序",
            "能建图并完成 DFS、BFS 最短路与并查集",
            "交付带统一入口、可复用的算法工具箱",
        ],
        "tips": "按项目顺序学习。教程负责带你敲出第一版，实验室负责检验你能否独立补全、解释和修复。"
                "标注「可快速过」的项目说明你已经掌握，快速验证后即可继续。",
        "modules_selected": selected_tracks,
    }


def build_course_path(selected_tracks: list[str], learning_depth: str = "标准") -> dict:
    """按课程既定依赖顺序构建项目制学习路径。"""
    selected = set(selected_tracks)
    phases = []
    day = 1
    for track in COURSE_TRACKS:
        if track["name"] not in selected:
            continue
        tasks = []
        for source in track["tasks"]:
            task = {"day": day, **source}
            tasks.append(task)
            day += 1
        phases.append({
            "name": track["name"],
            "description": track["description"],
            "tasks": tasks,
        })

    return {
        "curriculum_version": "agent-project-path-v1",
        "phases": phases,
        "estimated_total_days": day - 1,
        "learning_depth": learning_depth,
        "weekly_goals": [
            "每次学习都运行代码，保存一次可复现结果",
            "先完成最小版本，再补边界、错误处理和测试",
            "每周至少完成一次代码解释或故障修复",
        ],
        "key_milestones": [
            "能手写顺序表插入、链表反转与栈求值",
            "能手写二分搜索树的插入查找与两种遍历",
            "能手写堆的上浮下沉与堆排序",
            "能建图并完成 DFS、BFS 最短路与并查集",
            "交付带统一入口、可复用的算法工具箱",
        ],
        "tips": "按项目顺序学习。教程负责带你敲出第一版，实验室负责检验你能否独立补全、解释和修复。",
        "modules_selected": selected_tracks,
    }
