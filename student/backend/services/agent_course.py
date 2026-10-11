"""项目制数据结构课程蓝图。

学习路径、教程资料与编程实验通过 material/lab_id 显式绑定，避免再次退化成
只罗列知识概念的课程目录。四个阶段依次为线性结构、树与堆、图与并查集、
算法工具箱工程化。
"""

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
