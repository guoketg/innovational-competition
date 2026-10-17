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

# 课程级知识点清单：知识图谱的唯一节点来源。
# 节点全部来自 data/dsa_tutorial_seed.json 的 44 篇结构化教程（tag 一一对应），
# 这样图谱节点、教程、题库三者能直接用同一个 tag 对齐。
# in_course=True 的节点对应 12 个实训项目；其余是同一门课的拓展节点，
# 只有学到附近时才会出现在「我的图谱」里。
# 注意：前 11 个节点的 name 必须保持原样，题库 knowledge_tag 依赖这些中文名做映射。
COURSE_KNOWLEDGE_POINTS = [
    # ---------- 核心课程节点（对应 12 个实训项目，name 不可改） ----------
    {"tag": "dsa-dsa-linear-data-structures", "name": "线性结构：顺序表 / 链表 / 栈", "module": "核心教程", "in_course": True},
    {"tag": "dsa-binary-search-tree-insert", "name": "二分搜索树：插入与查找", "module": "二分搜索树", "in_course": True},
    {"tag": "dsa-binary-search-traverse", "name": "二分搜索树：中序与层序遍历", "module": "二分搜索树", "in_course": True},
    {"tag": "dsa-heap-shift-up", "name": "堆：上浮与下沉", "module": "堆", "in_course": True},
    {"tag": "dsa-heap-sort", "name": "堆排序", "module": "堆", "in_course": True},
    {"tag": "dsa-graph-theory-deep", "name": "图的表示与深度优先遍历", "module": "图论", "in_course": True},
    {"tag": "dsa-union-find-compress", "name": "并查集与路径压缩", "module": "并查集", "in_course": True},
    {"tag": "dsa-graph-theory-short-path", "name": "广度优先遍历与最短路径", "module": "图论", "in_course": True},
    {"tag": "dsa-dsa-basic-algorithm", "name": "算法工具箱：统一入口与分发", "module": "核心教程", "in_course": True},
    {"tag": "dsa-merge-sort", "name": "归并排序与性能基准", "module": "排序算法", "in_course": True},
    {"tag": "dsa-dsa-hash-table", "name": "哈希表与 LRU 缓存", "module": "核心教程", "in_course": True},
    # ---------- 课程导论 ----------
    {"tag": "dsa-data-structures-tutorial", "name": "数据结构与算法总览", "module": "核心教程", "in_course": False},
    {"tag": "dsa-dsa-intro", "name": "数据结构与算法简介", "module": "核心教程", "in_course": False},
    # ---------- 基础结构与算法思想 ----------
    {"tag": "dsa-dsa-tree", "name": "树形结构", "module": "核心教程", "in_course": False},
    {"tag": "dsa-dsa-graph", "name": "图论结构", "module": "核心教程", "in_course": False},
    {"tag": "dsa-dsa-divide-and-conquer", "name": "分治算法", "module": "核心教程", "in_course": False},
    {"tag": "dsa-dsa-greedy-algorithm", "name": "贪心算法", "module": "核心教程", "in_course": False},
    {"tag": "dsa-dsa-dynamic-programming", "name": "动态规划", "module": "核心教程", "in_course": False},
    {"tag": "dsa-dsa-advanced-tree", "name": "高级树结构", "module": "核心教程", "in_course": False},
    {"tag": "dsa-dsa-advanced-graph", "name": "高级图算法", "module": "核心教程", "in_course": False},
    # ---------- 排序算法 ----------
    {"tag": "dsa-dsa-sorting", "name": "排序算法总览", "module": "排序算法", "in_course": False},
    {"tag": "dsa-insertion-sort", "name": "插入排序", "module": "排序算法", "in_course": False},
    {"tag": "dsa-shell-sort", "name": "希尔排序", "module": "排序算法", "in_course": False},
    {"tag": "dsa-random-quick-sort", "name": "快速排序（随机化）", "module": "排序算法", "in_course": False},
    {"tag": "dsa-2way-quick-sort", "name": "双路快速排序", "module": "排序算法", "in_course": False},
    {"tag": "dsa-3way-qiuck-sort", "name": "三路快速排序", "module": "排序算法", "in_course": False},
    {"tag": "dsa-sorting-algorithm-derivative-problem", "name": "排序衍生问题", "module": "排序算法", "in_course": False},
    # ---------- 堆 ----------
    {"tag": "dsa-heap-storage", "name": "堆的基本存储", "module": "堆", "in_course": False},
    {"tag": "dsa-heap-shift-down", "name": "堆：下沉调整", "module": "堆", "in_course": False},
    {"tag": "dsa-heap-sort-optimization", "name": "优化堆排序", "module": "堆", "in_course": False},
    {"tag": "dsa-heap-index", "name": "索引堆及其优化", "module": "堆", "in_course": False},
    # ---------- 二分搜索树 ----------
    {"tag": "dsa-binary-search-tree", "name": "二分搜索树基础", "module": "二分搜索树", "in_course": False},
    {"tag": "dsa-binary-search-tree-search", "name": "二分搜索树查找", "module": "二分搜索树", "in_course": False},
    {"tag": "dsa-binary-search-level-traverse", "name": "二分搜索树层序遍历", "module": "二分搜索树", "in_course": False},
    {"tag": "dsa-binary-search-remove", "name": "二分搜索树删除节点", "module": "二分搜索树", "in_course": False},
    {"tag": "dsa-binary-search-feature", "name": "二分搜索树的特性", "module": "二分搜索树", "in_course": False},
    # ---------- 并查集 ----------
    {"tag": "dsa-union-find-basic", "name": "并查集基础", "module": "并查集", "in_course": False},
    {"tag": "dsa-union-find-quick", "name": "并查集快速查找", "module": "并查集", "in_course": False},
    {"tag": "dsa-union-find-quick-merge", "name": "并查集快速合并", "module": "并查集", "in_course": False},
    {"tag": "dsa-union-find-size", "name": "并查集按 size 优化", "module": "并查集", "in_course": False},
    {"tag": "dsa-union-find-rank", "name": "并查集按 rank 优化", "module": "并查集", "in_course": False},
    # ---------- 图论 ----------
    {"tag": "dsa-graph-theory", "name": "图论基础与表示", "module": "图论", "in_course": False},
    {"tag": "dsa-graph-theory-iter", "name": "相邻节点迭代器", "module": "图论", "in_course": False},
    {"tag": "dsa-graph-theory-path", "name": "寻路算法", "module": "图论", "in_course": False},
]


# 知识点属性：难度 1~5、认知层次（记忆/理解/应用/分析）、建议学时、考纲权重（原始分，之后归一化）。
# 这些属性是课程团队维护的静态事实，不依赖 LLM 重新生成；图谱生成时直接带上，
# 旧图谱读取时也会由路由层按需补齐。
DIFFICULTY_LABELS = {
    1: "入门",
    2: "基础",
    3: "进阶",
    4: "较难",
    5: "挑战",
}

KNOWLEDGE_META = {
    # ---------- 核心课程节点 ----------
    "dsa-dsa-linear-data-structures": {
        "difficulty": 2, "cognitive_level": "应用", "study_minutes": 90, "exam_weight_raw": 8,
        "misconceptions": ["把顺序表和链表的随机访问复杂度记反", "认为链表插入一定比顺序表快（忽略了定位成本）"],
    },
    "dsa-binary-search-tree-insert": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 75, "exam_weight_raw": 7,
        "misconceptions": ["插入时忘记维护 size 或子树关系", "认为插入顺序不影响树的高度"],
    },
    "dsa-binary-search-traverse": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 60, "exam_weight_raw": 6,
        "misconceptions": ["把中序遍历能有序输出误当成前序遍历的性质", "层序遍历误用递归实现"],
    },
    "dsa-heap-shift-up": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 60, "exam_weight_raw": 6,
        "misconceptions": ["上浮时只比较一次就停止", "混淆上浮与下沉的触发场景"],
    },
    "dsa-heap-sort": {
        "difficulty": 4, "cognitive_level": "应用", "study_minutes": 75, "exam_weight_raw": 7,
        "misconceptions": ["建堆后直接取根却忘了交换到末尾", "认为堆排序是稳定排序"],
    },
    "dsa-graph-theory-deep": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 75, "exam_weight_raw": 7,
        "misconceptions": ["DFS 忘记标记已访问导致死循环", "把邻接表的空间复杂度算成 O(V^2)"],
    },
    "dsa-union-find-compress": {
        "difficulty": 4, "cognitive_level": "应用", "study_minutes": 60, "exam_weight_raw": 6,
        "misconceptions": ["路径压缩写成只压缩当前节点", "find 没有返回值导致父指针丢失"],
    },
    "dsa-graph-theory-short-path": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 75, "exam_weight_raw": 8,
        "misconceptions": ["把 BFS 最短路用于带权图", "入队时机错误导致重复访问"],
    },
    "dsa-dsa-basic-algorithm": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 45, "exam_weight_raw": 4,
        "misconceptions": ["把工具入口当成具体算法实现", "混淆不同算法模板的适用条件"],
    },
    "dsa-merge-sort": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 75, "exam_weight_raw": 7,
        "misconceptions": ["归并时临时数组下标越界", "认为归并排序可以原地完成且空间 O(1)"],
    },
    "dsa-dsa-hash-table": {
        "difficulty": 4, "cognitive_level": "应用", "study_minutes": 75, "exam_weight_raw": 7,
        "misconceptions": ["冲突处理方式与探查序列记混", "认为哈希表最坏情况仍是 O(1)"],
    },
    # ---------- 课程导论 ----------
    "dsa-data-structures-tutorial": {
        "difficulty": 1, "cognitive_level": "记忆", "study_minutes": 30, "exam_weight_raw": 2,
        "misconceptions": ["把逻辑结构与存储结构混为一谈"],
    },
    "dsa-dsa-intro": {
        "difficulty": 1, "cognitive_level": "记忆", "study_minutes": 30, "exam_weight_raw": 2,
        "misconceptions": ["用运行时间直接比较算法优劣而忽略输入规模"],
    },
    # ---------- 基础结构与算法思想 ----------
    "dsa-dsa-tree": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["树的深度与高度定义混淆", "把节点的度与树的度混为一谈"],
    },
    "dsa-dsa-graph": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["有向图与无向图的度计算混淆", "邻接矩阵与邻接表适用场景记反"],
    },
    "dsa-dsa-divide-and-conquer": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 75, "exam_weight_raw": 5,
        "misconceptions": ["递归出口设计错误导致栈溢出", "合并步骤复杂度估计错误"],
    },
    "dsa-dsa-greedy-algorithm": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 60, "exam_weight_raw": 5,
        "misconceptions": ["认为贪心在所有问题上都能得到最优解", "反例构造时只看局部"],
    },
    "dsa-dsa-dynamic-programming": {
        "difficulty": 5, "cognitive_level": "分析", "study_minutes": 120, "exam_weight_raw": 8,
        "misconceptions": ["状态定义遗漏维度", "初始化与遍历顺序导致状态被重复使用"],
    },
    "dsa-dsa-advanced-tree": {
        "difficulty": 5, "cognitive_level": "分析", "study_minutes": 90, "exam_weight_raw": 5,
        "misconceptions": ["旋转操作方向记反", "平衡因子更新遗漏"],
    },
    "dsa-dsa-advanced-graph": {
        "difficulty": 5, "cognitive_level": "分析", "study_minutes": 90, "exam_weight_raw": 5,
        "misconceptions": ["最小生成树与最短路径算法混用", "负权边场景选错算法"],
    },
    # ---------- 排序算法 ----------
    "dsa-dsa-sorting": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 45, "exam_weight_raw": 3,
        "misconceptions": ["把稳定性与时间复杂度混为一谈", "认为所有 O(n log n) 排序都稳定"],
    },
    "dsa-insertion-sort": {
        "difficulty": 2, "cognitive_level": "应用", "study_minutes": 45, "exam_weight_raw": 4,
        "misconceptions": ["内层循环边界写错导致覆盖元素", "认为插入排序在任何数据上都慢"],
    },
    "dsa-shell-sort": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["增量序列选择与复杂度关系记混", "认为希尔排序稳定"],
    },
    "dsa-random-quick-sort": {
        "difficulty": 4, "cognitive_level": "应用", "study_minutes": 75, "exam_weight_raw": 6,
        "misconceptions": ["分区边界处理导致死循环", "随机化后仍认为最坏复杂度消失"],
    },
    "dsa-2way-quick-sort": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["双指针交换条件写反", "重复元素多时退化为单路分区"],
    },
    "dsa-3way-qiuck-sort": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["三路分区区间边界混淆", "把等于基准的元素重复交换"],
    },
    "dsa-sorting-algorithm-derivative-problem": {
        "difficulty": 4, "cognitive_level": "应用", "study_minutes": 75, "exam_weight_raw": 5,
        "misconceptions": ["直接套排序模板而忽略题目额外约束", "没有利用部分有序信息"],
    },
    # ---------- 堆 ----------
    "dsa-heap-storage": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 45, "exam_weight_raw": 4,
        "misconceptions": ["父子节点下标换算公式记错", "认为堆的数组存储必须从 0 开始"],
    },
    "dsa-heap-shift-down": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 45, "exam_weight_raw": 4,
        "misconceptions": ["下沉时选错较大的孩子", "越界判断遗漏"],
    },
    "dsa-heap-sort-optimization": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["认为优化后的堆排序稳定", "忽略建堆阶段与排序阶段的复杂度差异"],
    },
    "dsa-heap-index": {
        "difficulty": 5, "cognitive_level": "分析", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["索引堆中数据下标与索引下标混淆", "交换时没有同步反向索引"],
    },
    # ---------- 二分搜索树 ----------
    "dsa-binary-search-tree": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 45, "exam_weight_raw": 3,
        "misconceptions": ["认为 BST 的查找复杂度恒为 O(log n)", "中序有序与 BST 定义混为一谈"],
    },
    "dsa-binary-search-tree-search": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 45, "exam_weight_raw": 4,
        "misconceptions": ["递归查找没有返回子树结果", "比较方向写反"],
    },
    "dsa-binary-search-level-traverse": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 45, "exam_weight_raw": 4,
        "misconceptions": ["层序遍历忘记记录每层长度", "用栈代替队列"],
    },
    "dsa-binary-search-remove": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 60, "exam_weight_raw": 5,
        "misconceptions": ["删除双子节点时直接断开导致树断裂", "后继节点替换后未删除原后继"],
    },
    "dsa-binary-search-feature": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 45, "exam_weight_raw": 4,
        "misconceptions": ["把 BST 的前驱后继与中序相邻节点混淆", "认为删除操作不改变树结构"],
    },
    # ---------- 并查集 ----------
    "dsa-union-find-basic": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 40, "exam_weight_raw": 3,
        "misconceptions": ["把并查集当成普通集合使用", "认为 union 后需要重建全部指针"],
    },
    "dsa-union-find-quick": {
        "difficulty": 2, "cognitive_level": "应用", "study_minutes": 35, "exam_weight_raw": 3,
        "misconceptions": ["quick find 的合并代价估计错误", "把 id 数组与父指针数组混淆"],
    },
    "dsa-union-find-quick-merge": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 40, "exam_weight_raw": 4,
        "misconceptions": ["合并时只改一个节点的父指针", "查找时未沿父链上溯到根"],
    },
    "dsa-union-find-size": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 40, "exam_weight_raw": 4,
        "misconceptions": ["按 size 合并时没有累加大小", "把 size 记成深度"],
    },
    "dsa-union-find-rank": {
        "difficulty": 4, "cognitive_level": "分析", "study_minutes": 40, "exam_weight_raw": 4,
        "misconceptions": ["rank 相等时合并方向处理错误", "rank 与 size 的更新规则混用"],
    },
    # ---------- 图论 ----------
    "dsa-graph-theory": {
        "difficulty": 2, "cognitive_level": "理解", "study_minutes": 60, "exam_weight_raw": 4,
        "misconceptions": ["稠密图与稀疏图的存储选择记反", "把连通分量与强连通分量混淆"],
    },
    "dsa-graph-theory-iter": {
        "difficulty": 3, "cognitive_level": "应用", "study_minutes": 40, "exam_weight_raw": 3,
        "misconceptions": ["迭代器越界访问", "遍历时修改图结构导致结果不稳定"],
    },
    "dsa-graph-theory-path": {
        "difficulty": 4, "cognitive_level": "应用", "study_minutes": 75, "exam_weight_raw": 5,
        "misconceptions": ["记录路径时只存父节点却未回溯", "把可达性与最短路径混为一谈"],
    },
}

# 包含关系（part-of）：父节点 → 子节点。用于表达「排序算法总览包含插入排序」这类
# 目录层级，与先修关系严格区分——part-of 不参与先修判定，也不会成环。
PART_OF_MAP = {
    "dsa-dsa-tree": ["dsa-binary-search-tree", "dsa-dsa-advanced-tree"],
    "dsa-dsa-graph": ["dsa-graph-theory", "dsa-dsa-advanced-graph"],
    "dsa-dsa-sorting": [
        "dsa-insertion-sort", "dsa-shell-sort", "dsa-random-quick-sort",
        "dsa-2way-quick-sort", "dsa-3way-qiuck-sort",
        "dsa-sorting-algorithm-derivative-problem", "dsa-merge-sort",
    ],
    "dsa-heap-storage": [
        "dsa-heap-shift-up", "dsa-heap-shift-down",
        "dsa-heap-sort", "dsa-heap-sort-optimization", "dsa-heap-index",
    ],
    "dsa-binary-search-tree": [
        "dsa-binary-search-tree-insert", "dsa-binary-search-traverse",
        "dsa-binary-search-tree-search", "dsa-binary-search-level-traverse",
        "dsa-binary-search-remove", "dsa-binary-search-feature",
    ],
    "dsa-union-find-basic": [
        "dsa-union-find-compress", "dsa-union-find-quick",
        "dsa-union-find-quick-merge", "dsa-union-find-size", "dsa-union-find-rank",
    ],
    "dsa-graph-theory": [
        "dsa-graph-theory-deep", "dsa-graph-theory-short-path",
        "dsa-graph-theory-iter", "dsa-graph-theory-path",
    ],
}


def course_knowledge_points() -> list:
    """返回课程级知识点名单（tag + 规范展示名），供知识图谱使用。"""
    return [dict(item) for item in COURSE_KNOWLEDGE_POINTS]


def course_point_names() -> dict:
    """tag -> 课程规范展示名。"""
    return {item["tag"]: item["name"] for item in COURSE_KNOWLEDGE_POINTS}


def project_index(selected_tracks: list = None) -> dict:
    """tag -> 该知识点对应的课程项目列表（含真实 lab/module/资源）。

    用于「补先修复用已有项目」：前置知识点只要在课程里有项目，就不再额外
    造一个重复的文本任务，而是把已有项目标成补先修重点。
    """
    selected = set(selected_tracks) if selected_tracks else None
    index = {}
    for track in COURSE_TRACKS:
        if selected is not None and track["name"] not in selected:
            continue
        for task in track["tasks"]:
            tag = task.get("knowledge")
            if not tag:
                continue
            index.setdefault(tag, []).append({
                "phase_name": track["name"],
                "topic": task["topic"],
                "lab_id": task.get("lab_id"),
                "module_id": task.get("module_id"),
                "duration": task.get("duration"),
                "resource": task.get("resource"),
            })
    return index


def _enrich_knowledge_points() -> None:
    """把静态属性、教学资源、包含关系写回课程知识点清单。

    - exam_weight 按原始分归一化，总和为 1，便于路径排序时直接比较重要性；
    - taught_by / assessed_by 用课程里真实存在的教程与实训项目推导，不编造外部资源；
    - part_of 记录父节点，供图谱生成 part-of 边时反查。
    """
    projects = project_index()
    tags = {item["tag"] for item in COURSE_KNOWLEDGE_POINTS}
    parents = {}
    for parent, children in PART_OF_MAP.items():
        if parent not in tags:
            continue
        for child in children:
            if child in tags and child != parent:
                parents.setdefault(child, []).append(parent)
    total_raw = sum(
        (KNOWLEDGE_META.get(item["tag"]) or {}).get("exam_weight_raw") or 0
        for item in COURSE_KNOWLEDGE_POINTS
    ) or 1.0

    for item in COURSE_KNOWLEDGE_POINTS:
        meta = KNOWLEDGE_META.get(item["tag"]) or {}
        raw = float(meta.get("exam_weight_raw") or 0)
        difficulty = int(meta.get("difficulty") or 3)
        item["difficulty"] = difficulty
        item["difficulty_label"] = DIFFICULTY_LABELS.get(difficulty, "进阶")
        item["cognitive_level"] = meta.get("cognitive_level") or "应用"
        item["study_minutes"] = int(meta.get("study_minutes") or 60)
        item["exam_weight_raw"] = round(raw, 2)
        item["exam_weight"] = round(raw / total_raw, 4)
        item["misconceptions"] = list(meta.get("misconceptions") or [])
        item["part_of"] = parents.get(item["tag"], [])
        item["taught_by"] = [{
            "type": "tutorial",
            "name": f"{item['name']} · 课程教程",
            "ref": item["tag"],
        }]
        assessed = [{
            "type": "quiz",
            "name": "知识点测评题",
            "ref": item["tag"],
        }]
        for project in projects.get(item["tag"]) or []:
            assessed.append({
                "type": "lab",
                "name": project.get("topic") or "",
                "ref": project.get("lab_id") or project.get("module_id") or "",
            })
        item["assessed_by"] = assessed


def part_of_edges() -> list:
    """课程目录的包含关系边（父 → 子），供知识图谱与前端展示使用。"""
    tags = {item["tag"] for item in COURSE_KNOWLEDGE_POINTS}
    edges = []
    for parent, children in PART_OF_MAP.items():
        if parent not in tags:
            continue
        for child in children:
            if child not in tags or child == parent:
                continue
            edges.append({
                "source": parent,
                "target": child,
                "relation": "part-of",
                "reason": "课程目录层级",
                "origin": "expert",
                "confidence": 1.0,
                "evidence": "课程知识点分册结构",
                "review_status": "accepted",
            })
    return edges


_enrich_knowledge_points()

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

# 路径编排策略：四种候选方案（#44 候选生成 + 多目标排序）
PATH_STRATEGIES = ("balanced", "weak_first", "target_first", "time_saver")

STRATEGY_LABELS = {
    "balanced": "均衡推进",
    "weak_first": "补弱优先",
    "target_first": "目标优先",
    "time_saver": "省时优先",
}

MODE_TO_STRATEGY = {
    "均衡": "balanced",
    "补弱优先": "weak_first",
    "目标优先": "target_first",
    "省时优先": "time_saver",
}

# 每种策略对五项指标的权重；权重之和为 1，便于直接比较分数。
STRATEGY_WEIGHTS = {
    "balanced": {"prereq": 0.30, "target": 0.20, "weak": 0.20, "time": 0.15, "smooth": 0.15},
    "weak_first": {"prereq": 0.25, "target": 0.10, "weak": 0.40, "time": 0.10, "smooth": 0.15},
    "target_first": {"prereq": 0.25, "target": 0.45, "weak": 0.10, "time": 0.10, "smooth": 0.10},
    "time_saver": {"prereq": 0.20, "target": 0.10, "weak": 0.05, "time": 0.50, "smooth": 0.15},
}


def knowledge_meta_index() -> dict:
    """tag -> 知识点属性快照（难度/认知层次/建议学时/考纲权重/常见误区）。"""
    return {
        item["tag"]: {
            "difficulty": item.get("difficulty"),
            "difficulty_label": item.get("difficulty_label"),
            "cognitive_level": item.get("cognitive_level"),
            "study_minutes": item.get("study_minutes"),
            "exam_weight": item.get("exam_weight"),
            "misconceptions": list(item.get("misconceptions") or []),
        }
        for item in COURSE_KNOWLEDGE_POINTS
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


def _reorder_phase_tasks(tasks: list, prereq_map: dict, mastery: dict,
                         readiness: dict = None, strategy: str = "balanced",
                         target_tags: set = None, error_tags: set = None,
                         uncertain_tags: set = None) -> list:
    """阶段内重排：先满足先修依赖，同一批可学的任务里按策略决定先后。

    同阶段允许出现相同 knowledge 的多个项目（如阶段一的三个线性结构项目），
    因此按任务下标建图，而不是按知识点建图。

    传入 readiness（图谱就绪度）时，被前置知识卡住的任务会排到同批可学任务之后，
    避免把「还学不动」的项目排在最前面。

    strategy：balanced 均衡 / weak_first 补弱优先 / target_first 目标优先 /
    time_saver 省时优先。目标节点、错误画像、掌握度不确定度会改变同批任务的先后。
    """
    mastery_high, mastery_low = _mastery_thresholds()
    readiness = readiness or {}
    target_tags = target_tags or set()
    error_tags = error_tags or set()
    uncertain_tags = uncertain_tags or set()
    strategy = strategy if strategy in PATH_STRATEGIES else "balanced"

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
        knowledge = tasks[index].get("knowledge")
        score = mastery.get(knowledge)
        if (readiness.get(knowledge) or {}).get("state") == "blocked":
            rank = 40  # 前置没打牢：排到本阶段同一批可学任务之后
        elif score is None:
            rank = 10
        elif score < mastery_low:
            rank = 0
        elif score >= mastery_high:
            rank = 30
        else:
            rank = 20

        is_target = knowledge in target_tags
        is_error = knowledge in error_tags
        needs_check = knowledge in uncertain_tags

        if strategy == "target_first":
            if is_target:
                rank -= 30
            if is_error:
                rank -= 6
        elif strategy == "weak_first":
            if is_error:
                rank -= 12
            if needs_check:
                rank -= 4
            if is_target:
                rank -= 5
        elif strategy == "time_saver":
            if score is not None and score >= mastery_high:
                rank -= 15  # 已掌握的先快速过掉，把时间省给难点
            if is_target:
                rank -= 6
        else:
            if is_target:
                rank -= 8
            if is_error:
                rank -= 4
            if needs_check:
                rank -= 2
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
                                   reordered_phases: int, learning_depth: str,
                                   graph_info: dict = None, budget_info: dict = None) -> str:
    """生成一句用户能直接看懂的话，说明这条路径为什么这样排。"""
    source = level_profile.get("source")
    label = level_profile.get("level_label") or LEVEL_LABELS.get(level_profile.get("level"), "有一定基础")
    graph_info = graph_info or {}
    budget_info = budget_info or {}
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

    target_names = level_profile.get("target_names") or []
    if target_names:
        shown = "、".join(name for name in target_names[:3] if name)
        more = f"等 {len(target_names)} 个" if len(target_names) > 3 else ""
        parts.append(f"你指定的目标知识点（{shown}{more}）已优先排进路线。")
    error_profile = level_profile.get("error_profile") or {}
    error_items = error_profile.get("top_error_tags") or []
    if error_items:
        names = "、".join(item.get("name") or item.get("tag") for item in error_items[:3])
        parts.append(f"根据错题记录，最需要纠正的是「{names}」，相关任务已往前排。")
    uncertainty = level_profile.get("mastery_uncertainty") or {}
    check_items = uncertainty.get("top_uncertain_tags") or []
    if check_items:
        parts.append(f"有 {len(check_items)} 个知识点掌握度证据不足，路线会先安排小测确认。")

    if skipped:
        parts.append(f"其中 {len(skipped)} 个已掌握的项目被标记为「可快速过」，任务保留但学时压缩。")
    weak_count = len(level_profile.get("weak_tags") or [])
    if weak_count:
        parts.append(f"检测到 {weak_count} 个薄弱知识点，相关项目已尽量往前排。")
    if reordered_phases:
        parts.append(f"有 {reordered_phases} 个阶段调整了项目顺序。")
    if graph_info.get("has_graph"):
        merged_edges = int(graph_info.get("merged_edges") or 0)
        if merged_edges:
            parts.append(f"知识图谱补充了 {merged_edges} 条先修关系，已用来判断项目先后。")
        remedial = graph_info.get("remedial_inserted") or []
        if remedial:
            names = "、".join(item.get("blocker_name") or item.get("blocker") or "" for item in remedial[:3])
            parts.append(f"图谱发现前置知识没打牢，已在对应项目前插入 {len(remedial)} 个补先修任务（{names}）。")
        blocked_skips = graph_info.get("skip_blocked") or []
        if blocked_skips:
            parts.append(f"有 {len(blocked_skips)} 个项目虽然分数达标，但前置没掌握，暂时不标为可快速过。")
    if budget_info.get("budget_minutes"):
        parts.append(budget_info.get("message") or "")
    parts.append(f"按「{learning_depth}」深度，预计总学时约 {total_minutes} 分钟。")
    return "".join(part for part in parts if part)


def _build_remedial_task(target: dict, blocker: str, blocker_name: str,
                         depth_level: str) -> dict:
    """为「前置没打牢」生成一个补先修任务，插在目标项目之前。"""
    target_name = target.get("topic") or target.get("knowledge")
    return {
        "topic": f"补先修：{blocker_name}",
        "knowledge": blocker,
        "framework": target.get("framework") or "Python 标准库",
        "deliverable": f"能用自己的话说明「{blocker_name}」，并手写一个最小可运行例子",
        "duration": "30分钟",
        "action": f"先补齐「{blocker_name}」：看引导教程并手写一个最小例子，再进入「{target_name}」。",
        "resource": "引导教程 + 针对性练习",
        "check": f"能解释「{blocker_name}」的关键步骤，并说清它为什么是「{target_name}」的前提",
        "lab_id": None,
        "module_id": target.get("module_id"),
        "depth_level": depth_level,
        "skippable": False,
        "remedial_prerequisite": True,
        "graph_gated": True,
        "blocked_target": target.get("knowledge"),
        "blocker_name": blocker_name,
    }


def _build_course_candidate(selected_tracks: list[str], level_profile: dict,
                            learning_depth: str, prereq_map: dict,
                            graph_context: dict, strategy: str) -> dict:
    """按指定策略生成一条项目制候选路径（#44 候选生成）。

    四种策略共享同一套「跳过 / 重排 / 深度 / 图谱」编排器，区别在于同批任务的
    先后、时间预算压缩力度，以及对目标/薄弱/不确定知识点的侧重。
    """
    level_profile = level_profile or {}
    mastery = level_profile.get("mastery") or {}
    mastered_tags = set(level_profile.get("mastered_tags") or [])
    weak_tags = set(level_profile.get("weak_tags") or [])
    mastery_high, mastery_low = _mastery_thresholds()
    prereq_map = prereq_map if prereq_map is not None else _load_prerequisites()

    graph_context = graph_context or {}
    has_graph = bool(graph_context.get("has_graph"))
    readiness_map = graph_context.get("readiness") or {}
    similar_map = graph_context.get("similar") or {}
    name_map = {**course_point_names(), **(graph_context.get("names") or {})}
    added_edges = graph_context.get("added_edges") or []
    depth_level = DEPTH_LEVELS.get(learning_depth, learning_depth or "标准")
    meta_map = knowledge_meta_index()

    error_profile = level_profile.get("error_profile") or {}
    target_tags = set(level_profile.get("target_tags") or [])
    error_tags = {
        item.get("tag") for item in (error_profile.get("top_error_tags") or [])
        if item.get("tag")
    }
    uncertainty = level_profile.get("mastery_uncertainty") or {}
    uncertain_tags = {
        item.get("tag") for item in (uncertainty.get("top_uncertain_tags") or [])
        if item.get("tag")
    }
    misconceptions = {
        item["tag"]: list(item.get("misconceptions") or [])[:2]
        for item in (error_profile.get("top_error_tags") or [])
        if item.get("tag") and item.get("misconceptions")
    }


    selected = set(selected_tracks)
    selected_course_tracks = [track for track in COURSE_TRACKS if track["name"] in selected]
    project_map = project_index([track["name"] for track in selected_course_tracks])

    def _task_state(source: dict) -> tuple:
        """统一读取一个项目任务的掌握度、图谱就绪度与薄弱前置。"""
        knowledge = source.get("knowledge")
        score = mastery.get(knowledge)
        if score is None and knowledge in mastered_tags:
            score = 1.0
        if score is None and knowledge in weak_tags:
            score = 0.0
        readiness = readiness_map.get(knowledge) or {}
        blockers = [b for b in dict.fromkeys(readiness.get("root_blockers") or []) if b]
        blocked = has_graph and readiness.get("state") == "blocked" and bool(blockers)
        return knowledge, score, readiness, blockers, blocked

    # 预扫描：判断每个薄弱前置「能不能复用课程已有项目」。
    # 能复用 → 只给已有项目打补先修重点（保留真实实验/资源），不新增重复任务；
    # 不能复用（如课程外的前置）→ 才插入文本型补先修任务兜底。
    reuse_targets = {}
    fallback_targets = {}
    for track in selected_course_tracks:
        for source in track["tasks"]:
            _, _, _, blockers, blocked = _task_state(source)
            if not blocked:
                continue
            target_topic = source.get("topic")
            for blocker in blockers[:2]:
                if project_map.get(blocker):
                    bucket = reuse_targets.setdefault(blocker, [])
                    if target_topic not in bucket:
                        bucket.append(target_topic)
                else:
                    bucket = fallback_targets.setdefault(target_topic, [])
                    if blocker not in bucket:
                        bucket.append(blocker)

    phases = []
    day = 1
    total_minutes = 0
    skipped_topics = []
    reordered_phases = 0
    remedial_inserted = []
    remedial_links = []
    skip_blocked = []
    readiness_blocked = []
    remedial_done = set()

    for track in selected_course_tracks:
        source_tasks = [dict(task) for task in track["tasks"]]
        ordered_tasks = _reorder_phase_tasks(
            source_tasks, prereq_map, mastery, readiness_map,
            strategy=strategy, target_tags=target_tags,
            error_tags=error_tags, uncertain_tags=uncertain_tags,
        )
        if [task["topic"] for task in ordered_tasks] != [task["topic"] for task in source_tasks]:
            reordered_phases += 1

        tasks = []
        for source in ordered_tasks:
            knowledge, score, readiness, blockers, blocked = _task_state(source)
            state = readiness.get("state")

            # 兜底：这个前置在课程里没有对应项目，才真的插入一个补先修任务（同一前置只插一次）
            for blocker in fallback_targets.get(source.get("topic"), []):
                if blocker in remedial_done:
                    continue
                blocker_name = name_map.get(blocker) or blocker
                remedial = _build_remedial_task(source, blocker, blocker_name, depth_level)
                remedial["day"] = day
                remedial["graph_reason"] = (
                    f"图谱显示「{blocker_name}」还没掌握，直接学「{source.get('topic')}」会卡住"
                )
                tasks.append(remedial)
                remedial_inserted.append({
                    "day": day,
                    "topic": remedial["topic"],
                    "blocker": blocker,
                    "blocker_name": blocker_name,
                    "target": knowledge,
                    "target_topic": source.get("topic"),
                })
                total_minutes += _parse_minutes(remedial["duration"])
                day += 1
                remedial_done.add(blocker)

            task = {"day": day, **source}
            task["depth_level"] = depth_level
            task["is_target"] = knowledge in target_tags
            task["needs_check"] = (
                knowledge in uncertain_tags
                and not (score is not None and score >= mastery_high)
            )
            if knowledge in error_tags:
                task["error_focus"] = True
                task["misconceptions"] = misconceptions.get(knowledge) or []
            point_meta = meta_map.get(knowledge) or {}
            if point_meta:
                task["difficulty"] = point_meta.get("difficulty")
                task["difficulty_label"] = point_meta.get("difficulty_label")
                task["cognitive_level"] = point_meta.get("cognitive_level")
                task["study_minutes"] = point_meta.get("study_minutes")
                task["exam_weight"] = point_meta.get("exam_weight")
            if has_graph and readiness:
                task["graph_readiness"] = state
                task["graph_readiness_score"] = readiness.get("score")
                task["graph_blockers"] = [name_map.get(b) or b for b in blockers]
                task["graph_own_mastery"] = readiness.get("own_mastery")
                task["graph_undiagnosed"] = bool(readiness.get("undiagnosed"))
                task["graph_parents"] = readiness.get("parents") or []
                if blocked:
                    task["graph_gated"] = True
                    readiness_blocked.append({
                        "topic": source.get("topic"),
                        "knowledge": knowledge,
                        "blockers": [name_map.get(b) or b for b in blockers],
                    })

            # 复用的补先修：这个项目同时是别人的前置，直接标成「补先修重点」
            if knowledge in reuse_targets:
                task["remedial_focus"] = True
                task["remedial_for"] = reuse_targets[knowledge][:5]
                task["graph_reason"] = (
                    f"图谱显示「{name_map.get(knowledge) or knowledge}」是后续 "
                    f"{len(reuse_targets[knowledge])} 个项目的前置，建议在这一站把它打牢"
                )
                remedial_links.append({
                    "day": day,
                    "topic": source.get("topic"),
                    "blocker": knowledge,
                    "blocker_name": name_map.get(knowledge) or knowledge,
                    "targets": reuse_targets[knowledge][:5],
                    "lab_id": source.get("lab_id"),
                    "module_id": source.get("module_id"),
                    "duration": source.get("duration"),
                })

            # 相似知识点 → 对比学习提示
            similar = similar_map.get(knowledge) or []
            if similar:
                task["similar_topics"] = similar[:3]
                if not (score is not None and score >= mastery_high):
                    first = similar[0]
                    reason = first.get("reason") or "概念相近，容易混淆"
                    task["compare_hint"] = f"学完后可与「{first.get('name')}」对比：{reason}"

            base_minutes = _parse_minutes(source.get("duration"))

            if score is not None and score >= mastery_high:
                if blocked:
                    # 分数看着够，但前置没掌握：不压缩、不允许快进
                    task["skippable"] = False
                    task["skip_reason"] = ""
                    skip_blocked.append({
                        "topic": source.get("topic"),
                        "knowledge": knowledge,
                        "blockers": [name_map.get(b) or b for b in blockers],
                    })
                else:
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

    # ── 时间预算：超出用户预算时压缩非目标任务（#43）
    time_budget = level_profile.get("time_budget") or {}
    budget_minutes = time_budget.get("budget_minutes")
    all_tasks = [task for phase in phases for task in phase.get("tasks", [])]
    compressed_tasks = 0

    def _compress(predicate) -> None:
        nonlocal total_minutes, compressed_tasks
        ratio = max(0.5, float(budget_minutes) / max(1, total_minutes))
        for item in all_tasks:
            if not predicate(item):
                continue
            base = _parse_minutes(item.get("duration"))
            target_minutes = max(15, int(round(base * ratio)))
            if target_minutes >= base:
                continue
            if not item.get("original_duration"):
                item["original_duration"] = item.get("duration")
            item["duration"] = f"{target_minutes}分钟"
            item["budget_compressed"] = True
            total_minutes += target_minutes - base
            compressed_tasks += 1

    if budget_minutes and total_minutes > budget_minutes:
        # 先压非目标、非补先修的普通项目，保住用户明确想学的目标
        _compress(lambda t: not (
            t.get("is_target") or t.get("remedial_prerequisite")
            or t.get("remedial_focus") or t.get("budget_compressed")
        ))
        if total_minutes > budget_minutes:
            _compress(lambda t: not t.get("budget_compressed"))

    budget_info = {
        "budget_minutes": budget_minutes,
        "planned_minutes": total_minutes,
        "fit": (total_minutes <= budget_minutes) if budget_minutes else True,
        "compressed_tasks": compressed_tasks,
        "message": "",
    }
    if budget_minutes:
        if total_minutes <= budget_minutes:
            budget_info["message"] = (
                f"按你给的 {budget_minutes} 分钟预算，这条路线约 {total_minutes} 分钟，能按时完成。"
                + (f"已压缩 {compressed_tasks} 个非重点项目的学时。" if compressed_tasks else "")
            )
        else:
            budget_info["message"] = (
                f"按当前预算（{budget_minutes} 分钟）仍超出约 {total_minutes - budget_minutes} 分钟；"
                "建议减少目标知识点，或选择「省时优先」方案。"
            )

    # ── 多目标指标（#44）：先修阻塞、目标覆盖、薄弱前置、时间贴合、难度平滑
    total_tasks = max(1, len(all_tasks))
    target_positions = [i for i, item in enumerate(all_tasks) if item.get("is_target")]
    weak_positions = [
        i for i, item in enumerate(all_tasks)
        if item.get("error_focus")
        or (mastery.get(item.get("knowledge")) is not None
            and mastery.get(item.get("knowledge")) < mastery_low)
    ]
    blocked_tasks = sum(1 for item in all_tasks if item.get("graph_gated"))
    jumps, jump_count, prev_difficulty = 0, 0, None
    for item in all_tasks:
        difficulty = ((meta_map.get(item.get("knowledge")) or {}).get("difficulty"))
        if difficulty is None:
            continue
        if prev_difficulty is not None:
            jumps += max(0, difficulty - prev_difficulty)
            jump_count += 1
        prev_difficulty = difficulty
    covered_targets = {
        tag for tag in target_tags
        if any(item.get("knowledge") == tag for item in all_tasks)
    }
    metrics = {
        "total_tasks": len(all_tasks),
        "blocked_tasks": blocked_tasks,
        "target_total": len(target_tags),
        "target_covered": len(covered_targets),
        "target_coverage": round(len(covered_targets) / len(target_tags), 3) if target_tags else 1.0,
        "target_rank": round(sum(target_positions) / len(target_positions) / total_tasks, 3)
        if target_positions else 0.5,
        "weak_rank": round(sum(weak_positions) / len(weak_positions) / total_tasks, 3)
        if weak_positions else 0.5,
        "difficulty_jump": round(jumps / max(1, jump_count), 3),
        "total_minutes": total_minutes,
    }

    graph_operator = {
        "applied": has_graph,
        "has_graph": has_graph,
        "source": graph_context.get("source") or ("llm" if has_graph else "expert"),
        "graph_updated_at": (graph_context.get("graph") or {}).get("updated_at"),
        "merged_edges": len(added_edges),
        "merged_edge_samples": added_edges[:5],
        "readiness_blocked": readiness_blocked,
        "remedial_inserted": remedial_inserted,
        "remedial_links": remedial_links,
        "skip_blocked": skip_blocked,
    }

    return {
        "curriculum_version": CURRICULUM_VERSION,
        "strategy": strategy,
        "phases": phases,
        "estimated_total_days": day - 1,
        "estimated_total_minutes": total_minutes,
        "learning_depth": learning_depth,
        "depth_level": depth_level,
        "level_profile": level_profile,
        "time_budget": budget_info,
        "metrics": metrics,
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
            "graph": graph_operator,
        },
        "personalization_summary": _build_personalization_summary(
            level_profile, total_minutes, skipped_topics, reordered_phases,
            learning_depth, graph_operator, budget_info,
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
                "标注「可快速过」的项目说明你已经掌握，快速验证后即可继续；"
                "标注「补先修」的项目说明前置知识还没打牢，先补完再往下学会更顺。",
        "modules_selected": selected_tracks,
    }


def _normalize_metric(values: list, invert: bool = False) -> list:
    """把一组原始指标缩放到 0~1（越优越接近 1），用于多目标加权评分。"""
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [1.0 for _ in values]
    scaled = [(value - low) / (high - low) for value in values]
    if invert:
        scaled = [1.0 - value for value in scaled]
    return scaled


def _candidate_highlights(candidate: dict) -> list:
    """一句话说明这条备选方案的特点，供前端卡片直接展示。"""
    metrics = candidate.get("metrics") or {}
    time_budget = candidate.get("time_budget") or {}
    items = []
    if metrics.get("target_total"):
        items.append(f"覆盖 {metrics.get('target_covered')}/{metrics.get('target_total')} 个目标知识点")
    if metrics.get("weak_rank", 0.5) < 0.5:
        items.append("薄弱/常错知识点排在更前面")
    if metrics.get("blocked_tasks"):
        items.append(f"{metrics['blocked_tasks']} 个任务仍需先补前置")
    if time_budget.get("budget_minutes"):
        items.append(f"预计 {metrics.get('total_minutes')} 分钟，预算 {time_budget['budget_minutes']} 分钟")
    else:
        items.append(f"预计 {metrics.get('total_minutes')} 分钟")
    return items


def plan_course_path(selected_tracks: list[str], level_profile: dict = None,
                     learning_depth: str = "标准", prereq_map: dict = None,
                     graph_context: dict = None) -> dict:
    """按学生水平编排项目制学习路径（v3：候选生成 + 多目标排序 + 备选方案）。

    先生成四种候选（均衡 / 补弱优先 / 目标优先 / 省时优先），再用先修阻塞、
    目标覆盖与位置、薄弱项位置、时间贴合、难度平滑五项指标统一打分：
    - 用户明确选了偏好 → 直接采用对应策略；
    - 没有偏好 → 用「均衡」权重自动择优；
    - 其余候选作为备选方案返回，前端可一键切换。
    """
    level_profile = level_profile or {}
    preferences = level_profile.get("preferences") or {}
    requested_mode = preferences.get("mode") or ""
    forced_strategy = MODE_TO_STRATEGY.get(requested_mode)
    prereq_map = prereq_map if prereq_map is not None else _load_prerequisites()

    candidates = [
        _build_course_candidate(
            selected_tracks, level_profile, learning_depth,
            prereq_map, graph_context, strategy,
        )
        for strategy in PATH_STRATEGIES
    ]

    # 统一尺度打分：先修阻塞越少、目标/薄弱越靠前、用时越短、难度跳跃越小越好
    blocked_norm = _normalize_metric([c["metrics"]["blocked_tasks"] for c in candidates], invert=True)
    target_norm = _normalize_metric([c["metrics"]["target_rank"] for c in candidates], invert=True)
    weak_norm = _normalize_metric([c["metrics"]["weak_rank"] for c in candidates], invert=True)
    time_norm = _normalize_metric([c["metrics"]["total_minutes"] for c in candidates], invert=True)
    smooth_norm = _normalize_metric([c["metrics"]["difficulty_jump"] for c in candidates], invert=True)
    components = {
        "prereq": blocked_norm,
        "target": target_norm,
        "weak": weak_norm,
        "time": time_norm,
        "smooth": smooth_norm,
    }

    for index, candidate in enumerate(candidates):
        strategy_weights = STRATEGY_WEIGHTS[candidate["strategy"]]
        candidate["metrics"]["components"] = {
            key: round(values[index], 3) for key, values in components.items()
        }
        candidate["score"] = round(sum(
            strategy_weights[key] * components[key][index] for key in strategy_weights
        ), 4)

    by_strategy = {candidate["strategy"]: candidate for candidate in candidates}
    if forced_strategy:
        chosen = by_strategy[forced_strategy]
    else:
        # 没有偏好时统一用「均衡」权重比较，避免每种方案各自打分造成偏差
        balanced_weights = STRATEGY_WEIGHTS["balanced"]
        for index, candidate in enumerate(candidates):
            candidate["auto_score"] = round(sum(
                balanced_weights[key] * components[key][index] for key in balanced_weights
            ), 4)
        chosen = max(candidates, key=lambda item: (item["auto_score"], item["score"]))

    alternatives = []
    for candidate in candidates:
        if candidate["strategy"] == chosen["strategy"]:
            continue
        alternatives.append({
            "strategy": candidate["strategy"],
            "mode_label": STRATEGY_LABELS[candidate["strategy"]],
            "mode": next(
                (mode for mode, value in MODE_TO_STRATEGY.items() if value == candidate["strategy"]),
                "均衡",
            ),
            "score": candidate["score"],
            "estimated_total_minutes": candidate["estimated_total_minutes"],
            "estimated_total_days": candidate["estimated_total_days"],
            "highlights": _candidate_highlights(candidate),
            "time_fit": (candidate.get("time_budget") or {}).get("fit"),
        })
    alternatives.sort(key=lambda item: -item["score"])

    result = {key: value for key, value in chosen.items() if key not in ("score", "auto_score")}
    result["path_strategy"] = {
        "strategy": chosen["strategy"],
        "mode_label": STRATEGY_LABELS[chosen["strategy"]],
        "requested_mode": requested_mode,
        "auto_selected": not bool(forced_strategy),
        "score": chosen["score"],
        "reason": (
            f"已按你选的「{requested_mode}」生成。"
            if forced_strategy else
            "系统比较了四种编排方式，这条在目标覆盖、薄弱补强和时间安排上综合最优。"
        ),
    }
    result["alternatives"] = alternatives
    return result


KNOWLEDGE_PATH_VERSION = "agent-knowledge-path-v1"


def plan_knowledge_path(mastery: dict = None, prereq_map: dict = None,
                        graph_context: dict = None,
                        selected_tracks: list = None,
                        level_profile: dict = None,
                        mastery_detail: dict = None) -> dict:
    """把课程全部知识点按先修关系编成一条可执行的学习序列（v2）。

    与 plan_course_path 的区别：这里的「一站」是知识点本身，不是项目。
    12 个实训项目只作为知识点上的练习资源挂载；没有项目的拓展知识点
    同样进入序列，通过教程 + 快速测评推进。

    #43 起，每个知识点还带难度、认知层次、建议学时、考纲权重、常见误区，
    并消费学习者模型里的目标节点、时间预算、偏好、错误画像与掌握度不确定度。

    Args:
        mastery: tag -> 0~1 掌握度（来自知识追踪）。
        prereq_map: 合并后的先修表（图谱先修边 + 专家表）；不传则退回专家表。
        graph_context: _build_graph_context() 的结果，用 readiness 判断锁定。
        selected_tracks: 只挂载这些阶段里的项目；不传则全部阶段。
        level_profile: 学习者模型（目标/预算/偏好/错误画像/不确定度）。
        mastery_detail: tag -> 掌握度证据明细，用于置信度与不确定度。
    """
    mastery = mastery or {}
    level_profile = level_profile or {}
    mastery_detail = mastery_detail or {}
    prereq_map = prereq_map if prereq_map is not None else _load_prerequisites()
    graph_context = graph_context or {}
    readiness_map = graph_context.get("readiness") or {}
    name_map = {**course_point_names(), **(graph_context.get("names") or {})}
    mastery_high, mastery_low = _mastery_thresholds()
    project_map = project_index(selected_tracks)
    meta_map = knowledge_meta_index()

    error_profile = level_profile.get("error_profile") or {}
    target_tags = set(level_profile.get("target_tags") or [])
    error_tags = {
        item.get("tag") for item in (error_profile.get("top_error_tags") or [])
        if item.get("tag")
    }
    uncertainty = level_profile.get("mastery_uncertainty") or {}
    uncertain_tags = {
        item.get("tag") for item in (uncertainty.get("top_uncertain_tags") or [])
        if item.get("tag")
    }
    misconceptions = {
        item["tag"]: list(item.get("misconceptions") or [])[:2]
        for item in (error_profile.get("top_error_tags") or [])
        if item.get("tag") and item.get("misconceptions")
    }
    preferences = level_profile.get("preferences") or {}
    strategy = MODE_TO_STRATEGY.get(preferences.get("mode") or "", "balanced")
    time_budget = level_profile.get("time_budget") or {}


    points = [dict(item) for item in COURSE_KNOWLEDGE_POINTS]
    course_order = {item["tag"]: index for index, item in enumerate(points)}
    known = set(course_order)
    parents = {
        item["tag"]: [
            p for p in dict.fromkeys(prereq_map.get(item["tag"]) or [])
            if p in known and p != item["tag"]
        ]
        for item in points
    }

    # 拓扑波次：波次越小越靠前；同一波内没有先修先后，可以按掌握度调整。
    wave_memo = {}

    def _wave(tag: str, seen: set) -> int:
        if tag in wave_memo:
            return wave_memo[tag]
        if tag in seen:  # 环保护：依赖表若出现环，回退为 0
            return 0
        ps = parents.get(tag) or []
        value = 0 if not ps else 1 + max(_wave(p, seen | {tag}) for p in ps)
        wave_memo[tag] = value
        return value

    units = []
    for item in points:
        tag = item["tag"]
        score = mastery.get(tag)
        if not isinstance(score, (int, float)):
            score = None

        readiness = readiness_map.get(tag) or {}
        state = readiness.get("state")
        blockers = [
            b for b in dict.fromkeys(readiness.get("root_blockers") or []) if b in known
        ]
        if state == "blocked":
            locked = True
        elif not readiness_map:
            # 没有图谱时用直接先修兜底：前置有练习证据但没打牢，也视为锁定。
            blockers = [
                p for p in parents[tag]
                if mastery.get(p) is not None and mastery.get(p) < mastery_low
            ]
            locked = bool(blockers)
        else:
            locked = False

        if locked:
            status = "locked"
            blocker_names = [name_map.get(b) or b for b in blockers]
            reason = f"先补「{'、'.join(blocker_names)}」，再学这个知识点"
        elif score is not None and score >= mastery_high:
            status = "done"
            reason = "已经掌握，可以直接往后学"
        else:
            status = "todo"
            if score is not None and score < mastery_low:
                reason = f"掌握度 {round(score * 100)}%，建议优先补强"
            else:
                reason = "前置已就绪，可以安排到下一步"

        if score is None:
            band = "unknown"
            priority = 1
        elif score >= mastery_high:
            band = "high"
            priority = 3
        elif score >= mastery_low:
            band = "medium"
            priority = 2
        else:
            band = "low"
            priority = 0

        is_target = tag in target_tags
        needs_check = tag in uncertain_tags and not (score is not None and score >= mastery_high)
        if strategy == "target_first":
            priority -= 30 if is_target else 0
        elif strategy == "weak_first":
            priority -= 12 if tag in error_tags else 0
            priority -= 4 if needs_check else 0
            priority -= 5 if is_target else 0
        elif strategy == "time_saver":
            priority -= 15 if band == "high" else 0
            priority -= 6 if is_target else 0
        else:
            priority -= 8 if is_target else 0
            priority -= 4 if tag in error_tags else 0
            priority -= 2 if needs_check else 0

        project_items = project_map.get(tag) or []
        project = project_items[0] if project_items else None
        point_meta = meta_map.get(tag) or {}
        detail = mastery_detail.get(tag) or {}
        confidence = detail.get("confidence")
        estimated_minutes = int(point_meta.get("study_minutes") or 0) or (
            _parse_minutes(project.get("duration")) if project else 30
        )
        if is_target:
            reason = f"你指定的目标知识点；{reason}"
        elif tag in error_tags:
            reason = f"错题最多的知识点之一，建议优先纠正；{reason}"
        elif needs_check:
            reason = f"掌握度证据不足，先做一次小测确认；{reason}"

        units.append({
            "tag": tag,
            "name": item.get("name") or name_map.get(tag) or tag,
            "module": item.get("module") or "",
            "in_course": bool(item.get("in_course")),
            "wave": _wave(tag, set()),
            "mastery": round(score, 3) if score is not None else None,
            "mastery_band": band,
            "mastery_confidence": round(float(confidence), 3) if confidence is not None else None,
            "mastery_uncertainty": round(1 - float(confidence), 3) if confidence is not None else None,
            "needs_check": needs_check,
            "status": status,
            "blocked": locked,
            "blockers": [name_map.get(b) or b for b in blockers],
            "blocker_tags": blockers,
            "prerequisites": [
                {"tag": p, "name": name_map.get(p) or p} for p in parents[tag]
            ],
            "project": project,
            "resources": {
                "tutorial": True,
                "quiz": True,
                "project": bool(project),
            },
            "difficulty": point_meta.get("difficulty"),
            "difficulty_label": point_meta.get("difficulty_label"),
            "cognitive_level": point_meta.get("cognitive_level"),
            "study_minutes": point_meta.get("study_minutes"),
            "exam_weight": point_meta.get("exam_weight"),
            "misconceptions": list(point_meta.get("misconceptions") or [])[:2]
            if tag in error_tags else list(point_meta.get("misconceptions") or [])[:1],
            "is_target": is_target,
            "error_focus": tag in error_tags,
            "estimated_minutes": estimated_minutes,
            "project_minutes": _parse_minutes(project.get("duration")) if project else None,
            "reason": reason,
            "_priority": priority,
        })

    units.sort(key=lambda unit: (unit["wave"], unit["_priority"], course_order[unit["tag"]]))
    current = None
    for index, unit in enumerate(units, start=1):
        unit["order"] = index
        unit.pop("_priority", None)
        if current is None and unit["status"] == "todo":
            unit["status"] = "current"
            unit["reason"] = (
                "下一步就学这个（你指定的目标）：先看教程，再做一道小测确认"
                if unit.get("is_target") else
                "下一步就学这个：先看教程，再做一道小测确认"
            )
            current = unit

    mastered_count = sum(1 for unit in units if unit["status"] == "done")
    remaining_minutes = sum(
        unit["estimated_minutes"] for unit in units if unit["status"] != "done"
    )
    budget_minutes = time_budget.get("budget_minutes")
    current_brief = None
    if current:
        current_brief = {
            key: current[key]
            for key in ("order", "tag", "name", "module", "mastery", "mastery_band",
                        "status", "blockers", "project", "reason", "is_target",
                        "difficulty_label", "cognitive_level", "study_minutes", "needs_check")
        }

    return {
        "version": KNOWLEDGE_PATH_VERSION,
        "total": len(units),
        "mastered": mastered_count,
        "remaining": len(units) - mastered_count,
        "project_units": sum(1 for unit in units if unit["project"]),
        "extension_units": sum(1 for unit in units if not unit["in_course"]),
        "current": current_brief,
        "path_strategy": {
            "strategy": strategy,
            "mode_label": STRATEGY_LABELS[strategy],
            "auto_selected": not bool(preferences.get("mode")),
        },
        "targets": [
            {
                "tag": unit["tag"], "name": unit["name"], "order": unit["order"],
                "status": unit["status"], "mastery": unit["mastery"],
                "needs_check": unit["needs_check"],
            }
            for unit in units if unit.get("is_target")
        ],
        "error_focus": [
            {
                "tag": unit["tag"], "name": unit["name"], "order": unit["order"],
                "misconceptions": unit["misconceptions"],
            }
            for unit in units if unit.get("error_focus")
        ][:6],
        "uncertain": [
            {"tag": unit["tag"], "name": unit["name"], "order": unit["order"],
             "uncertainty": unit["mastery_uncertainty"]}
            for unit in units if unit["needs_check"]
        ][:8],
        "time_budget": {
            "budget_minutes": budget_minutes,
            "weekly_hours": time_budget.get("weekly_hours"),
            "deadline_weeks": time_budget.get("deadline_weeks"),
            "remaining_minutes": remaining_minutes,
            "fit": (remaining_minutes <= budget_minutes) if budget_minutes else True,
        },
        "preferences": {
            "mode": preferences.get("mode") or "",
            "mode_label": preferences.get("mode_label") or "自动选择",
            "target_count": len(target_tags),
            "error_count": len(error_tags),
        },
        "units": units,
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
