"""旗舰编程实验的变式迁移规格。

这里的任务刻意改变业务场景、输入输出契约和边界条件，但仍复用原实验
训练的核心能力。测试用例只在服务端执行，前端仅展示场景说明。
"""

ADDITIONAL_VARIANT_SPECS = {
    "1-1": {
        "target": "insert_interval",
        "language": "cpp",
        "cpp": {
            "signature": (
                "std::vector<std::vector<int>> insert_interval("
                "std::vector<std::vector<int>> intervals, std::vector<int> new_interval)"
            ),
            "includes": ["<vector>", "<stdexcept>", "<string>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "日程表场景。每个日程是一个 [start, end] 二元组，同一份日程表里的区间"
            "互不重叠且按 start 升序排好。现在有一个新日程 new_interval，请把它插入"
            "日程表并保持有序、互不重叠：\n"
            "1. 新日程与已有日程重叠（含端点相接）时，把它们合并成一个区间；\n"
            "2. 合并可能连锁发生，要一直合到不再重叠为止；\n"
            "3. 新日程落在所有日程之前或之后时，直接放进正确的位置；\n"
            "4. 日程表为空时，返回只含新日程的表格；\n"
            "5. 任何一个日程的 start 大于 end、或元素个数不是 2 时，"
            "抛出 std::invalid_argument。\n"
            "不得修改传入的任何容器，返回一份新的日程表。"
        ),
        "hints": [
            {
                "level": 1, "title": "思考问题",
                "content": "两个日程在什么情况下算重叠？端点相接（前一个的 end 正好等于后一个的 start）算不算？先把定义写清楚再动手。",
            },
            {
                "level": 2, "title": "方向提示",
                "content": "先把新日程按 start 插进有序表，再从左往右扫一遍合并相邻区间，比一边找位置一边合并更好写。",
            },
            {
                "level": 3, "title": "检查清单",
                "content": "空表、插在最前、插在最后、被一个大区间完全包含、把多个区间串成一串、端点相接——六种都试过再提交；返回新容器，不要改动传入的 intervals。",
            },
        ],
        "cases": [
            {"description": "插入到空日程表", "args": [[], [1, 3]], "expected": [[1, 3]]},
            {"description": "完全在已有的日程之前", "args": [[[5, 7]], [1, 2]], "expected": [[1, 2], [5, 7]]},
            {"description": "完全在已有的日程之后", "args": [[[1, 2]], [5, 7]], "expected": [[1, 2], [5, 7]]},
            {"description": "落在两个日程之间且不重叠", "args": [[[1, 2], [5, 7]], [3, 4]], "expected": [[1, 2], [3, 4], [5, 7]]},
            {"description": "与已有日程重叠时合并", "args": [[[1, 3], [6, 8]], [2, 7]], "expected": [[1, 8]]},
            {"description": "链式合并多个日程", "args": [[[1, 2], [4, 5], [7, 9]], [2, 8]], "expected": [[1, 9]]},
            {"description": "端点相接也要合并", "args": [[[1, 3], [5, 7]], [3, 5]], "expected": [[1, 7]]},
            {"description": "新日程完全覆盖已有日程", "args": [[[3, 4], [6, 7]], [1, 9]], "expected": [[1, 9]]},
            {"description": "新日程被已有日程完全包含", "args": [[[1, 9]], [3, 4]], "expected": [[1, 9]]},
            {"description": "落在首位并触发合并", "args": [[[3, 5], [8, 9]], [1, 4]], "expected": [[1, 5], [8, 9]]},
            {"description": "落在末位并触发合并", "args": [[[1, 2], [5, 6]], [6, 9]], "expected": [[1, 2], [5, 9]]},
            {"description": "拒绝 start 大于 end 的日程", "args": [[[1, 2]], [4, 3]], "exception": "invalid_argument"},
            {"description": "拒绝元素个数不是 2 的日程", "args": [[[1, 2, 3]], [4, 5]], "exception": "invalid_argument"},
        ],
    },
    "1-2": {
        "target": "merge_two_lists",
        "language": "cpp",
        "cpp": {
            "signature": "Node* merge_two_lists(Node* a, Node* b)",
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：合并两条有序链表\n\n"
            "原项目反转一条单链表。现在实现 `merge_two_lists(a, b)`，"
            "把两条**已按值非降序排列**的单链表合并成一条同样有序的链表并返回其头节点。\n\n"
            "节点用公共结构体 `struct Node { int value; Node* next; }` 表示，"
            "`a`、`b` 可以是 `nullptr` 表示空链。要求返回一条**全新的**链表（用 `new Node` 构造），"
            "不得修改 `a` 或 `b` 上的任何节点。每条链自身必须按值非降序，否则抛出 "
            "`std::invalid_argument`。两条链中的重复值都要保留。\n\n"
            "**迁移重点**：链表的指针拼接、双指针推进，以及不改动输入数据的纪律。"
        ),
        "cases": [
            {"description": "两条空链合并", "args": [None, None], "expected": None},
            {"description": "一条为空链", "args": [None, {"value": 1, "next": {"value": 2, "next": None}}], "expected": {"value": 1, "next": {"value": 2, "next": None}}},
            {"description": "等长链表交错合并", "args": [
                {"value": 1, "next": {"value": 3, "next": None}},
                {"value": 2, "next": {"value": 4, "next": None}}
            ], "expected": {"value": 1, "next": {"value": 2, "next": {"value": 3, "next": {"value": 4, "next": None}}}}, "immutable": True},
            {"description": "长度不等的链表合并", "args": [
                {"value": 1, "next": {"value": 2, "next": None}},
                {"value": 3, "next": {"value": 4, "next": {"value": 5, "next": None}}}
            ], "expected": {"value": 1, "next": {"value": 2, "next": {"value": 3, "next": {"value": 4, "next": {"value": 5, "next": None}}}}}},
            {"description": "左侧先耗尽", "args": [
                {"value": 1, "next": {"value": 2, "next": {"value": 3, "next": None}}},
                {"value": 4, "next": None}
            ], "expected": {"value": 1, "next": {"value": 2, "next": {"value": 3, "next": {"value": 4, "next": None}}}}},
            {"description": "重复值全部保留", "args": [
                {"value": 1, "next": {"value": 2, "next": {"value": 2, "next": None}}},
                {"value": 2, "next": {"value": 3, "next": None}}
            ], "expected": {"value": 1, "next": {"value": 2, "next": {"value": 2, "next": {"value": 2, "next": {"value": 3, "next": None}}}}}},
            {"description": "负数参与合并", "args": [
                {"value": -3, "next": {"value": 0, "next": None}},
                {"value": -1, "next": {"value": 2, "next": None}}
            ], "expected": {"value": -3, "next": {"value": -1, "next": {"value": 0, "next": {"value": 2, "next": None}}}}},
            {"description": "拒绝未按值升序的链表", "args": [
                {"value": 3, "next": {"value": 1, "next": None}}, None
            ], "exception": "invalid_argument"},
        ],
        "hints": [{"level": 1, "title": "先处理两条都非空的情形", "content": "比较两条链当前节点的 value，较小的那个用 new Node 接到结果尾部，然后那条链往前走一步。"}, {"level": 2, "title": "别丢下剩下的尾巴", "content": "循环在任一条链耗尽时结束，另一条的剩余部分要整段接上去。"}, {"level": 3, "title": "先校验升序再合并", "content": "取值之前先确认每条链按 value 非降序；不满足就抛 std::invalid_argument。"}],
    },
    "1-3": {
        "target": "moving_average",
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<double> moving_average(int window, std::vector<double> events)",
            "includes": ["<stdexcept>", "<cmath>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：滑动窗口平均值\n\n"
            "原项目用栈处理逆波兰表达式（后进先出）。现在换成它的对偶结构——**队列**（先进先出）："
            "实现 `moving_average(window, events)`，按顺序读入 `events` 中的每个数字，"
            "每次读入后返回当前窗口内的平均值；窗口元素超过 `window` 个时，最旧的那个要被挤出去。\n\n"
            "返回一个 `std::vector<double>`，长度与 `events` 相同：第 i 项是读完第 i 个事件后的平均值。"
            "窗口还没填满时，按当前实际元素个数求平均。每个平均值保留三位小数，"
            "用 `std::round(值 * 1000.0) / 1000.0` 取整到三位。\n\n"
            "`window` 必须是整数且不小于 1，否则抛出 std::invalid_argument。不得修改 `events`。\n\n"
            "**迁移重点**：队列的先进先出、滑动窗口的进出配对，以及用舍入固定浮点结果。"
        ),
        "cases": [
            {"description": "窗口恰好填满", "args": [3, [1, 2, 3]], "expected": [1.0, 1.5, 2.0]},
            {"description": "窗口填满后挤掉最旧事件", "args": [3, [1, 2, 3, 4]], "expected": [1.0, 1.5, 2.0, 3.0]},
            {"description": "窗口为 1 时等于原值", "args": [1, [5, 6, 7]], "expected": [5.0, 6.0, 7.0]},
            {"description": "窗口为 2 的滑动平均", "args": [2, [1, 2, 3, 4]], "expected": [1.0, 1.5, 2.5, 3.5], "immutable": True},
            {"description": "没有事件", "args": [3, []], "expected": []},
            {"description": "窗口大于事件数量", "args": [5, [2, 4]], "expected": [2.0, 3.0]},
            {"description": "负数参与平均", "args": [2, [-1, 1, 3]], "expected": [-1.0, 0.0, 2.0]},
            {"description": "结果保留三位小数", "args": [3, [1, 2, 4]], "expected": [1.0, 1.5, 2.333]},
            {"description": "拒绝窗口为 0", "args": [0, [1]], "exception": "invalid_argument"},
            {"description": "拒绝负的窗口", "args": [-2, [1]], "exception": "invalid_argument"},
        ],
        "hints": [{"level": 1, "title": "先进先出", "content": "新事件从一端进，超过窗口时从另一端出——这正是队列，别用栈的 pop_back() 思路。"}, {"level": 2, "title": "边读边算", "content": "每读入一个事件就立刻 push_back 一个平均值，不要在循环外统一计算。"}, {"level": 3, "title": "舍入到三位", "content": "平均值用 std::round(值 * 1000.0) / 1000.0 固定到三位小数，否则 7/3 这种会多出很多位。"}],
    },
    "2-1": {
        "target": "bst_range_values",
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<int> bst_range_values(TreeNode* tree, int low, int high)",
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：BST 区间检索\n\n"
            "原项目在二分搜索树上做单值插入与查找。现在改成**范围查询**："
            "实现 `bst_range_values(tree, low, high)`，返回树中所有落在闭区间 `[low, high]` "
            "内的节点值，并按**升序**排列。\n\n"
            "树用公共结构体 `struct TreeNode { int value; TreeNode* left; TreeNode* right; }` 表示，"
            "`nullptr` 表示空树；整棵树必须满足二分搜索树性质（左子树全部小于根、右子树全部大于根，不允许重复值）。"
            "`low > high` 时抛出 std::invalid_argument。不得修改传入的树。\n\n"
            "提示：充分利用 BST 的有序性剪枝——若某棵子树的根已经大于 `high`，"
            "它的整棵右子树都不必再看；小于 `low` 时同理剪掉左子树。\n\n"
            "**迁移重点**：把「沿一条路径查找单值」升级为「按区间收集一批值」，"
            "并用有序性剪枝代替全树遍历。"
        ),
        "cases": [
            {"description": "区间覆盖整棵树", "args": [[10, [5, None, None], [15, None, None]], 5, 15], "expected": [5, 10, 15]},
            {"description": "区间只命中部分节点", "args": [[10, [5, None, None], [15, None, None]], 6, 15], "expected": [10, 15]},
            {"description": "闭区间端点都要包含", "args": [[10, [5, None, None], [15, None, None]], 5, 5], "expected": [5]},
            {"description": "区间与整棵树不相交", "args": [[10, [5, None, None], [15, None, None]], 6, 9], "expected": []},
            {"description": "空树返回空列表", "args": [None, 1, 5], "expected": []},
            {"description": "下界低于最小值", "args": [[10, [5, [1, None, None], None], [15, None, None]], -100, 5], "expected": [1, 5]},
            {"description": "上界高于最大值", "args": [[10, [5, [1, None, None], None], [15, None, None]], 10, 100], "expected": [10, 15]},
            {"description": "负数区间", "args": [[-5, [-10, None, None], [0, None, None]], -10, -5], "expected": [-10, -5]},
            {"description": "跨越多层收集", "args": [[20, [10, [5, None, None], [15, None, None]], [30, None, None]], 8, 25], "expected": [10, 15, 20]},
            {"description": "单节点树命中", "args": [[7, None, None], 7, 7], "expected": [7]},
            {"description": "单节点树未命中", "args": [[7, None, None], 1, 6], "expected": []},
            {"description": "区间落在两个值中间", "args": [[10, [5, None, None], [15, None, None]], 11, 14], "expected": []},
            {"description": "检索不得修改原树", "args": [[20, [10, [5, None, None], [15, None, None]], [30, None, None]], 8, 25], "expected": [10, 15, 20], "immutable": True},
            {"description": "拒绝下界大于上界", "args": [[10, None, None], 15, 5], "exception": "invalid_argument"},
            {"description": "拒绝违反 BST 顺序的树", "args": [[10, [15, None, None], None], 1, 20], "exception": "invalid_argument"},
            {"description": "拒绝深层违反 BST 顺序的树", "args": [[20, [10, [25, None, None], None], None], 1, 30], "exception": "invalid_argument"},
        ],
        "hints": [
            {"level": 1, "title": "中序才有升序", "content": "要求的输出是升序，而 BST 的中序遍历天然升序——先想清楚用什么顺序访问节点，再考虑剪枝。"},
            {"level": 2, "title": "三段式剪枝", "content": "对每个节点：根值大于 low 才需要进入左子树；根值落在区间内就收集；根值小于 high 才需要进入右子树。"},
            {"level": 3, "title": "先校验再剪枝", "content": "剪枝依赖 BST 性质成立，所以必须先校验树的有序性；low > high 也要在遍历前就报错。"},
        ],
    },
    "2-2": {
        "target": "bst_reverse_level_order",
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<std::vector<int>> bst_reverse_level_order(TreeNode* tree)",
            "includes": ["<vector>", "<algorithm>"],
        },
        "scenario": (
            "### 变式迁移：自底向上的层序遍历\n\n"
            "原项目自顶向下按层输出二叉树。现在把同一套遍历能力反着用："
            "实现 `bst_reverse_level_order(tree)`，先自顶向下逐层收集，"
            "再把层序结果整体反转，返回**自底向上**的层次列表。\n\n"
            "树用公共结构体 `struct TreeNode { int value; TreeNode* left; TreeNode* right; }` 表示，"
            "`nullptr` 表示空树，空树返回 `{}`。缺失的孩子不占位置，为 `nullptr` 的孩子不进入下一层；"
            "每一层内部保持从左到右的顺序。不得修改传入的树。\n\n"
            "**迁移重点**：层序骨架不变，但输出顺序、空树和稀疏树的边界都要重新确认。"
        ),
        "cases": [
            {"description": "空树返回空列表", "args": [None], "expected": []},
            {"description": "单节点树只有一层", "args": [[1, None, None]], "expected": [[1]]},
            {"description": "三层满树自底向上", "args": [[10, [5, None, None], [15, None, None]]], "expected": [[5, 15], [10]]},
            {"description": "缺失节点不占位置", "args": [[10, [5, [1, None, None], None], [15, None, None]]], "expected": [[1], [5, 15], [10]]},
            {"description": "左倾链式树逐层反转", "args": [[3, [2, [1, None, None], None], None]], "expected": [[1], [2], [3]]},
            {"description": "右倾链式树逐层反转", "args": [[1, None, [2, None, [3, None, None]]]], "expected": [[3], [2], [1]]},
            {"description": "只有根和左孩子", "args": [[2, [1, None, None], None]], "expected": [[1], [2]]},
            {"description": "只有根和右孩子", "args": [[2, None, [3, None, None]]], "expected": [[3], [2]]},
            {"description": "负数节点值的树", "args": [[0, [-5, None, None], [8, None, None]]], "expected": [[-5, 8], [0]]},
            {"description": "最底层只有一个节点", "args": [[1, [2, [4, None, None], None], [3, None, None]]], "expected": [[4], [2, 3], [1]]},
            {"description": "遍历不得修改原树", "args": [[10, [5, [1, None, None], None], [15, None, None]]], "expected": [[1], [5, 15], [10]], "immutable": True},
        ],
        "hints": [
            {"level": 1, "title": "先自顶向下再整体反转", "content": "先把每一层从左到右收集成 vector<vector<int>>，最后把这批层整体 std::reverse 即可，不必真的从叶子往上爬。"},
            {"level": 2, "title": "用队列推进层序", "content": "当前层的节点容器就是下一层的输入；为 nullptr 的孩子不要塞进下一层，否则空层会占位。"},
            {"level": 3, "title": "边界在空树和稀疏树", "content": "重点自测：空树返回 {}、单节点返回 [[值]]、缺孩子的稀疏树不要多出空层，且原树不能被改动。"},
        ],
    },
    "2-3": {
        "target": "heap_build",
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<int> heap_build(std::vector<int> items)",
            "includes": ["<vector>"],
        },
        "scenario": (
            "### 变式迁移：自底向上建大顶堆\n\n"
            "原项目只要求对单个下标做一次上浮或下沉。现在把下沉组合成完整的**建堆**算法："
            "实现 `heap_build(items)`，把无序整数容器整理成大顶堆并返回。\n\n"
            "大顶堆用 std::vector<int> 按层序存储：下标 `i` 的左孩子是 `2*i+1`、右孩子是 `2*i+2`，"
            "每个父节点都不小于它的孩子。必须使用自底向上的 Floyd 建堆："
            "从下标 `size()/2 - 1` 开始**倒序**对每个下标执行一次下沉；"
            "下沉时若左右孩子值相等，优先与左孩子交换。"
            "请严格遵循这一过程，不要改用逐个插入的建堆方式，否则同样是合法堆也会与用例不符。\n\n"
            "返回**新容器**，不得修改 `items`；空容器返回 `{}`。\n\n"
            "**迁移重点**：把一次下沉扩展成一趟自底向上的批量下沉，并保持输入不可变。"
        ),
        "cases": [
            {"description": "空列表返回空堆", "args": [[]], "expected": []},
            {"description": "单元素本身就是堆", "args": [[2]], "expected": [2]},
            {"description": "已是大顶堆则保持不变", "args": [[9, 5, 8]], "expected": [9, 5, 8]},
            {"description": "降序列表本身就是大顶堆", "args": [[5, 4, 3, 2, 1]], "expected": [5, 4, 3, 2, 1]},
            {"description": "升序列表需要调整", "args": [[1, 2, 3, 4]], "expected": [4, 2, 3, 1]},
            {"description": "重复元素全部保留", "args": [[3, 1, 4, 1, 5]], "expected": [5, 3, 4, 1, 1]},
            {"description": "全部元素相同", "args": [[7, 7, 7]], "expected": [7, 7, 7]},
            {"description": "相邻重复值", "args": [[2, 1, 2, 1]], "expected": [2, 1, 2, 1]},
            {"description": "负数参与建堆", "args": [[-3, 0, -1, 2]], "expected": [2, 0, -1, -3]},
            {"description": "七元素乱序列表", "args": [[1, 2, 3, 4, 5, 6, 7]], "expected": [7, 5, 6, 4, 2, 1, 3]},
            {"description": "十元素乱序列表", "args": [[5, 3, 8, 1, 9, 2, 7, 4, 6, 0]], "expected": [9, 6, 8, 5, 3, 2, 7, 4, 1, 0]},
            {"description": "正负混合列表", "args": [[10, -5, 7, 3, -8]], "expected": [10, 3, 7, -5, -8]},
            {"description": "建堆不得修改原列表", "args": [[5, 3, 8, 1, 9, 2, 7, 4, 6, 0]], "expected": [9, 6, 8, 5, 3, 2, 7, 4, 1, 0], "immutable": True},
        ],
        "hints": [
            {"level": 1, "title": "叶子不用下沉", "content": "长度 n 的容器里，下标大于等于 n/2 的位置都是叶子，没有孩子，所以起点是 n/2 - 1。"},
            {"level": 2, "title": "倒序下沉", "content": "从起点开始向前扫描，每到一个下标就和较大的孩子交换并继续往下走，直到不需要交换为止。"},
            {"level": 3, "title": "先复制再动手", "content": "返回的是新容器，动手前先复制一份；同时记住相等的兄弟节点要优先换左边，否则用例比对会对不上。"},
        ],
    },
    "2-4": {
        "target": "k_largest",
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<int> k_largest(std::vector<int> items, int k)",
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：用堆求前 k 大的元素\n\n"
            "原项目用堆完成全量排序。现在只要求前 k 个："
            "实现 `k_largest(items, k)`，返回 `items` 中**最大的 k 个元素**，按**降序**排列。\n\n"
            "重复值按出现次数分别计数，例如 `k=2` 时 `[3, 3, 3]` 的前两大的元素是 `[3, 3]`。\n\n"
            "`k` 必须满足 `1 <= k <= items.size()`，否则抛出 std::invalid_argument。不得修改 `items`。\n\n"
            "提示：先把容器整理成大顶堆，再连续取 k 次堆顶（每次取走堆顶、把末尾元素换上来再下沉）。\n\n"
            "**迁移重点**：把堆从「整表排序工具」改造成「有容量上限的筛选结构」，"
            "并额外关注 k 的取值范围校验。"
        ),
        "cases": [
            {"description": "取前三大元素", "args": [[3, 1, 4, 1, 5, 9, 2, 6], 3], "expected": [9, 6, 5]},
            {"description": "k 等于长度时等价于降序排序", "args": [[3, 1, 4, 1, 5, 9, 2, 6], 8], "expected": [9, 6, 5, 4, 3, 2, 1, 1]},
            {"description": "k 为 1 时取最大值", "args": [[3, 1, 4, 1, 5, 9, 2, 6], 1], "expected": [9]},
            {"description": "重复值分别计数", "args": [[3, 3, 3], 2], "expected": [3, 3]},
            {"description": "全部元素相同", "args": [[4, 4, 4, 4], 3], "expected": [4, 4, 4]},
            {"description": "负数参与比较", "args": [[-1, -5, -3], 2], "expected": [-1, -3]},
            {"description": "负数与正数混合", "args": [[-5, 10, 0, -10, 3], 2], "expected": [10, 3]},
            {"description": "降序列表取前三", "args": [[5, 4, 3, 2, 1], 3], "expected": [5, 4, 3]},
            {"description": "升序列表取前二", "args": [[1, 2, 3, 4, 5], 2], "expected": [5, 4]},
            {"description": "单元素列表取全部", "args": [[7], 1], "expected": [7]},
            {"description": "十元素列表取前四", "args": [[5, 3, 8, 1, 9, 2, 7, 4, 6, 0], 4], "expected": [9, 8, 7, 6]},
            {"description": "取值不得修改原列表", "args": [[5, 3, 8, 1, 9, 2, 7, 4, 6, 0], 4], "expected": [9, 8, 7, 6], "immutable": True},
            {"description": "拒绝 k 为 0", "args": [[1, 2, 3], 0], "exception": "invalid_argument"},
            {"description": "拒绝负的 k", "args": [[1, 2, 3], -1], "exception": "invalid_argument"},
            {"description": "拒绝超过长度的 k", "args": [[1, 2, 3], 4], "exception": "invalid_argument"},
            {"description": "空列表无法取值", "args": [[], 1], "exception": "invalid_argument"},
        ],
        "hints": [
            {"level": 1, "title": "为什么要用堆", "content": "全排序要 O(n log n)，而只关心前 k 个时可以只维护 k 个候选，别直接把整表排完再切片。"},
            {"level": 2, "title": "先建大顶堆再取 k 次", "content": "建堆后堆顶是最大值，取走堆顶、把末尾元素换上来下沉，重复 k 次就是降序的前 k 大。"},
            {"level": 3, "title": "别漏掉范围校验", "content": "先校验 k 落在 1..items.size() 内；空容器配任何 k 都应报错。"},
        ],
    },
    "3-1": {
        "target": "has_cycle",
        "language": "cpp",
        "cpp": {
            "signature": "bool has_cycle(std::vector<std::vector<int>> edges, int node_count)",
            "includes": ["<stdexcept>", "<algorithm>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：无向图判环\n\n"
            "原项目建立邻接表并做深度优先遍历。现在用同一套能力回答一个问题："
            "实现 `has_cycle(edges, node_count)`，判断这张**无向图**中是否存在环，返回布尔值。\n\n"
            "`edges` 是边容器，每条边是长度为 2 的 `[端点, 端点]`；"
            "`node_count` 是节点总数，节点编号为 `0 ~ node_count-1`。\n\n"
            "出现**自环**、边长度不为 2、端点越界或节点数非法时抛出 std::invalid_argument。"
            "重复出现的同一条边（如 `[0, 1]` 与 `[1, 0]`）只是同一条边，不算环。不得修改 `edges`。\n\n"
            "提示：用并查集，合并时发现两端已经在同一集合即有环。\n\n"
            "**迁移重点**：遍历的骨架不变，但要把「访问顺序」升级为「识别回边」，"
            "并处理重复边、非连通图等边界。"
        ),
        "cases": [
            {"description": "没有任何边的图", "args": [[], 3], "expected": False},
            {"description": "单节点无边图", "args": [[], 1], "expected": False},
            {"description": "一条边不构成环", "args": [[[0, 1]], 2], "expected": False},
            {"description": "链式图不构成环", "args": [[[0, 1], [1, 2], [2, 3]], 4], "expected": False},
            {"description": "树形图不构成环", "args": [[[0, 1], [0, 2], [1, 3], [1, 4]], 5], "expected": False},
            {"description": "四边形首尾相接本身就构成环", "args": [[[0, 1], [1, 2], [2, 3], [3, 0]], 4], "expected": True},
            {"description": "六节点长路径仍然无环", "args": [[[0, 1], [1, 2], [2, 3], [3, 4]], 6], "expected": False},
            {"description": "三角形存在环", "args": [[[0, 1], [1, 2], [0, 2]], 3], "expected": True},
            {"description": "四边形加一条对角线存在环", "args": [[[0, 1], [1, 2], [2, 3], [3, 0], [0, 2]], 4], "expected": True},
            {"description": "并列的重复边不算环", "args": [[[0, 1], [1, 0]], 2], "expected": False},
            {"description": "重复三次的同一条边不算环", "args": [[[0, 1], [0, 1], [1, 0]], 3], "expected": False},
            {"description": "重复边中夹着真实的环", "args": [[[0, 1], [1, 2], [2, 0], [0, 2]], 3], "expected": True},
            {"description": "只有其中一个连通分量有环", "args": [[[0, 1], [1, 2], [2, 0], [3, 4]], 5], "expected": True},
            {"description": "两个连通分量都无环", "args": [[[0, 1], [2, 3], [3, 4]], 5], "expected": False},
            {"description": "孤立节点不影响判定", "args": [[[1, 2]], 4], "expected": False},
            {"description": "判定不得修改边列表", "args": [[[0, 1], [1, 2], [0, 2]], 3], "expected": True, "immutable": True},
            {"description": "拒绝自环", "args": [[[0, 0]], 2], "exception": "invalid_argument"},
            {"description": "拒绝越界的端点", "args": [[[0, 5]], 3], "exception": "invalid_argument"},
            {"description": "拒绝负数端点", "args": [[[0, -1]], 3], "exception": "invalid_argument"},
            {"description": "拒绝长度不为 2 的边", "args": [[[0, 1, 2]], 3], "exception": "invalid_argument"},
            {"description": "拒绝长度不为 2 的单元素边", "args": [[[0]], 3], "exception": "invalid_argument"},
            {"description": "拒绝节点数为 0", "args": [[], 0], "exception": "invalid_argument"},
        ],
        "hints": [
            {"level": 1, "title": "环就是回边", "content": "用并查集：合并前先查两端各自的根，若已经在同一集合里，再连这条边就会成环。"},
            {"level": 2, "title": "去重后按边合并", "content": "同一条边正反写两遍只是一条边，先规范化（小的端点在前）去重再合并，避免误判成环。"},
            {"level": 3, "title": "先把边整理干净", "content": "先校验并去重：自环要按契约直接报错，而不是当成环返回 true。"},
        ],
    },
    "3-2": {
        "target": "count_provinces",
        "language": "cpp",
        "cpp": {
            "signature": "int count_provinces(std::vector<std::vector<int>> matrix)",
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：用并查集统计省份数量\n\n"
            "原项目直接操作 parent 数组做查找与路径压缩。现在把并查集用到一个真实任务上："
            "实现 `count_provinces(matrix)`，统计邻接矩阵中有多少个**省份**（互相连通的节点集合）。"
            "若 `matrix[i][j] == 1`，表示城市 i 与城市 j 直接相连——直接相连或间接相连的城市属于同一个省。\n\n"
            "`matrix` 是 `n x n` 的邻接矩阵（`n >= 1`）：每一行长度相同，"
            "每个元素是整数 `0` 或 `1`，对角线必须是 `1`，且矩阵必须是对称的"
            "（`matrix[i][j] == matrix[j][i]`）。任何一项不满足都抛出 std::invalid_argument。\n\n"
            "请用并查集实现：遍历上三角，遇到 1 就把两个城市合并，最后统计根的数量。"
            "不得修改 `matrix`。\n\n"
            "**迁移重点**：把 parent 数组上的单步操作组合成完整的连通性统计，"
            "并把并查集从「边列表」迁移到「邻接矩阵」这一新输入形态。"
        ),
        "cases": [
            {"description": "两个直接相连的城市与一个孤立城市", "args": [[[1, 1, 0], [1, 1, 0], [0, 0, 1]]], "expected": 2},
            {"description": "三座互不相连的城市", "args": [[[1, 0, 0], [0, 1, 0], [0, 0, 1]]], "expected": 3},
            {"description": "所有城市两两相连", "args": [[[1, 1, 1], [1, 1, 1], [1, 1, 1]]], "expected": 1},
            {"description": "只有一个城市", "args": [[[1]]], "expected": 1},
            {"description": "两个相连省份", "args": [[[1, 0, 0, 0], [0, 1, 1, 0], [0, 1, 1, 0], [0, 0, 0, 1]]], "expected": 3},
            {"description": "链式相连合成一个省份", "args": [[[1, 1, 0], [1, 1, 1], [0, 1, 1]]], "expected": 1},
            {"description": "星形结构合成一个省份", "args": [[[1, 1, 1, 1], [1, 1, 0, 0], [1, 0, 1, 0], [1, 0, 0, 1]]], "expected": 1},
            {"description": "两两成对的两组城市", "args": [[[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 1], [0, 0, 1, 1]]], "expected": 2},
            {"description": "长链首尾相连", "args": [[[1, 1, 0, 0, 0], [1, 1, 1, 0, 0], [0, 1, 1, 1, 0], [0, 0, 1, 1, 1], [0, 0, 0, 1, 1]]], "expected": 1},
            {"description": "统计不得修改邻接矩阵", "args": [[[1, 1, 0], [1, 1, 0], [0, 0, 1]]], "expected": 2, "immutable": True},
            {"description": "拒绝空矩阵", "args": [[]], "exception": "invalid_argument"},
            {"description": "拒绝非方阵", "args": [[[1, 1], [1]]], "exception": "invalid_argument"},
            {"description": "拒绝出现 0/1 以外的值", "args": [[[1, 2], [2, 1]]], "exception": "invalid_argument"},
            {"description": "拒绝对角线不为 1", "args": [[[0, 0], [0, 0]]], "exception": "invalid_argument"},
            {"description": "拒绝非对称矩阵", "args": [[[1, 1, 0], [0, 1, 0], [0, 0, 1]]], "exception": "invalid_argument"},
        ],
        "hints": [
            {"level": 1, "title": "矩阵只是边的另一种写法", "content": "matrix[i][j] == 1 就等价于一条连接 i 与 j 的边，先想清楚怎么把它喂给并查集。"},
            {"level": 2, "title": "只扫上三角", "content": "矩阵是对称的，只看 j > i 的那一半就够；每遇到一个 1 就 union(i, j)，最后数一数有多少个根。"},
            {"level": 3, "title": "校验要配上契约", "content": "先校验方阵、元素只能是 0/1、对角线为 1 且矩阵对称；另外别忘了合并前先各自查根，否则统计会出错。"},
        ],
    },
    "3-3": {
        "target": "bfs_all_distances",
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<int> bfs_all_distances(std::vector<std::vector<int>> edges, int node_count, int start)",
            "includes": ["<stdexcept>", "<algorithm>", "<queue>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：一次 BFS 求出到所有节点的最短距离\n\n"
            "原项目只求起点到某一个终点的最短路径。现在把同一套 BFS 能力扩展成"
            "**单源全图最短路**：实现 `bfs_all_distances(edges, node_count, start)`，"
            "返回一个长度为 `node_count` 的容器，第 i 项是 `start` 到节点 i 的最短边数；"
            "不可达的节点记为 `-1`，起点到自己是 `0`。\n\n"
            "`edges` 是无向边容器，每条边是长度为 2 的整数容器；节点编号为 `0 ~ node_count-1`。\n\n"
            "`start` 越界、出现自环、边长度不为 2、端点越界或节点数非法时抛出 std::invalid_argument。"
            "同一条边重复出现只算一条。不得修改 `edges`。\n\n"
            "提示：BFS 按层扩散，第一次访问到某个节点时的层数就是最短距离。\n\n"
            "**迁移重点**：把「到达即停」的路径搜索改成「扩散完整个连通分量」的距离表，"
            "并正确处理不可达与重复边的边界。"
        ),
        "cases": [
            {"description": "链式图逐跳扩散", "args": [[[0, 1], [1, 2]], 3, 0], "expected": [0, 1, 2]},
            {"description": "从中间节点出发", "args": [[[0, 1], [1, 2]], 3, 1], "expected": [1, 0, 1]},
            {"description": "单节点图的距离表", "args": [[], 1, 0], "expected": [0]},
            {"description": "不可达节点记为 -1", "args": [[[0, 1]], 3, 0], "expected": [0, 1, -1]},
            {"description": "起点是孤立节点", "args": [[[1, 2]], 3, 0], "expected": [0, -1, -1]},
            {"description": "四边形图上各点的距离", "args": [[[0, 1], [1, 2], [2, 3], [3, 0]], 4, 0], "expected": [0, 1, 2, 1]},
            {"description": "多条路径取最短的那条", "args": [[[0, 1], [1, 3], [0, 2], [2, 3]], 4, 0], "expected": [0, 1, 1, 2]},
            {"description": "重复边不影响距离", "args": [[[0, 1], [1, 0], [1, 2]], 3, 0], "expected": [0, 1, 2]},
            {"description": "两个连通分量都可达性不同", "args": [[[0, 1], [2, 3], [3, 4]], 5, 2], "expected": [-1, -1, 0, 1, 2]},
            {"description": "星形图上所有叶子距离为 1", "args": [[[0, 1], [0, 2], [0, 3]], 4, 0], "expected": [0, 1, 1, 1]},
            {"description": "更长的链式图", "args": [[[0, 1], [1, 2], [2, 3], [3, 4]], 5, 0], "expected": [0, 1, 2, 3, 4]},
            {"description": "搜索不得修改边列表", "args": [[[0, 1], [2, 3], [3, 4]], 5, 2], "expected": [-1, -1, 0, 1, 2], "immutable": True},
            {"description": "拒绝越界的起点", "args": [[[0, 1]], 2, 5], "exception": "invalid_argument"},
            {"description": "拒绝负数起点", "args": [[[0, 1]], 2, -1], "exception": "invalid_argument"},
            {"description": "拒绝自环边", "args": [[[0, 0]], 2, 0], "exception": "invalid_argument"},
            {"description": "拒绝越界的边端点", "args": [[[0, 5]], 3, 0], "exception": "invalid_argument"},
            {"description": "拒绝长度不为 2 的边", "args": [[[0, 1, 2]], 3, 0], "exception": "invalid_argument"},
            {"description": "拒绝节点数为 0", "args": [[], 0, 0], "exception": "invalid_argument"},
        ],
        "hints": [
            {"level": 1, "title": "距离就是层号", "content": "先给所有节点记为 -1（未访问），起点记 0；BFS 从起点一层层往外扩，邻居的距离等于当前距离加一。"},
            {"level": 2, "title": "先建邻接表再扩散", "content": "把无向边整理成邻接表，用队列从起点扩散；只有还没被访问过的邻居才入队，避免重复计数。"},
            {"level": 3, "title": "边界全在不可达与重复边上", "content": "重点自测：不可达节点必须是 -1、起点到自己是 0、同一条边正反写两遍不会改变结果，且边列表不被改动。"},
        ],
    },
    "4-1": {
        "target": "toolbox_call_many",
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<std::vector<int>> toolbox_call_many(std::vector<std::string> names, std::vector<std::vector<int>> datas)",
            "includes": ["<stdexcept>", "<string>", "<functional>", "<map>", "<algorithm>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        "scenario": (
            "### 变式迁移：批量调用算法工具箱\n\n"
            "原项目一次只调用工具箱里的一个操作。现在把能力扩展到**批量调度**："
            "实现 `toolbox_call_many(names, datas)`，按顺序执行一批工具箱调用。\n\n"
            "`names[i]` 是第 i 次调用的操作名，`datas[i]` 是它的输入容器。返回一个容器，"
            "第 i 项就是第 i 次调用的返回值，顺序与输入完全一致。工具箱内登记本实验已实现的"
            "三个操作，语义不变：`sort`（升序排序）、`reverse`（反转）、`dedup`（去重，保留首次出现）。\n\n"
            "`names` 与 `datas` 长度不一致、或出现未登记的操作名时抛出 std::invalid_argument。"
            "注册表请在函数内部构造（`std::map<std::string, std::function<...>>`），"
            "再由 `toolbox_call_many` 使用。不得修改输入容器。\n\n"
            "**迁移重点**：把「单次分发」升级为「批量调度」，同时保证返回顺序与输入不可变。"
        ),
        "cases": [
            {"description": "空的调用列表返回空列表", "args": [[], []], "expected": []},
            {"description": "批量排序", "args": [["sort"], [[3, 1, 2]]], "expected": [[1, 2, 3]]},
            {"description": "两个操作按顺序返回", "args": [["sort", "reverse"], [[3, 1, 2], [1, 2, 3]]], "expected": [[1, 2, 3], [3, 2, 1]]},
            {"description": "批量去重", "args": [["dedup"], [[1, 2, 2, 3]]], "expected": [[1, 2, 3]]},
            {"description": "拒绝 names 与 datas 长度不一致", "args": [["sort"], []], "exception": "invalid_argument"},
            {"description": "拒绝未登记的操作名", "args": [["missing"], [[1]]], "exception": "invalid_argument"},
        ],
        "hints": [
            {"level": 1, "title": "注册表要在函数内部构造", "content": "先写一个返回 std::map 的内部构造函数，再让批量入口去用它。"},
            {"level": 2, "title": "先校验整批再执行", "content": "先确认 names 与 datas 长度一致、每个操作名都已登记，然后再进入执行循环。"},
            {"level": 3, "title": "异常不要包装", "content": "未登记的操作名要抛 std::invalid_argument；别用默认值兜底。"},
        ],
    },
    "4-2": {
        "target": "count_inversions",
        "language": "cpp",
        "cpp": {
            "signature": "int count_inversions(std::vector<int> items)",
            "includes": ["<vector>", "<utility>"],
        },
        "scenario": (
            "### 变式迁移：用归并排序统计逆序对\n\n"
            "原项目用归并排序把容器排好。现在不改排序本身，而是让它**顺带数出信息**："
            "实现 `count_inversions(items)`，返回容器中的逆序对数量。"
            "下标满足 `i < j` 且 `items[i] > items[j]` 的数对算作一个逆序对。\n\n"
            "直接双重循环是 O(n^2)，请用归并排序在 O(n log n) 内完成："
            "归并两段有序序列时，只要右段的元素先被取出，"
            "就说明左段剩下的所有元素都大于它，一次性累加这一段长度。\n\n"
            "不得修改 `items`；空容器和单元素容器都返回 `0`。\n\n"
            "**迁移重点**：把归并排序的合并步骤当作计数时机，"
            "理解「排序过程中天然能拿到逆序信息」，并把无副作用的输入契约保持住。"
        ),
        "cases": [
            {"description": "空列表没有逆序对", "args": [[]], "expected": 0},
            {"description": "单元素列表没有逆序对", "args": [[1]], "expected": 0},
            {"description": "已升序没有逆序对", "args": [[1, 2, 3, 4]], "expected": 0},
            {"description": "全部逆序的三元素列表", "args": [[3, 2, 1]], "expected": 3},
            {"description": "交错乱序的列表", "args": [[2, 4, 1, 3]], "expected": 3},
            {"description": "重复元素只统计严格大于", "args": [[2, 1, 2, 1]], "expected": 3},
            {"description": "全部元素相同", "args": [[7, 7, 7]], "expected": 0},
            {"description": "负数参与比较", "args": [[-1, -3, 2]], "expected": 1},
            {"description": "正负混合的列表", "args": [[0, -1, 2, -3, 1]], "expected": 5},
            {"description": "十元素完全逆序", "args": [[10, 9, 8, 7, 6, 5, 4, 3, 2, 1]], "expected": 45},
            {"description": "只有一对逆序", "args": [[1, 2, 3, 5, 4]], "expected": 1},
            {"description": "统计不得修改原列表", "args": [[0, -1, 2, -3, 1]], "expected": 5, "immutable": True},
        ],
        "hints": [
            {"level": 1, "title": "逆序对藏在合并里", "content": "两段都已经有序——只要右段的数先出来，左段还没来得及取出的数就全都比它大。"},
            {"level": 2, "title": "一次累加一段长度", "content": "合并时若取右段元素，就让计数加上「左段剩余元素个数」，不需要再逐个比较。"},
            {"level": 3, "title": "相等不算逆序", "content": "只有严格大于才是逆序对，所以取数时必须先取左段的相等元素，否则重复值会被多算。"},
        ],
    },
    "4-3": {
        "target": "subarray_sum_equals_k",
        "language": "cpp",
        "cpp": {
            "signature": "int subarray_sum_equals_k(std::vector<int> nums, int k)",
            "includes": ["<vector>", "<unordered_map>"],
        },
        "scenario": (
            "### 变式迁移：前缀和 + 哈希表统计和为 k 的子数组\n\n"
            "原项目用哈希表把两数之和从 O(n^2) 降到 O(n)。现在把同一手法迁移到**子数组计数**："
            "实现 `subarray_sum_equals_k(nums, k)`，返回和恰好等于 `k` 的**连续子数组**个数。\n\n"
            "元素可以是负数、零或正数；子数组至少要有一个元素。"
            "`nums = [1, 1, 1]`、`k = 2` 时应返回 `2`，因为前两个和后两个各构成一个子数组。\n\n"
            "不得修改 `nums`。\n\n"
            "提示：维护「当前前缀和」以及「每个前缀和出现过多少次」。"
            "走到位置 i 时，若前缀和减去 `k` 曾经出现过 c 次，就说明有 c 个子数组以 i 结尾且和为 k。"
            "别忘记在开始前把前缀和 `0` 的计数记为 1。\n\n"
            "**迁移重点**：把「查找一个补数」扩展为「累加补数的出现次数」，"
            "并注意负数与零会让前缀和重复出现，不能只记第一次。"
        ),
        "cases": [
            {"description": "三个 1 中取和为 2 的子数组", "args": [[1, 1, 1], 2], "expected": 2},
            {"description": "连续递增序列中和为 3 的子数组", "args": [[1, 2, 3], 3], "expected": 2},
            {"description": "含零的子数组", "args": [[1, -1, 0], 0], "expected": 3},
            {"description": "全零数组", "args": [[0, 0, 0], 0], "expected": 6},
            {"description": "全负数数组", "args": [[-1, -1], -1], "expected": 2},
            {"description": "正负交替的前缀和重复", "args": [[1, -1, 1, -1], 0], "expected": 4},
            {"description": "负数使前缀和回落", "args": [[1, -1, -1, 1], 0], "expected": 3},
            {"description": "没有满足条件的子数组", "args": [[1, 2, 3], 100], "expected": 0},
            {"description": "空数组没有子数组", "args": [[], 0], "expected": 0},
            {"description": "单元素命中", "args": [[5], 5], "expected": 1},
            {"description": "单元素不命中", "args": [[5], 3], "expected": 0},
            {"description": "负数 k 的情形", "args": [[-3, -3, 3], -3], "expected": 3},
            {"description": "较长数组的计数", "args": [[3, 4, 7, 2, -3, 1, 4, 2], 7], "expected": 4},
            {"description": "计数不得修改原数组", "args": [[3, 4, 7, 2, -3, 1, 4, 2], 7], "expected": 4, "immutable": True},
        ],
        "hints": [
            {"level": 1, "title": "子数组和等于两个前缀和之差", "content": "把「求一段区间的和」换成「两个前缀和相减」，问题就变成了在历史前缀和里找等于当前前缀和减 k 的值。"},
            {"level": 2, "title": "计数而不是判存在", "content": "用 unordered_map 记录每个前缀和出现了几次：答案累加的是「当前前缀和 - k」的出现次数。"},
            {"level": 3, "title": "初始状态和重复值", "content": "开始前先记 {0: 1}，否则以第一个元素开头的合法子数组会被漏掉；负数与零会让同一个前缀和反复出现，必须累计次数而不是覆盖。"},
        ],
    },
}
