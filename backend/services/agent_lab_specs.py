"""关卡声明。13 关全部只用标准库实现，零第三方依赖（缺省 Python，1-1 为 C++ 试点）。

语言由每关的 "language" 字段声明，缺省 "python"。C++ 关卡额外声明 "cpp"
契约（signature / includes / exception_map），用例里的 exception 取语言中立
的 token（如 out_of_range），由该关的 exception_map 映射到具体的 C++ 类型。

用例约定（服务端私有，不会通过资源接口发送给浏览器；学生只能看到公开样例与
失败场景名称）：
- {"args": [...], "expected": ...} 要求返回值等于 expected；
- {"args": [...], "exception": <token>} 要求抛出指定异常：Python 关卡按内置异常名解析（SAFE_BUILTINS），C++ 关卡由该关的 exception_map 映射到具体类型；
- "immutable": True 要求调用前后输入对象完全不变；
- "func" 字段只在 Python 判题路径生效（改调该函数）；C++ 判题路径只调用
  spec["target"]。

本文件不再使用 mode=tool_call / tool_plan / checkpoint / sqlalchemy_query
等专用判题分支。
"""

# 二叉树统一用 [值, 左子树, 右子树] 表示，空树为 None。
_EMPTY_TREE_CASES = "树用 [值, 左, 右] 嵌套表示，None 表示空树"

SPECS = {
    # ══════════════════════════════════════════════════════════
    #  阶段一：线性结构与基础容器
    # ══════════════════════════════════════════════════════════
    "1-1": {
        "target": "array_insert",
        "targets": ["array_insert"],
        # 缺省视为 python。语言决定工作区文件名、阶段检查文案与判题执行路径。
        "language": "cpp",
        "cpp": {
            "signature": "std::vector<int> array_insert(std::vector<int> items, int index, int value)",
            "includes": ["<vector>", "<stdexcept>", "<string>"],
            "exception_map": {"out_of_range": "std::out_of_range"},
        },
        # exception 用语言中立的 token，由本关的 exception_map 映射到 C++ 类型。
        # 原来 10 条「传字符串/浮点/布尔当索引」的用例在 C++ 里编译期就挡掉了
        # （bool→int、double→int 是静默转换，不报错），因此改写成 C++ 真正的
        # 边界考点：单元素、size()-1、重复元素、下界越界。
        "cases": [
            {"description": "在中间插入元素", "args": [[1, 2, 3], 1, 9], "expected": [1, 9, 2, 3]},
            {"description": "在头部插入元素", "args": [[1, 2, 3], 0, 9], "expected": [9, 1, 2, 3]},
            {"description": "在末尾插入元素", "args": [[1, 2, 3], 3, 9], "expected": [1, 2, 3, 9]},
            {"description": "向空容器插入", "args": [[], 0, 5], "expected": [5]},
            {"description": "插入后不修改原容器", "args": [[1, 2, 3], 1, 9], "expected": [1, 9, 2, 3], "immutable": True},
            {"description": "拒绝越界索引", "args": [[1, 2, 3], 4, 9], "exception": "out_of_range"},
            {"description": "拒绝负数索引", "args": [[1, 2, 3], -1, 9], "exception": "out_of_range"},
            {"description": "单元素容器插入到头部", "args": [[7], 0, 9], "expected": [9, 7]},
            {"description": "单元素容器插入到末尾", "args": [[7], 1, 9], "expected": [7, 9]},
            {"description": "较长容器中间插入", "args": [[1, 2, 3, 4, 5], 2, 0], "expected": [1, 2, 0, 3, 4, 5]},
            {"description": "插入到 size()-1 位置", "args": [[1, 2, 3, 4], 3, 9], "expected": [1, 2, 3, 9, 4]},
            {"description": "含重复元素的容器", "args": [[5, 5, 5], 1, 5], "expected": [5, 5, 5, 5]},
            {"description": "下界越界", "args": [[1, 2, 3], -4, 9], "exception": "out_of_range"},
        ],
    },
    "1-2": {
        "target": "reverse_list",
        "targets": ["reverse_list"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "reverse_list": "Node* reverse_list(Node* head)",
            },
        },
        # 节点用公共类型 struct Node { int value; Node* next; }，空链表为 nullptr。
        # Python 里「节点不是字典 / 缺 value 或 next 键 / next 类型非法」这些
        # 结构错误用例在 C++ 里是编译期保证的（Node 的字段类型固定），因此删掉；
        # 保留空链 / 单节点 / 多节点反转与「不修改原链表」这些核心考点。
        "cases": [
            {"description": "反转空链表", "args": [None], "expected": None},
            {"description": "反转单节点链表", "args": [{"value": 1, "next": None}], "expected": {"value": 1, "next": None}},
            {"description": "反转两节点链表", "args": [{"value": 1, "next": {"value": 2, "next": None}}], "expected": {"value": 2, "next": {"value": 1, "next": None}}},
            {"description": "反转三节点链表", "args": [{"value": 1, "next": {"value": 2, "next": {"value": 3, "next": None}}}], "expected": {"value": 3, "next": {"value": 2, "next": {"value": 1, "next": None}}}},
            {"description": "反转四节点链表", "args": [{"value": 1, "next": {"value": 2, "next": {"value": 3, "next": {"value": 4, "next": None}}}}], "expected": {"value": 4, "next": {"value": 3, "next": {"value": 2, "next": {"value": 1, "next": None}}}}},
            {"description": "反转五节点链表", "args": [{"value": 1, "next": {"value": 2, "next": {"value": 3, "next": {"value": 4, "next": {"value": 5, "next": None}}}}}], "expected": {"value": 5, "next": {"value": 4, "next": {"value": 3, "next": {"value": 2, "next": {"value": 1, "next": None}}}}}},
            {"description": "反转后不修改原链表", "args": [{"value": 1, "next": {"value": 2, "next": {"value": 3, "next": None}}}], "expected": {"value": 3, "next": {"value": 2, "next": {"value": 1, "next": None}}}, "immutable": True},
        ],
    },
    "1-3": {
        "target": "eval_rpn",
        "targets": ["eval_rpn"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "eval_rpn": "int eval_rpn(std::vector<std::string> tokens)",
            },
            "includes": ["<stdexcept>", "<string>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # tokens 是 std::vector<std::string>，所以「非字符串 token」「非列表输入」
        # 两类错误在 C++ 里是编译期保证的，直接删掉；除法用 C++ 原生整数除法
        # （天然向零截断）。其余非法业务状态（未知运算符、操作数不足、除零、
        # 栈残留、非法数字 token）改抛 std::invalid_argument。
        "cases": [
            {"description": "基础四则表达式", "args": [["2", "1", "+", "3", "*"]], "expected": 9},
            {"description": "先除后加", "args": [["4", "13", "5", "/", "+"]], "expected": 6},
            {"description": "较长表达式求值", "args": [["10", "6", "9", "3", "+", "-11", "*", "/", "*", "17", "+", "5", "+"]], "expected": 22},
            {"description": "单个数字", "args": [["42"]], "expected": 42},
            {"description": "负数token参与运算", "args": [["-3", "4", "*"]], "expected": -12},
            {"description": "减法区分左右操作数", "args": [["5", "3", "-"]], "expected": 2},
            {"description": "减法不满足交换律", "args": [["3", "5", "-"]], "expected": -2},
            {"description": "连续运算是左结合", "args": [["20", "3", "-", "4", "-"]], "expected": 13},
            # ── 除法必须向零截断：C++ 整数除法天然满足 ──
            {"description": "除法向零截断（负被除数）", "args": [["-7", "2", "/"]], "expected": -3},
            {"description": "除法向零截断（负除数）", "args": [["6", "-2", "/"]], "expected": -3},
            # ── 边界与非法输入：栈必须恰好回到一个元素 ──
            {"description": "拒绝未知运算符", "args": [["1", "2", "%"]], "exception": "invalid_argument"},
            {"description": "拒绝操作数不足", "args": [["1", "+"]], "exception": "invalid_argument"},
            {"description": "拒绝只有运算符", "args": [["+"]], "exception": "invalid_argument"},
            {"description": "拒绝剩余未消费的操作数", "args": [["1", "2"]], "exception": "invalid_argument"},
            {"description": "拒绝空表达式", "args": [[]], "exception": "invalid_argument"},
            {"description": "拒绝非数字token", "args": [["a", "1", "+"]], "exception": "invalid_argument"},
            {"description": "拒绝浮点token", "args": [["1.5", "1", "+"]], "exception": "invalid_argument"},
            {"description": "拒绝除以零", "args": [["1", "0", "/"]], "exception": "invalid_argument"},
        ],
    },

    # ══════════════════════════════════════════════════════════
    #  阶段二：树与堆
    # ══════════════════════════════════════════════════════════
    "2-1": {
        "target": "bst_insert",
        "targets": ["bst_insert", "bst_search"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "bst_insert": "TreeNode* bst_insert(TreeNode* root, int value)",
                "bst_search": "bool bst_search(TreeNode* root, int value)",
            },
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # 树用公共类型 struct TreeNode { int value; TreeNode* left; TreeNode* right; }，
        # nullptr 表示空树。Python 里「值不是整数/树不是列表/节点长度不为 3」这些
        # 类型错误在 C++ 里是编译期保证的，删除；保留重复值拒绝与「树必须满足
        # 左小右大」这两类业务校验，改抛 std::invalid_argument。
        "cases": [
            {"description": "向空树插入根节点", "args": [None, 5], "expected": [5, None, None]},
            {"description": "插入到左子树", "args": [[10, None, None], 5], "expected": [10, [5, None, None], None]},
            {"description": "插入到右子树", "args": [[10, None, None], 15], "expected": [10, None, [15, None, None]]},
            {"description": "插入到已有子树之间", "args": [[10, [5, None, None], [15, None, None]], 12], "expected": [10, [5, None, None], [15, [12, None, None], None]]},
            {"description": "插入当前最小值", "args": [[10, [5, None, None], [15, None, None]], 1], "expected": [10, [5, [1, None, None], None], [15, None, None]]},
            {"description": "插入当前最大值", "args": [[10, [5, None, None], [15, None, None]], 20], "expected": [10, [5, None, None], [15, None, [20, None, None]]]},
            {"description": "插入时不得修改原树", "args": [[10, [5, None, None], [15, None, None]], 12], "expected": [10, [5, None, None], [15, [12, None, None], None]], "immutable": True},
            # ── 二分搜索树不允许重复值，重复插入必须报错 ──
            {"description": "拒绝重复的根值", "args": [[10, None, None], 10], "exception": "invalid_argument"},
            {"description": "拒绝重复的深层值", "args": [[10, [5, None, None], [15, None, None]], 15], "exception": "invalid_argument"},
            # ── 树必须满足「左小右大」的 BST 不变式 ──
            {"description": "拒绝左子树大于根的非法树", "args": [[10, [15, None, None], None], 3], "exception": "invalid_argument"},
            {"description": "拒绝深层违反 BST 顺序的树", "args": [[20, [10, [25, None, None], None], None], 3], "exception": "invalid_argument"},
            # ── bst_search：查找不得修改树，未命中返回 False ──
            {"description": "查找命中根节点", "func": "bst_search", "args": [[10, [5, None, None], [15, None, None]], 10], "expected": True},
            {"description": "查找命中左叶子", "func": "bst_search", "args": [[10, [5, None, None], [15, None, None]], 5], "expected": True},
            {"description": "查找命中右叶子", "func": "bst_search", "args": [[10, [5, None, None], [15, None, None]], 15], "expected": True},
            {"description": "查找不存在的值", "func": "bst_search", "args": [[10, [5, None, None], [15, None, None]], 7], "expected": False},
            {"description": "在空树中查找", "func": "bst_search", "args": [None, 5], "expected": False},
            {"description": "查找不得修改原树", "func": "bst_search", "args": [[10, [5, None, None], [15, None, None]], 15], "expected": True, "immutable": True},
        ],
    },
    "2-2": {
        "target": "bst_inorder",
        "targets": ["bst_inorder", "bst_level_order"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "bst_inorder": "std::vector<int> bst_inorder(TreeNode* root)",
                "bst_level_order": "std::vector<std::vector<int>> bst_level_order(TreeNode* root)",
            },
        },
        # 树结构由 TreeNode 保证（指针/字段类型固定），Python 里的「非法树」用例
        # 不再存在，删除；保留中序升序、层序分层、缺失节点不占位等核心考点。
        "cases": [
            {"description": "空树的中序遍历", "args": [None], "expected": []},
            {"description": "单节点树的中序遍历", "args": [[1, None, None]], "expected": [1]},
            {"description": "三层满树的中序遍历", "args": [[10, [5, None, None], [15, None, None]]], "expected": [5, 10, 15]},
            {"description": "不平衡树的中序遍历", "args": [[10, [5, [1, None, None], None], [15, None, None]]], "expected": [1, 5, 10, 15]},
            {"description": "只有右子树的链式中序", "args": [[1, None, [2, None, [3, None, None]]]], "expected": [1, 2, 3]},
            {"description": "只有左子树的链式中序", "args": [[3, [2, [1, None, None], None], None]], "expected": [1, 2, 3]},
            {"description": "中序遍历不得修改原树", "args": [[10, [5, None, None], [15, None, None]]], "expected": [5, 10, 15], "immutable": True},
            # ── bst_level_order：层序遍历按层返回 ──
            {"description": "空树的层序遍历", "func": "bst_level_order", "args": [None], "expected": []},
            {"description": "单节点树的层序遍历", "func": "bst_level_order", "args": [[1, None, None]], "expected": [[1]]},
            {"description": "三层满树的层序遍历", "func": "bst_level_order", "args": [[10, [5, None, None], [15, None, None]]], "expected": [[10], [5, 15]]},
            {"description": "缺失节点不占位置", "func": "bst_level_order", "args": [[10, [5, [1, None, None], None], [15, None, None]]], "expected": [[10], [5, 15], [1]]},
            {"description": "单链树的层序逐层返回", "func": "bst_level_order", "args": [[1, None, [2, None, [3, None, None]]]], "expected": [[1], [2], [3]]},
            {"description": "层序遍历不得修改原树", "func": "bst_level_order", "args": [[10, [5, None, None], [15, None, None]]], "expected": [[10], [5, 15]], "immutable": True},
        ],
    },
    "2-3": {
        "target": "heap_shift_up",
        "targets": ["heap_shift_up", "heap_shift_down"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "heap_shift_up": "std::vector<int> heap_shift_up(std::vector<int> heap, int index)",
                "heap_shift_down": "std::vector<int> heap_shift_down(std::vector<int> heap, int index, int size)",
            },
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # 大顶堆用 std::vector<int> 按层序存储：下标 i 的父节点是 (i-1)/2，子节点是 2i+1 与 2i+2。
        # Python 里「下标是浮点/布尔、堆不是列表、含非整数元素」这些类型错误在 C++ 里
        # 是编译期保证的，删除；保留下标越界与 size 非法这两类业务校验。
        "cases": [
            {"description": "根节点无需上浮", "args": [[5, 3, 4], 0], "expected": [5, 3, 4]},
            {"description": "单元素堆无需上浮", "args": [[7], 0], "expected": [7]},
            {"description": "上浮一层", "args": [[5, 3, 8], 2], "expected": [8, 3, 5]},
            {"description": "连续上浮两层", "args": [[9, 5, 8, 4, 2, 7, 10], 6], "expected": [10, 5, 9, 4, 2, 7, 8]},
            {"description": "父节点已更大则原地不动", "args": [[9, 5, 8, 1, 2, 3, 7], 6], "expected": [9, 5, 8, 1, 2, 3, 7]},
            {"description": "上浮不得修改原列表", "args": [[5, 3, 8], 2], "expected": [8, 3, 5], "immutable": True},
            {"description": "拒绝越界的下标", "args": [[1, 2], 2], "exception": "invalid_argument"},
            {"description": "拒绝负数下标", "args": [[1, 2], -1], "exception": "invalid_argument"},
            # ── heap_shift_down：size 限定堆的有效范围，堆排序依赖它 ──
            {"description": "根节点已最大无需下沉", "func": "heap_shift_down", "args": [[9, 5, 8], 0, 3], "expected": [9, 5, 8]},
            {"description": "与较大子节点交换", "func": "heap_shift_down", "args": [[1, 5, 8], 0, 3], "expected": [8, 5, 1]},
            {"description": "左子节点更大时选左边", "func": "heap_shift_down", "args": [[2, 9, 3], 0, 3], "expected": [9, 2, 3]},
            {"description": "连续下沉两层", "func": "heap_shift_down", "args": [[1, 9, 8, 7, 6, 5], 0, 6], "expected": [9, 7, 8, 1, 6, 5]},
            {"description": "size 之外的元素不参与", "func": "heap_shift_down", "args": [[1, 9, 8], 0, 2], "expected": [9, 1, 8]},
            {"description": "size 为 1 时无子节点", "func": "heap_shift_down", "args": [[1, 9, 8], 0, 1], "expected": [1, 9, 8]},
            {"description": "叶子节点无需下沉", "func": "heap_shift_down", "args": [[5, 1, 3], 1, 3], "expected": [5, 1, 3]},
            {"description": "下沉不得修改原列表", "func": "heap_shift_down", "args": [[1, 5, 8], 0, 3], "expected": [8, 5, 1], "immutable": True},
            {"description": "拒绝超过列表长度的 size", "func": "heap_shift_down", "args": [[1, 2], 0, 5], "exception": "invalid_argument"},
            {"description": "拒绝 size 为 0", "func": "heap_shift_down", "args": [[1, 2], 0, 0], "exception": "invalid_argument"},
            {"description": "拒绝超出 size 的下标", "func": "heap_shift_down", "args": [[1, 2], 2, 2], "exception": "invalid_argument"},
        ],
    },
    "2-4": {
        "target": "heap_sort",
        "targets": ["heap_sort"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "heap_sort": "std::vector<int> heap_sort(std::vector<int> items)",
            },
        },
        # items 是 std::vector<int>，Python 里的「非列表输入 / 非整数 / 布尔 / None 元素」
        # 都是编译期保证的，删除。
        "cases": [
            {"description": "空列表排序", "args": [[]], "expected": []},
            {"description": "单元素排序", "args": [[1]], "expected": [1]},
            {"description": "已有序列表保持有序", "args": [[1, 2, 3, 4]], "expected": [1, 2, 3, 4]},
            {"description": "逆序列表排序", "args": [[4, 3, 2, 1]], "expected": [1, 2, 3, 4]},
            {"description": "重复元素全部保留", "args": [[3, 1, 3, 2, 1]], "expected": [1, 1, 2, 3, 3]},
            {"description": "负数参与排序", "args": [[-3, 0, -1, 2]], "expected": [-3, -1, 0, 2]},
            {"description": "全部元素相同", "args": [[7, 7, 7]], "expected": [7, 7, 7]},
            {"description": "较长列表排序", "args": [[5, 3, 8, 1, 9, 2, 7, 4, 6, 0]], "expected": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]},
            {"description": "排序不得修改原列表", "args": [[5, 3, 8, 1]], "expected": [1, 3, 5, 8], "immutable": True},
        ],
    },

    # ══════════════════════════════════════════════════════════
    #  阶段三：图与并查集
    # ══════════════════════════════════════════════════════════
    "3-1": {
        "target": "build_adjacency",
        "targets": ["build_adjacency", "dfs_order"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "build_adjacency": "std::vector<std::vector<int>> build_adjacency(int node_count, std::vector<std::vector<int>> edges)",
                "dfs_order": "std::vector<int> dfs_order(std::vector<std::vector<int>> adjacency, int start)",
            },
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # 邻接表用 std::vector<std::vector<int>>，Python 里「端点不是整数 / 布尔 / 非列表」
        # 的类型错误在 C++ 里是编译期保证的，删除；保留自环、越界、边长度非法等业务校验。
        "cases": [
            {"description": "无边图返回空邻接表", "args": [3, []], "expected": [[], [], []]},
            {"description": "单个节点的图", "args": [1, []], "expected": [[]]},
            {"description": "一条无向边连接两个节点", "args": [2, [[0, 1]]], "expected": [[1], [0]]},
            {"description": "三角形图", "args": [3, [[0, 1], [1, 2], [0, 2]]], "expected": [[1, 2], [0, 2], [0, 1]]},
            {"description": "邻居按升序排列", "args": [3, [[0, 2], [0, 1]]], "expected": [[1, 2], [0], [0]]},
            {"description": "重复边只保留一次", "args": [2, [[0, 1], [1, 0]]], "expected": [[1], [0]]},
            {"description": "不修改传入的边列表", "args": [2, [[0, 1]]], "expected": [[1], [0]], "immutable": True},
            {"description": "拒绝自环", "args": [2, [[0, 0]]], "exception": "invalid_argument"},
            {"description": "拒绝越界的边端点", "args": [2, [[0, 2]]], "exception": "invalid_argument"},
            {"description": "拒绝负数端点", "args": [2, [[0, -1]]], "exception": "invalid_argument"},
            {"description": "拒绝长度不为 2 的边", "args": [2, [[0, 1, 2]]], "exception": "invalid_argument"},
            {"description": "拒绝非正数节点数", "args": [0, []], "exception": "invalid_argument"},
            # ── dfs_order：按邻接表的升序邻居做深度优先遍历 ──
            {"description": "链式图从起点走到底", "func": "dfs_order", "args": [[[1], [0, 2], [1]], 0], "expected": [0, 1, 2]},
            {"description": "分叉图先深入第一个邻居", "func": "dfs_order", "args": [[[1, 2], [0], [0]], 0], "expected": [0, 1, 2]},
            {"description": "只访问起点所在的连通分量", "func": "dfs_order", "args": [[[1], [0], [3], [2]], 0], "expected": [0, 1]},
            {"description": "换一个起点重新遍历", "func": "dfs_order", "args": [[[1], [0, 2], [1]], 1], "expected": [1, 0, 2]},
            {"description": "单节点图", "func": "dfs_order", "args": [[[]], 0], "expected": [0]},
            {"description": "环上不重复访问", "func": "dfs_order", "args": [[[1, 2], [0, 2], [0, 1]], 0], "expected": [0, 1, 2]},
            {"description": "遍历不得修改邻接表", "func": "dfs_order", "args": [[[1], [0, 2], [1]], 0], "expected": [0, 1, 2], "immutable": True},
            {"description": "拒绝越界的起点", "func": "dfs_order", "args": [[[1], [0]], 2], "exception": "invalid_argument"},
        ],
    },
    "3-2": {
        "target": "uf_find_root",
        "targets": ["uf_find_root", "uf_compress", "count_components"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "uf_find_root": "int uf_find_root(std::vector<int> parent, int x)",
                "uf_compress": "std::vector<int> uf_compress(std::vector<int> parent, int x)",
                "count_components": "int count_components(int node_count, std::vector<std::vector<int>> edges)",
            },
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # parent[i] == i 表示 i 是根；否则 parent[i] 是 i 的父节点。Python 里的
        # 浮点/布尔节点、非列表 parent、非整数元素这些类型错误在 C++ 里是编译期保证的，删除。
        "cases": [
            {"description": "单节点自己就是根", "args": [[0], 0], "expected": 0},
            {"description": "顺着父指针找到根", "args": [[1, 2, 2], 0], "expected": 2},
            {"description": "根节点直接返回自己", "args": [[1, 2, 2], 2], "expected": 2},
            {"description": "三层深的链找到根", "args": [[1, 2, 3, 3], 0], "expected": 3},
            {"description": "查找不得修改 parent 数组", "args": [[1, 2, 2], 0], "expected": 2, "immutable": True},
            {"description": "拒绝越界的节点", "args": [[0], 1], "exception": "invalid_argument"},
            {"description": "拒绝负数节点", "args": [[0], -1], "exception": "invalid_argument"},
            # ── uf_compress：路径压缩返回新的 parent 数组 ──
            {"description": "把两层链压平成一层", "func": "uf_compress", "args": [[1, 2, 2], 0], "expected": [2, 2, 2]},
            {"description": "整条链都直接指向根", "func": "uf_compress", "args": [[1, 2, 3, 3], 0], "expected": [3, 3, 3, 3]},
            {"description": "已是根则数组不变", "func": "uf_compress", "args": [[1, 2, 2], 2], "expected": [1, 2, 2]},
            {"description": "只压缩该节点所在的路径", "func": "uf_compress", "args": [[1, 2, 3, 3], 3], "expected": [1, 2, 3, 3]},
            {"description": "压缩不得修改原数组", "func": "uf_compress", "args": [[1, 2, 2], 0], "expected": [2, 2, 2], "immutable": True},
            {"description": "压缩拒绝越界节点", "func": "uf_compress", "args": [[1, 2, 2], 5], "exception": "invalid_argument"},
            # ── count_components：用并查集统计无向图的连通分量 ──
            {"description": "无边图每个节点独立成分量", "func": "count_components", "args": [3, []], "expected": 3},
            {"description": "一条边把两个节点并成一份", "func": "count_components", "args": [2, [[0, 1]]], "expected": 1},
            {"description": "三角形只有一个连通分量", "func": "count_components", "args": [3, [[0, 1], [1, 2], [0, 2]]], "expected": 1},
            {"description": "两组独立的分量", "func": "count_components", "args": [4, [[0, 1], [2, 3]]], "expected": 2},
            {"description": "孤立节点也算一个分量", "func": "count_components", "args": [5, [[0, 1], [3, 4]]], "expected": 3},
            {"description": "单节点图", "func": "count_components", "args": [1, []], "expected": 1},
            {"description": "重复边不影响分量数", "func": "count_components", "args": [3, [[0, 1], [1, 0], [0, 1]]], "expected": 2},
            {"description": "统计不得修改边列表", "func": "count_components", "args": [4, [[0, 1], [2, 3]]], "expected": 2, "immutable": True},
            {"description": "统计拒绝越界的边", "func": "count_components", "args": [2, [[0, 5]]], "exception": "invalid_argument"},
            {"description": "统计拒绝非正数节点数", "func": "count_components", "args": [0, []], "exception": "invalid_argument"},
            {"description": "统计拒绝自环", "func": "count_components", "args": [2, [[1, 1]]], "exception": "invalid_argument"},
        ],
    },
    "3-3": {
        "target": "bfs_shortest_path",
        "targets": ["bfs_shortest_path"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "bfs_shortest_path": "std::vector<int> bfs_shortest_path(std::vector<std::vector<int>> edges, int node_count, int start, int end)",
            },
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # 「不可达返回 None」在 C++ 里改为返回空容器 {}（start==end 返回 [start] 非空，
        # 所以空容器语义无歧义）。Python 里的非整数终点等类型错误是编译期保证的，删除。
        "cases": [
            {"description": "直接相连的两个节点", "args": [[[0, 1]], 2, 0, 1], "expected": [0, 1]},
            {"description": "两跳可达", "args": [[[0, 1], [1, 2]], 3, 0, 2], "expected": [0, 1, 2]},
            {"description": "起点即终点", "args": [[[0, 1]], 2, 0, 0], "expected": [0]},
            {"description": "不可达返回空容器", "args": [[[0, 1]], 3, 0, 2], "expected": []},
            {"description": "多条路径取最短的那条", "args": [[[0, 1], [1, 3], [0, 2], [2, 3]], 4, 0, 3], "expected": [0, 1, 3]},
            {"description": "直达优于绕远", "args": [[[0, 1], [0, 2], [1, 2]], 3, 0, 2], "expected": [0, 2]},
            {"description": "链式图逐跳前进", "args": [[[0, 1], [1, 2], [2, 3]], 4, 0, 3], "expected": [0, 1, 2, 3]},
            {"description": "起点是孤立节点", "args": [[[1, 2]], 3, 0, 2], "expected": []},
            {"description": "只有两个节点但不相连", "args": [[], 2, 0, 1], "expected": []},
            {"description": "搜索不得修改边列表", "args": [[[0, 1], [1, 2]], 3, 0, 2], "expected": [0, 1, 2], "immutable": True},
            {"description": "拒绝越界的起点", "args": [[[0, 1]], 2, 0, 5], "exception": "invalid_argument"},
            {"description": "拒绝越界的终点", "args": [[[0, 1]], 2, 3, 1], "exception": "invalid_argument"},
            {"description": "拒绝非正数节点数", "args": [[[0, 1]], 0, 0, 1], "exception": "invalid_argument"},
            {"description": "拒绝自环边", "args": [[[0, 0]], 2, 0, 1], "exception": "invalid_argument"},
        ],
    },

    # ══════════════════════════════════════════════════════════
    #  阶段四：算法工具箱工程化
    # ══════════════════════════════════════════════════════════
    "4-1": {
        "target": "toolbox_call",
        "targets": ["describe_toolbox", "toolbox_call"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "describe_toolbox": "std::vector<std::string> describe_toolbox()",
                "toolbox_call": "std::vector<int> toolbox_call(std::string name, std::vector<int> data)",
            },
            "includes": ["<stdexcept>", "<string>", "<functional>", "<map>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # 重设计（Python 的动态分发在 C++ 里换成同构签名）：工具箱里登记三个
        # std::vector<int> → std::vector<int> 的操作：sort（升序排序）、reverse（反转）、
        # dedup（去重，保留首次出现）。注册表用 std::map<std::string, std::function<...>>
        # 在函数内部构造，未知操作名抛 std::invalid_argument。
        "cases": [
            {"description": "工具箱清单按名称升序", "func": "describe_toolbox", "args": [], "expected": ["dedup", "reverse", "sort"]},
            {"description": "通过工具箱排序", "args": ["sort", [3, 1, 2]], "expected": [1, 2, 3]},
            {"description": "通过工具箱反转", "args": ["reverse", [1, 2, 3]], "expected": [3, 2, 1]},
            {"description": "通过工具箱去重", "args": ["dedup", [1, 2, 2, 3, 1]], "expected": [1, 2, 3]},
            {"description": "空容器排序", "args": ["sort", []], "expected": []},
            {"description": "工具箱不得修改输入", "args": ["reverse", [1, 2, 3]], "expected": [3, 2, 1], "immutable": True},
            {"description": "拒绝未登记的操作名", "args": ["missing", [1]], "exception": "invalid_argument"},
        ],
    },
    "4-2": {
        "target": "merge_sort",
        "targets": ["merge_sort", "merge_sorted", "is_sorted_ascending"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "merge_sort": "std::vector<int> merge_sort(std::vector<int> items)",
                "merge_sorted": "std::vector<int> merge_sorted(std::vector<int> left, std::vector<int> right)",
                "is_sorted_ascending": "bool is_sorted_ascending(std::vector<int> items)",
            },
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # Python 里的「非列表输入 / 非整数 / 布尔元素」类型错误在 C++ 里是编译期保证的，删除；
        # 保留「merge_sorted 输入必须各自有序」这条业务校验。
        "cases": [
            {"description": "空列表归并排序", "args": [[]], "expected": []},
            {"description": "单元素归并排序", "args": [[1]], "expected": [1]},
            {"description": "已有序列表保持不变", "args": [[1, 2, 3]], "expected": [1, 2, 3]},
            {"description": "逆序列表完成排序", "args": [[3, 2, 1]], "expected": [1, 2, 3]},
            {"description": "重复元素全部保留", "args": [[2, 1, 2, 1]], "expected": [1, 1, 2, 2]},
            {"description": "负数参与排序", "args": [[-3, 0, -1, 2]], "expected": [-3, -1, 0, 2]},
            {"description": "较长列表排序", "args": [[5, 3, 8, 1, 9, 2, 7, 4, 6, 0]], "expected": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]},
            {"description": "排序不得修改原列表", "args": [[5, 3, 8, 1]], "expected": [1, 3, 5, 8], "immutable": True},
            # ── merge_sorted：归并两个各自有序的列表 ──
            {"description": "归并两个空列表", "func": "merge_sorted", "args": [[], []], "expected": []},
            {"description": "一侧为空", "func": "merge_sorted", "args": [[], [1, 2]], "expected": [1, 2]},
            {"description": "交错归并", "func": "merge_sorted", "args": [[1, 3], [2, 4]], "expected": [1, 2, 3, 4]},
            {"description": "重复值全部保留", "func": "merge_sorted", "args": [[1, 2], [2, 3]], "expected": [1, 2, 2, 3]},
            {"description": "整体拼接的情形", "func": "merge_sorted", "args": [[1, 2], [3, 4]], "expected": [1, 2, 3, 4]},
            {"description": "归并不得修改原列表", "func": "merge_sorted", "args": [[1, 3], [2, 4]], "expected": [1, 2, 3, 4], "immutable": True},
            {"description": "拒绝未排序的输入", "func": "merge_sorted", "args": [[3, 1], [2]], "exception": "invalid_argument"},
            # ── is_sorted_ascending：复杂度验证要用到的判定工具 ──
            {"description": "空列表视为有序", "func": "is_sorted_ascending", "args": [[]], "expected": True},
            {"description": "单元素视为有序", "func": "is_sorted_ascending", "args": [[1]], "expected": True},
            {"description": "非降序即有序", "func": "is_sorted_ascending", "args": [[1, 2, 2, 3]], "expected": True},
            {"description": "全部相同视为有序", "func": "is_sorted_ascending", "args": [[1, 1]], "expected": True},
            {"description": "逆序判定为无序", "func": "is_sorted_ascending", "args": [[3, 1]], "expected": False},
            {"description": "中间乱序判定为无序", "func": "is_sorted_ascending", "args": [[1, 3, 2]], "expected": False},
        ],
    },
    "4-3": {
        "target": "lru_simulate",
        "targets": ["lru_simulate", "two_sum"],
        "language": "cpp",
        "cpp": {
            "signatures": {
                "lru_simulate": "std::vector<int> lru_simulate(int capacity, std::vector<std::vector<int>> operations)",
                "two_sum": "std::vector<int> two_sum(std::vector<int> nums, int target)",
            },
            "includes": ["<stdexcept>"],
            "exception_map": {"invalid_argument": "std::invalid_argument"},
        },
        # 重设计（Python 的混合类型操作序列换成定长整数编码）：operations 是
        # std::vector<std::vector<int>>，[0, k] 表示 get(k)，[1, k, v] 表示 put(k, v)。
        # 返回值是所有 get 的结果，命中返回对应值，未命中返回 -1。
        "cases": [
            {"description": "写入后立即命中", "args": [1, [[1, 1, 1], [0, 1]]], "expected": [1]},
            {"description": "读取不存在的键返回 -1", "args": [2, [[0, 1]]], "expected": [-1]},
            {"description": "容量满时淘汰最久未使用的键", "args": [2, [[1, 1, 1], [1, 2, 2], [0, 1], [1, 3, 3], [0, 2]]], "expected": [1, -1]},
            {"description": "更新已有键会刷新其新鲜度", "args": [2, [[1, 1, 1], [1, 2, 2], [1, 1, 10], [1, 3, 3], [0, 2], [0, 1]]], "expected": [-1, 10]},
            {"description": "重复读取同一键都命中", "args": [2, [[1, 1, 1], [0, 1], [0, 1]]], "expected": [1, 1]},
            {"description": "容量为 1 时只保留最新键", "args": [1, [[1, 1, 1], [1, 2, 2], [0, 1], [0, 2]]], "expected": [-1, 2]},
            {"description": "没有任何操作时返回空列表", "args": [2, []], "expected": []},
            {"description": "只有写入没有读取", "args": [2, [[1, 1, 1]]], "expected": []},
            {"description": "拒绝容量为 0", "args": [0, []], "exception": "invalid_argument"},
            {"description": "拒绝负容量", "args": [-1, []], "exception": "invalid_argument"},
            {"description": "拒绝未知操作码", "args": [2, [[2, 1]]], "exception": "invalid_argument"},
            {"description": "拒绝缺少键的读取操作", "args": [2, [[0]]], "exception": "invalid_argument"},
            {"description": "拒绝缺少值的写入操作", "args": [2, [[1, 1]]], "exception": "invalid_argument"},
            # ── two_sum：哈希表让查找从 O(n^2) 降到 O(n) ──
            {"description": "经典两数之和", "func": "two_sum", "args": [[2, 7, 11, 15], 9], "expected": [0, 1]},
            {"description": "答案在后面两个元素", "func": "two_sum", "args": [[3, 2, 4], 6], "expected": [1, 2]},
            {"description": "相同的两个数", "func": "two_sum", "args": [[3, 3], 6], "expected": [0, 1]},
            {"description": "无解返回空列表", "func": "two_sum", "args": [[1, 2, 3], 100], "expected": []},
            {"description": "空数组无解", "func": "two_sum", "args": [[], 0], "expected": []},
            {"description": "负数参与求和", "func": "two_sum", "args": [[-3, 4, 3, 90], 0], "expected": [0, 2]},
            {"description": "多个零取下标最小的一对", "func": "two_sum", "args": [[0, 4, 3, 0], 0], "expected": [0, 3]},
            {"description": "查找不得修改原数组", "func": "two_sum", "args": [[2, 7, 11, 15], 9], "expected": [0, 1], "immutable": True},
        ],
    },
}

FLAGSHIP_IDS = set(SPECS)


# ── 语言派生 ────────────────────────────────────────────────
# 工作区的文件名、阶段检查的措辞、给 AI 导师的提示词全部从这里取，避免
# 「solution.py」这个字符串散落在 service 各处后改不干净。
_LANGUAGE_FILES = {
    "python": ("solution.py", "repair_target.py", "Python"),
    "cpp": ("solution.cpp", "repair_target.cpp", "C++"),
}
_DEFAULT_LANGUAGE_FILES = _LANGUAGE_FILES["python"]


def lab_language(exercise_id: str) -> str:
    """本关的实现语言，缺省 python。"""
    spec = SPECS.get(str(exercise_id)) or {}
    return str(spec.get("language") or "python")


def _language_files(exercise_id: str) -> tuple[str, str, str]:
    return _LANGUAGE_FILES.get(lab_language(exercise_id), _DEFAULT_LANGUAGE_FILES)


def lab_solution_file(exercise_id: str) -> str:
    """本关学生要实现的那个文件。"""
    return _language_files(exercise_id)[0]


def lab_repair_file(exercise_id: str) -> str:
    """故障修复阶段生成的独立文件。"""
    return _language_files(exercise_id)[1]


def lab_language_label(exercise_id: str) -> str:
    return _language_files(exercise_id)[2]
