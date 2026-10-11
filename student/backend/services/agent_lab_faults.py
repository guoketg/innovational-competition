"""Exercise-aware fault injection for the flagship programming labs.

Each curated mutation breaks exactly one concept the lab is teaching (an
off-by-one on an insert boundary, a reversed comparison in a BST, a heap that
stops being a max-heap, a path-compression that stops returning a copy, and so
on).  The public prompt describes the observable symptom; the private profile
stays in the capability session so the explanation scorer can check whether the
learner found the actual mechanism.

The curated candidates are best-effort: they only fire when the learner's
implementation matches a recognisable shape.  ``capability_service`` falls back
to generic and AST-driven mutations when none of them hit, so a miss here costs
nothing but precision.
"""

from __future__ import annotations

import re
from typing import Any


FAULT_PROFILES: dict[str, dict[str, Any]] = {
    "1-1": {
        "focus": "顺序表插入的下标边界与值语义",
        "root_cause": (
            "插入位置的边界判断被收紧成 index >= static_cast<int>(items.size())，"
            "导致「追加到末尾」这个合法调用被误判为越界。"
        ),
        "root_terms": ["array_insert", "index", "size", "out_of_range", "越界", "末尾"],
    },
    "1-2": {
        "focus": "单链表反转时的指针掉头与不可变性",
        "root_cause": "新节点的 next 仍然指向原链表的下一个节点，指针没有真正掉头，遍历结果和原链表一样。",
        "root_terms": ["next", "指针", "掉头", "反转", "prev", "不可变", "原链表"],
    },
    "1-3": {
        "focus": "栈求值的左右操作数顺序与除法截断方向",
        "root_cause": "两个操作数的弹出顺序被调换，减法和除法拿到了颠倒的左右操作数；或除法错误地实现成向下取整，负数结果不再向零截断。",
        "root_terms": ["pop_back", "左操作数", "右操作数", "顺序", "截断", "向零", "向下取整", "负数"],
    },
    "2-1": {
        "focus": "二分搜索树「左小右大」不变式与重复值拒绝",
        "root_cause": "插入时的比较方向被写反（或重复值不再报错），新节点挂到了错误的一侧，树不再满足 BST 性质。",
        "root_terms": ["BST", "左小右大", "不变式", "比较方向", "重复值", "中序", "插入"],
    },
    "2-2": {
        "focus": "中序遍历的访问次序与层序遍历的分层收集",
        "root_cause": "中序把根节点的访问提前到了左子树之前，退化成前序；或层序收集到的是节点对象而不是节点值。",
        "root_terms": ["中序", "前序", "访问次序", "左子树", "层序", "分层", "节点值"],
    },
    "2-3": {
        "focus": "堆的父子下标映射、大顶堆方向与 size 边界",
        "root_cause": "父节点下标算成 index / 2，或下沉时改挑较小的子节点，堆从大顶堆变成了小顶堆。",
        "root_terms": ["父节点", "下标", "(index - 1) / 2", "子节点", "大顶堆", "小顶堆", "size"],
    },
    "2-4": {
        "focus": "建堆的遍历方向与有序区间的收缩",
        "root_cause": "建堆时从叶子往根的方向被写反，或交换堆顶后没有把堆的有效长度减一，末尾元素又被卷回堆里。",
        "root_terms": ["建堆", "n / 2 - 1", "自底向上", "缩小", "有效长度", "堆顶", "末尾"],
    },
    "3-1": {
        "focus": "无向图邻接表的双向登记与 DFS 的访问顺序",
        "root_cause": "反向边只登记了一次，邻接表变成了有向图；或入栈前没有按逆序压入，深度优先的访问顺序不再唯一。",
        "root_terms": ["邻接表", "双向", "有向", "反向边", "入栈顺序", "逆序", "DFS", "访问顺序"],
    },
    "3-2": {
        "focus": "并查集的根判定、路径压缩的不可变语义与分量计数",
        "root_cause": "路径压缩直接改写了传入的 parent 数组；或统计分量时数的是节点而不是不同的根。",
        "root_terms": ["parent", "根", "路径压缩", "不可变", "新列表", "连通分量", "根的数量"],
    },
    "3-3": {
        "focus": "BFS 的最短性前提与回溯路径的方向",
        "root_cause": "节点出队后才标记已访问，同一节点被重复入队并覆盖了前驱；或回溯出的路径没有反转，返回了逆序路径。",
        "root_terms": ["BFS", "入队即标记", "前驱", "覆盖", "回溯", "反转", "最短路径", "逆序"],
    },
    "4-1": {
        "focus": "工具箱注册表的分发契约与异常处理",
        "root_cause": "分发时直接返回了输入导致操作没生效，或 sort 操作没有真正排序。",
        "root_terms": ["注册表", "registry", "分发", "排序", "升序", "未登记", "std::invalid_argument"],
    },
    "4-2": {
        "focus": "归并的双指针取舍与有序性判定方向",
        "root_cause": "合并时从错误的序列取值，或 is_sorted_ascending 的比较方向写反，把降序当成升序。",
        "root_terms": ["归并", "双指针", "left", "right", "比较", "is_sorted_ascending", "降序", "升序"],
    },
    "4-3": {
        "focus": "LRU 的新鲜度刷新与最久未使用淘汰",
        "root_cause": "get 命中后没有把该键移到最新，或淘汰时删掉的是最新的那一项，LRU 退化成 FIFO 甚至反 LRU。",
        "root_terms": ["LRU", "新鲜度", "刷新", "移到最新", "淘汰", "最久未使用", "FIFO", "顺序"],
    },
}


def _replace(code: str, pattern: str, replacement: str, *, flags: int = 0) -> str | None:
    updated, count = re.subn(pattern, replacement, code, count=1, flags=flags)
    return updated if count else None


def curated_mutation_candidates(exercise_id: str, code: str) -> list[tuple[str, dict[str, Any]]]:
    """Return deterministic, concept-aligned mutation candidates for one lab."""
    profile = FAULT_PROFILES.get(exercise_id)
    if not profile:
        return []

    candidates: list[str | None] = []
    if exercise_id == "1-1":
        # 边界收紧：合法的「追加到末尾」被当成越界。
        # 只匹配 "index >" 这一段、不把右边写进正则——学生可能写成
        # static_cast<int>(items.size()) / (int)items.size() / items.size()，
        # 把 RHS 一起写死就会漏掉其中那几种写法。
        #
        # ⚠️ (?!=) 这个否定断言是必须的，别省：合法写法里 `index >= 0` 很常见，
        # 而 `index\s*>\s*` 会匹配到 `index >=` 里的那个 `>`，把 `index >= 0`
        # 变成 `index >= = 0` —— 一份**编译不过的残骸**。更糟的是 _build_mutation
        # 只检查「判题是否不通过」，编译错误同样导致 passed=False，所以这份残骸
        # 会被当成一个「有效故障」收下，学生看到的是语法垃圾而不是逻辑 bug。
        candidates.append(_replace(code, r"index\s*>(?!=)\s*", "index >= "))
        # 位置偏移：无论要插到哪个位置都插到最前面，中间/末尾插入全错（仍然编译得过）。
        # 同样只匹配 ".begin() + index" 这一段，容器变量名叫什么都不影响。
        candidates.append(_replace(code, r"\.begin\(\)\s*\+\s*index", ".begin()"))
        # 异常类型替换：越界仍然被拦住，但抛的不是题目要求的 std::out_of_range，
        # 两条边界用例会失败。
        # 注意**不要**把这条说成「必然命中」：学生完全可能写 `using namespace std;`
        # 之后直接 `throw out_of_range(...)`，这样正则里的 `std::` 就匹配不上。
        # 控制器实测过一份这样的解（three 条候选全部落空）——见 Step 3 下面的说明。
        candidates.append(_replace(code, r"std::out_of_range", "std::runtime_error"))
    elif exercise_id == "1-2":
        # 指针没有掉头：新节点的 next 仍指向原链表的下一个节点。
        candidates.append(_replace(code, r"new\s+Node\s*\{\s*node->value\s*,\s*prev\s*\}", "new Node{node->value, node->next}"))
        # 返回了原链表而不是反转后的新链表。
        candidates.append(_replace(code, r"return\s+prev\b", "return head"))
    elif exercise_id == "1-3":
        # 左右操作数顺序颠倒：先弹的记成了 left、后弹的记成了 right。
        candidates.append(_replace(
            code,
            r"int\s+right\s*=\s*stack\.back\(\);\s*stack\.pop_back\(\);(\s*\n\s*)int\s+left\s*=\s*stack\.back\(\);\s*stack\.pop_back\(\);",
            r"int left = stack.back(); stack.pop_back();\1int right = stack.back(); stack.pop_back();",
        ))
        # 除零检查被短路：除数为 0 时不再抛异常。
        candidates.append(_replace(code, r"if\s*\(\s*right\s*==\s*0\s*\)", "if (false)"))
    elif exercise_id == "2-1":
        # 比较方向写反：新节点挂到错误的一侧。
        candidates.append(_replace(code, r"value\s*<\s*root->value", "value > root->value"))
        # 重复值不再拒绝。
        candidates.append(_replace(code, r"if\s*\(\s*value\s*==\s*root->value\s*\)", "if (false)"))
    elif exercise_id == "2-2":
        # 中序访问次序写反：先右后左，退化成降序。
        candidates.append(_replace(code, r"inorder_walk\(node->left, result\);", "inorder_walk(node->right, result);"))
        # 层序把右孩子当左孩子推进：左子树节点被漏掉。
        candidates.append(_replace(code, r"if\s*\(node->left\)\s*next\.push_back\(node->left\);", "if (node->right) next.push_back(node->right);"))
    elif exercise_id == "2-3":
        # 父节点下标公式写错。
        candidates.append(_replace(code, r"int parent = \(index - 1\) / 2;", "int parent = index / 2;"))
        # 下沉时改挑较小的子节点：大顶堆变成小顶堆。
        candidates.append(_replace(code, r"heap\[left\] > heap\[largest\]", "heap[left] < heap[largest]"))
    elif exercise_id == "2-4":
        # 建堆方向写反：从根往叶子逐个下沉。
        candidates.append(_replace(
            code,
            r"for \(int start = total / 2 - 1; start >= 0; --start\)",
            "for (int start = 0; start < total; ++start)",
        ))
        # 交换堆顶后没有缩小堆的范围。
        candidates.append(_replace(code, r"sift_down\(result, 0, end\);", "sift_down(result, 0, total);"))
    elif exercise_id == "3-1":
        # 反向边只登记一次：无向图退化成有向图。
        candidates.append(_replace(code, r"adjacency\[right\]\.push_back\(left\);", "(void)0;"))
        # 邻居列表不再排序：访问顺序不再唯一。
        candidates.append(_replace(code, r"std::sort\(neighbors\.begin\(\), neighbors\.end\(\)\);", "(void)0;"))
    elif exercise_id == "3-2":
        # 爬根只走一步：没有爬到真正的根。
        candidates.append(_replace(code, r"while \(parent\[x\] != x\) x = parent\[x\];", "x = parent[x];"))
        # 合并时没有真正挂接：分量永远不合并。
        candidates.append(_replace(code, r"parent\[root_right\] = root_left;", "parent[root_right] = root_right;"))
    elif exercise_id == "3-3":
        # 回溯出的路径没有反转。
        candidates.append(_replace(code, r"std::reverse\(path\.begin\(\), path\.end\(\)\);", "(void)0;"))
        # 前驱记录错了：所有节点都指回起点。
        candidates.append(_replace(code, r"previous\[neighbor\] = node;", "previous[neighbor] = start;"))
    elif exercise_id == "4-1":
        # 分发时直接返回了输入，操作没有生效。
        candidates.append(_replace(code, r"return it->second\(data\);", "return data;"))
        # sort 操作不再排序。
        candidates.append(_replace(code, r"std::sort\(result\.begin\(\), result\.end\(\)\);", "(void)0;"))
    elif exercise_id == "4-2":
        # 双指针从错误的序列取值。
        candidates.append(_replace(code, r"merged\.push_back\(left\[i\+\+\]\);", "merged.push_back(right[j++]);"))
        # 有序性判定方向写反：降序被当成升序。
        candidates.append(_replace(code, r"if \(items\[i\] < items\[i - 1\]\) return false;", "if (items[i] < items[i - 1]) return true;"))
    elif exercise_id == "4-3":
        # 未命中返回了 0 而不是 -1。
        candidates.append(_replace(code, r"results\.push_back\(-1\);", "results.push_back(0);"))
        # 淘汰的是最新的一项而不是最久未使用的一项。
        candidates.append(_replace(code, r"int oldest = order\.front\(\);", "int oldest = order.back();"))

    return [(candidate, dict(profile)) for candidate in candidates if candidate and candidate != code]
