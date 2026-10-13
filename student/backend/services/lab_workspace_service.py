"""Persistent workspaces for the guided data-structure labs.

每关是一个只含 ``solution.py`` 的单文件项目，形态对齐 PTA（拼题A）：读题 →
写实现 → 用【自测】跑公开样例 → 提交评测。没有终端、没有虚拟环境、没有依赖
声明——13 个关卡全部只用 Python 标准库。工作区文件与阶段进度在请求之间持久化。
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePosixPath

from config import BASE_DIR
from services.secret_store import decrypt_config
from services.agent_lab_specs import (
    SPECS, lab_language, lab_language_label, lab_repair_file, lab_solution_file,
)
from services.ai_service import redact_secrets
from services.judge_service import (
    feedback_guidance as _feedback_guidance,
    get_flagship_exercise,
    is_flagship_exercise,
    judge_samples,
    judge_submission,
    public_sample_views,
)


WORKSPACE_ROOT = Path(BASE_DIR) / "data" / "lab_workspaces"
MAX_FILE_SIZE = 300_000
# .venv 只用于隐藏历史工作区里遗留的虚拟环境目录，新关卡不再创建。
SKIP_PARTS = {".venv", "__pycache__", ".git", ".pytest_cache", ".cache"}
TUTOR_HISTORY_LIMIT = 12
logger = logging.getLogger(__name__)

# #29 行为通道护栏：AI 直改学生工作区（写文件/建目录）被拦时，回灌给模型的拒绝说明。
# 与内容通道（文本护栏）共用同一释放阀，杜绝"绕过文本护栏、直接调工具把答案写进代码"。
_TOOL_GUARD_DENY_MESSAGE = (
    "【防泄题护栏·工具拦截】本次调用被拒绝：当前未达到直接改写学生工作区的条件。"
    "请不要直接写入/覆盖学生的代码，改为用提问和提示引导他从下一步该做什么开始思考。"
    "当学生自己贴出尝试代码、或已多轮尝试、或该关掌握度达标后，系统才会放行直接改写。"
)
TRACK_CONFIG = {
    "1": {
        # 四个阶段都是数据结构与算法：只用标准库，因此 packages / imports 都为空。
        # 这两个字段为空会连带关闭「框架接入」「项目 API Key」「运行时真实调用」等
        # 只对模型调用类实验有意义的检查（见 check_stage 与 _run_integration_runtime_test）。
        "framework": "Python 标准库",
        "packages": [],
        "imports": [],
    },
    "2": {
        "framework": "Python 标准库",
        "packages": [],
        "imports": [],
    },
    "3": {
        "framework": "Python 标准库",
        "packages": [],
        "imports": [],
    },
    "4": {
        "framework": "Python 标准库",
        "packages": [],
        "imports": [],
    },
}

TRACK_PREREQUISITES = {
    "1": ["Python 列表与字典", "函数与异常处理", "循环与条件分支"],
    "2": ["递归", "列表嵌套结构", "不可变数据"],
    "3": ["集合与字典", "队列与栈", "二维列表"],
    "4": ["模块与导入", "排序与查找", "复杂度初步"],
}

# 13 关全部是数据结构与算法练习：只用 Python 标准库，零第三方依赖、零框架接入。
# 「建虚拟环境 / 声明依赖 / 把函数接回可运行应用」这三步对它们都是空转，因此所有
# 阶段统一不开设——阶段四（工具箱 / 基准 / LRU）的重点是把散装函数整理成可复用的
# 模块，用 solution.py 里的组织方式加判题即可验证，不需要 .venv 与 requirements.txt。
# 移除后无需额外补偿：acceptance 的「前置阶段」按 course["stages"][:-1] 遍历，
# completed_stages 也始终按 course["stages"] 重建（见 check_stage 末尾），
# 旧状态里残留的 environment / dependencies / integration 会自动被剔除。


def _stage_hints(stage_id: str, exercise: dict, targets: list[str], track: dict,
                 solution_file: str = "solution.py", language: str = "python") -> list[dict]:
    """Build a small, progressive hint ladder without exposing the full answer."""
    target_label = "、".join(targets) or "核心函数"
    steps = [str(item).strip() for item in exercise.get("steps", []) if str(item).strip()]
    acceptance = [str(item).strip() for item in exercise.get("acceptance", []) if str(item).strip()]
    if stage_id == "structure":
        texts = [
            f"本关只有一个文件 {solution_file}——不需要虚拟环境，也不需要 requirements.txt。",
            f"打开 {solution_file}，先看清目标函数的签名、参数顺序和返回值契约，这些不能改动。",
            f"如果找不到文件，确认项目根目录下 {solution_file} 存在且大小写完全一致。",
        ]
    elif stage_id == "doc_intro":
        texts = [
            "先明确三件事：这一步要实现什么函数？输入输出是什么？验收标准有哪些？",
            "打开「项目文档」（面板标题栏 📚 图标）或本卡片里的「查看文档讲解」，通读配套教程的前两节。",
            "文档里带「插入编辑器」按钮的示例代码可以先点进去看，但先理解结构再动手写自己的版本。",
        ]
    elif stage_id == "first_llm_call":
        texts = [
            f"先别管函数签名，用最朴素的方式把这件事在 {solution_file} 里做一遍，怎么方便怎么来。",
            "写完点【自测】跑一次样例，看清每一步发生了什么，再回头看下面的现象描述对不对得上。",
            "这一步只求看懂现象，不必写成最终形态；正式实现留到下一阶段。",
            (
                "自测没有任何输出时，先确认目标函数已经 return，而不是仍然 throw 占位异常。"
                if language == "cpp"
                else "自测没有任何输出时，先确认目标函数已经 return，而不是仍然 raise NotImplementedError。"
            ),
        ]
    elif stage_id == "implementation":
        ordered = " → ".join(steps) if steps else f"先完成 {target_label} 的正常路径，再补输入边界"
        done_when = "；".join(acceptance) if acceptance else "正常路径、边界输入和不可变性都满足题目契约"
        texts = [
            f"把上一阶段热身的写法改写成 {target_label} 函数：写死的输入换成参数，"
            + ("观察用的 std::cout 换成 return。" if language == "cpp" else "观察用的 print 换成 return。"),
            f"建议按最小步骤推进：{ordered}。每完成一步就用一个最小输入手动验证。",
            f"用验收标准反查遗漏：{done_when}。",
            "如果仍然卡住，可以插入函数骨架；只补当前失败分支，不要同时重写整个函数。",
        ]
    else:
        texts = [
            "验收失败时先看第一个未通过阶段，不要同时修改多个文件。",
            "先修复公开阶段检查，再运行私有业务场景；私有测试用于确认你没有只适配示例。",
            "全部通过后，请准备解释关键设计选择，而不只是复述代码执行过程。",
        ]
    return [
        {"level": index, "title": ["思考问题", "方向提示", "检查清单", "骨架提示"][min(index - 1, 3)], "content": text}
        for index, text in enumerate(texts, 1)
    ]


def _failure_hint_text(outcome: dict) -> str:
    """把最近一次判题结果压成一句「针对你上次报错」的提示（#28）。

    静态提示阶梯按 stage 写死，与学生的具体报错无关；这里用真实失败用例补一条
    最深一级提示。全部通过或数据缺失时返回空串，调用方据此决定是否追加。
    """
    if not isinstance(outcome, dict):
        return ""
    if outcome.get("compile_error"):
        return f"上次代码无法运行：{str(outcome['compile_error'])[:160]}。先修掉这个编译/语法错误，再看业务逻辑。"
    failed = [c for c in (outcome.get("cases") or []) if not c.get("passed")]
    if not failed:
        return ""
    first = failed[0]
    parts = [f"上次「{first.get('description', '')}」未通过"]
    if first.get("input"):
        parts.append(f"输入 {first['input']}")
    if first.get("expected") not in (None, ""):
        parts.append(f"期望 {first['expected']}")
    if first.get("actual") not in (None, ""):
        parts.append(f"实际 {first['actual']}")
    detail = str(first.get("detail") or "").strip()
    if detail:
        parts.append(f"报错 {detail[:120]}")
    return "，".join(parts) + "。先拿这组数据手动跑一遍，定位差在哪一步。"


def _safe_part(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]", "-", str(value or ""))
    if not value:
        raise ValueError("工作区标识不能为空")
    return value[:80]


def _root(user_id: int, exercise_id: str) -> Path:
    if exercise_id not in SPECS:
        raise ValueError("未找到该实验项目")
    path = WORKSPACE_ROOT / f"user-{int(user_id)}" / _safe_part(exercise_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_path(root: Path, relative_path: str, *, allow_hidden: bool = True) -> Path:
    raw = str(relative_path or "").replace("\\", "/").strip("/")
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or ".." in pure.parts:
        raise ValueError("文件路径不合法")
    if len(pure.parts) > 64 or any(len(part) > 255 for part in pure.parts):
        raise ValueError("文件路径过深或名称过长")
    if not allow_hidden and any(part.startswith(".") for part in pure.parts):
        raise ValueError("该隐藏目录不可操作")
    resolved = (root / Path(*pure.parts)).resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("文件必须位于当前项目内")
    return resolved


def _localize_text(text: str, solution_file: str, language_label: str) -> str:
    """把阶段模板里的 Python 措辞换成当前关卡语言的措辞（幂等）。"""
    if solution_file != "solution.py":
        text = text.replace("solution.py", solution_file)
    if language_label != "Python":
        text = text.replace("Python 标准库", f"{language_label} 标准库")
    return text


def _course_solution_file(course: dict) -> str:
    """课程对象里的实现文件名。所有读写 solution.* 的地方都从这里取。"""
    return str(course.get("solution_file") or "solution.py")


def _language_label_of(course: dict) -> str:
    """课程对象里的语言显示名。"""
    return str(course.get("language_label") or "Python")


def _tutor_code_snippets(files: list[dict], solution_file: str, mode: str, active_file: str) -> list[str]:
    """AI 导师能看到哪些项目文件。按本关的实现文件后缀派生，13 关共用同一套判据。"""
    suffix = Path(solution_file).suffix
    return [
        f"--- {item['path']} ---\n{redact_secrets(item['content'][:2500])}"
        for item in files
        if item["path"].endswith((suffix, ".txt", ".md")) and (mode == "agent" or item["path"] == active_file)
    ]


def _course(exercise_id: str) -> dict:
    exercise = get_flagship_exercise(exercise_id) or {}
    track_id = exercise_id.split("-", 1)[0]
    track = TRACK_CONFIG[track_id]
    # 本关的语言属性决定文件名、阶段措辞与判题执行路径。必须放在下面所有
    # _IMPL_NOTES / _FIRST_RUN_STAGES / stages 的构造之前。
    language = lab_language(exercise_id)
    solution_file = lab_solution_file(exercise_id)
    repair_file = lab_repair_file(exercise_id)
    language_label = lab_language_label(exercise_id)
    spec = SPECS[exercise_id]
    declared_targets = spec.get("targets") or ([spec.get("target")] if spec.get("target") else [])
    targets = [str(item) for item in declared_targets]
    if spec.get("mode") == "checkpoint":
        targets = ["save_checkpoint", "load_checkpoint"]
    # 本关自己的函数排在首位，其后是从上一关累积下来的「算法工具箱」函数。
    # 判分只看 spec["target"]，这里多出来的名字只用于「函数是否还在工具箱里」的结构检查。
    # 阶段一是累积式项目（1-2 继承 1-1、1-3 继承 1-2）。只在前一关与本关语言
    # 相同时才继承：1-1 改成 C++ 后，1-2 再宣称「继承 1-1 的 solution.py」就是假话，
    # 而且 _carry_over_toolbox 也找不到那个文件。
    _CARRIES_FROM = {"1-2": "1-1", "1-3": "1-2"}
    previous = _CARRIES_FROM.get(exercise_id, "")
    carries_from = previous if previous and lab_language(previous) == lab_language(exercise_id) else ""
    carried_targets = targets[1:] if carries_from else []

    # 每个实验对应的配套文档（tutorial_documents 种子中的 knowledge_tag）
    _KNOWLEDGE_TAGS = {
        "1-1": "dsa-dsa-linear-data-structures",
        "1-2": "dsa-dsa-linear-data-structures",
        "1-3": "dsa-dsa-linear-data-structures",
        "2-1": "dsa-binary-search-tree-insert",
        "2-2": "dsa-binary-search-traverse",
        "2-3": "dsa-heap-shift-up",
        "2-4": "dsa-heap-sort",
        "3-1": "dsa-graph-theory-deep",
        "3-2": "dsa-union-find-compress",
        "3-3": "dsa-graph-theory-short-path",
        "4-1": "dsa-dsa-basic-algorithm",
        "4-2": "dsa-merge-sort",
        "4-3": "dsa-dsa-hash-table",
    }
    knowledge_tag = _KNOWLEDGE_TAGS.get(exercise_id, "")
    # 学习文档的内部标签（如 dsa-dsa-linear-data-structures）对用户不友好，
    # 卡片里改显示「文档 › 小节」的可读名称。
    _KNOWLEDGE_LABELS = {
        "1-1": "数据结构与算法 › 线性数据结构 › 数组（Array）",
        "1-2": "数据结构与算法 › 线性数据结构 › 链表（Linked List）",
        "1-3": "数据结构与算法 › 线性数据结构 › 栈（Stack）",
        "2-1": "数据结构与算法 › 二叉搜索树 › 插入与查找",
        "2-2": "数据结构与算法 › 二叉搜索树 › 遍历",
        "2-3": "数据结构与算法 › 堆 › 上浮与下沉",
        "2-4": "数据结构与算法 › 堆 › 堆排序",
        "3-1": "数据结构与算法 › 图论 › 深度优先遍历",
        "3-2": "数据结构与算法 › 并查集 › 路径压缩",
        "3-3": "数据结构与算法 › 图论 › 最短路径",
        "4-1": "数据结构与算法 › 基础算法 › 模块化与接口",
        "4-2": "数据结构与算法 › 排序算法 › 归并排序",
        "4-3": "数据结构与算法 › 哈希表（Hash Table）",
    }
    knowledge_label = _KNOWLEDGE_LABELS.get(exercise_id, knowledge_tag)

    implementation_steps = [str(item).strip() for item in exercise.get("steps", []) if str(item).strip()]
    implementation_hint = (
        f" 建议按这个顺序完成：{' → '.join(implementation_steps)}。"
        if implementation_steps else ""
    )
    test_count = max(len(spec.get("cases", [])) + int(spec.get("extra_cases", 0)), 4)
    # ── 实验专属实现指引（补充步骤卡片中太简略的描述） ──
    _IMPL_NOTES = {
        "1-1": (
            "接收 items、index、value 三个参数。先校验 items 是列表（字符串、字典都不算），"
            "再校验 index 是非布尔整数且落在 [0, len(items)] 内——索引等于长度是合法的，表示追加到末尾。"
            "然后复制一份 items（如 result = list(items)）再插入，绝不能直接改传入的列表。\n\n"
            "注意两个容易踩的坑：Python 的 list.insert 支持负数索引，但本题要求负数直接报错；"
            "bool 是 int 的子类，isinstance(True, int) 为 True，需要显式排除。"
        ),
        "1-2": (
            "接收 head 一个参数，它要么是 None（空链表），要么是形如 {\"value\": 值, \"next\": 下一个节点或 None} 的字典。\n\n"
            "先校验整条链：每个节点必须同时含 value 与 next 键，next 必须是节点或 None，"
            "任何一处不合法都抛出 ValueError——注意要在解引用之前校验，否则会先抛 KeyError 或 TypeError。\n\n"
            "反转用经典的 prev / node 双指针：每步先记住 next，再把当前节点的指针指向 prev，"
            "然后两个指针整体前移。要求构造新节点而不是改动原链表，所以赋值时应新建字典。"
        ),
        "1-3": (
            "接收 tokens 一个参数（字符串列表），返回整数结果。用一个列表当栈：\n\n"
            "1. 遇到数字 token 就 int(token) 后压栈；\n"
            "2. 遇到运算符必须先弹出右操作数、再弹出左操作数（顺序反了减法和除法就全错）；\n"
            "3. 除法用 int(left / right) 实现向零截断，不要用 // —— Python 的 // 是向下取整，"
            "-7 // 2 得 -4，而本题要求 -3；\n"
            "4. 循环结束后栈里必须恰好剩一个值，多了少了都说明表达式不合法。\n\n"
            "除数为 0、token 不是字符串、数字写法非法、运算符未知时都要抛出 ValueError。"
        ),
        "2-1": (
            "树用三元素列表表示：[值, 左子树, 右子树]，None 表示空树。\n\n"
            "1. 先写一个校验函数，用中序遍历把树摊平成值列表，确认严格递增——"
            "不满足「左小右大」就不是合法 BST，先抛 ValueError；\n"
            "2. value 必须是非布尔整数（bool 是 int 的子类，要显式排除）；\n"
            "3. bst_insert 递归下降：走到 None 就返回新叶子 [value, None, None]；"
            "比当前节点小就走左、大就走右；相等说明重复，直接抛 ValueError；\n"
            "4. 每层都要构造新列表（形如 return [node[0], insert(node[1]), node[2]]），"
            "不要写 node[1] = ...，那会改动传入的树；\n"
            "5. bst_search 用 while 循环只走一条路径就够，不需要递归，更不需要建新树。\n\n"
            "容易踩的坑：[] 也是列表但不是合法节点——节点必须是长度恰好 3 的列表。"
        ),
        "2-2": (
            "两个函数共用同一套树表示：[值, 左子树, 右子树] 或 None。\n\n"
            "1. 先写一个只做结构校验（节点长度、值类型）的辅助函数，两个遍历都先用它挡掉非法输入；\n"
            "2. bst_inorder：递归顺序必须是「左子树 → 当前节点的值 → 右子树」。"
            "用一个外层列表收集结果，内层递归函数负责下降；顺序写错就会退化成前序（根跑到第一个位置）；\n"
            "3. bst_level_order：维护「当前层」和「下一层」两个列表，"
            "每轮先记录 [node[0] for node in current] 得到本层的值，"
            "再把 current 中每个节点的非空左右子树依次追加进下一层，然后整体切换。\n\n"
            "容易踩的坑：空子树不要放进下一层，否则输出里会混进 None，"
            "与「缺失的节点不占位置」这一约定不符。"
        ),
        "2-3": (
            "大顶堆用列表按层序存储，下标 i 的父节点是 (i-1)//2，左子节点是 2i+1、右子节点是 2i+2。\n\n"
            "1. 先校验 heap 是整数列表、index 与 size 是非布尔整数，并检查下标范围；\n"
            "2. heap_shift_up：从 index 出发，只要 index > 0 就把自己和父节点 (index-1)//2 比较，"
            "比父节点大就交换并把 index 上移，否则立即 break。根节点没有父节点，循环条件不能漏；\n"
            "3. heap_shift_down：在 2*index+1 与 2*index+2 里挑出较大的那个子节点，"
            "但两个子节点的下标都必须 < size —— 这里用 size 而不是 len(heap) 判断，"
            "正是堆排序能复用它缩小堆范围的前提；\n"
            "4. 两个函数都先 result = list(heap) 复制一份再操作，返回新列表。\n\n"
            "容易踩的坑：先选较大的子节点、再拿它和当前节点比，顺序反了会选错分支。"
        ),
        "2-4": (
            "堆排序 = 建堆 + 反复把最大值换到末尾，两步都靠同一个下沉函数。\n\n"
            "1. 校验并复制一份 result = list(items)；\n"
            "2. 建堆：从最后一个非叶子节点开始往前逐个下沉，"
            "也就是 for start in range(len(result) // 2 - 1, -1, -1)。"
            "从 n//2-1 开始就够了，再往后的都是叶子；顺序必须是从后往前；\n"
            "3. 排序：让 end 从 len(result)-1 递减到 1，每轮把 result[0]（当前最大值）与 result[end] 交换，"
            "再对 result[0] 在 [0, end) 范围内下沉一次——边界传的是 end 而不是 len(result)，"
            "否则刚排好的最大值又会被卷回堆里；\n"
            "4. 循环结束时 result 即为升序。\n\n"
            "容易踩的坑：把下沉写成带 size 参数的版本，建堆和排序就能共用同一个函数。"
        ),
        "3-1": (
            "邻接表用「列表的列表」：第 i 项是节点 i 的邻居，按升序排列。\n\n"
            "1. build_adjacency 先校验 node_count 是正整数、每条边是长度为 2 的整数列表、"
            "端点不越界、不允许自环；\n"
            "2. 对每条边 [u, v] 要在 u 侧和 v 侧各登记一次（无向图就是双向的），"
            "登记前用 if v not in adjacency[u] 去重，最后对每个邻居列表排序，保证结果可复现；\n"
            "3. dfs_order 用一个列表当栈，有两个关键点："
            "一是必须维护已访问集合，否则遇到环会无限循环；"
            "二是压栈时按邻居的逆序压入（邻接表切片 [::-1]），这样先弹出的是升序里的第一个；\n"
            "4. 从 start 出发只能走完它所在的连通分量，不可达的节点不会出现在结果里。\n\n"
            "容易踩的坑：判断「已访问」要在出栈之后、扩展邻居之前做，"
            "并且只把未访问的邻居压栈，否则同一节点会被重复压入。"
        ),
        "3-2": (
            "parent[i] == i 表示 i 是所在集合的根，否则 parent[i] 指向 i 的父亲。\n\n"
            "1. uf_find_root：用 while parent[node] != node 一路往上爬，返回根；只读不写；\n"
            "2. uf_compress：先爬到根，然后 result = list(parent) 复制一份，"
            "再从原节点出发沿路径把每个节点的父指针直接改写成根，最后返回 result。"
            "必须返回新列表——原地改传入的 parent 会破坏不可变约定；\n"
            "3. count_components：初始化 parent = list(range(node_count)) 与 sizes = [1] * node_count，"
            "逐条边找到两个端点各自的根，根相同就跳过，否则按 size 合并"
            "（把小树的根挂到大树的根上并累加 size），最后统计有多少个不同的根。\n\n"
            "容易踩的坑：合并的必须是「根」而不是「节点」——直接写 parent[v] = u 会把两棵树接错；"
            "统计分量时数的是不同的根，不是节点个数。"
        ),
        "3-3": (
            "无权图上 BFS 第一次到达某节点时走过的边数就是最短距离，深度优先做不到这一点。\n\n"
            "1. 先把图建成邻接表（可以直接复用 3-1 的 build_adjacency，顺带把校验带上）；\n"
            "2. start == end 时直接返回 [start]，这是最容易漏的边界；\n"
            "3. previous 字典同时承担两个职责：记录前驱、标记已访问。"
            "先把 previous[start] 置为 None，队列里只放 start；\n"
            "4. 每轮从队首取节点、遍历它的邻居：邻居只要已经在 previous 里就跳过；"
            "否则立刻记下 previous[neighbor] = node ——标记必须发生在「入队的那一刻」，"
            "等出队再标记会让同一节点被重复入队并覆盖前驱，路径就不再最短；\n"
            "5. 命中 end 时用 previous 从 end 往回回溯到 start，再反转得到正序路径；"
            "队列空了仍未命中就返回 None。\n\n"
            "容易踩的坑：回溯出来的是「终点 → 起点」，必须反转；"
            "别用 list.pop(0) 出队，那是 O(n)，用下标指针模拟即可。"
        ),
        "4-1": (
            "这一关把前三阶段的函数集中到一个文件，再给它们一个统一入口。\n\n"
            "1. 先把 5 个函数搬进来：array_insert、reverse_list、eval_rpn、bst_insert、heap_sort，"
            "函数体可以直接沿用前面关卡写好的版本；\n"
            "2. 写一个内部辅助函数（比如 _toolbox_registry）返回「名称 → 函数对象」的字典。"
            "注册表必须在函数内部构造——判题沙箱只允许模块级出现函数定义和字面量赋值，"
            "在模块级写 TOOLBOX = {\"名称\": array_insert} 会直接判为不合规；\n"
            "3. describe_toolbox 返回排序后的名称列表，顺序必须是升序；\n"
            "4. toolbox_call 先校验 name 是字符串、args 是列表，再查注册表，查不到就抛 ValueError；"
            "最后直接调用并返回，不要用 try/except 把异常包起来——"
            "被调用函数自己抛出的 ValueError 必须原样透传给调用方。\n\n"
            "容易踩的坑：多注册或少注册函数都会判错，清单里恰好是那 5 个名字。"
        ),
        "4-2": (
            "归并排序 = 递归切分 + 合并两个有序段，是分治最干净的样板。\n\n"
            "1. merge_sorted(left, right)：用 i、j 两个指针同时扫两个列表，"
            "每次把较小的一端追加进结果并推进对应指针；某个指针走完后，"
            "把另一侧剩下的整段切片后一次性接上；\n"
            "2. merge_sorted 还要先校验两侧各自有序——这是它的前置条件，"
            "不满足时抛 ValueError，否则调用方拿到的会是一个静默给出错误结果的黑盒；\n"
            "3. merge_sort(items)：递归出口是长度 <= 1（返回副本），"
            "否则从中间切开、分别排序后合并；\n"
            "4. is_sorted_ascending(items)：从头扫一遍，"
            "只要发现 items[i] < items[i-1] 就返回 False，全部扫完返回 True。"
            "相等是允许的（非降序），所以判断用 < 而不是 <=。\n\n"
            "容易踩的坑：递归出口写成 len == 0 会在单元素列表上无限递归；"
            "合并时取等号（left[i] <= right[j]），相等元素才不会被打乱相对次序。"
        ),
        "4-3": (
            "LRU 缓存 = 哈希表（O(1) 查找）+ 顺序（决定淘汰谁）。\n\n"
            "1. lru_simulate 先校验 capacity 是正整数、operations 是列表；"
            "用一个普通字典当缓存即可——Python 3.7 起字典保持插入顺序，"
            "所以「最久未使用」永远是字典里的第一个键；\n"
            "2. put：键已存在时先删除再重新赋值，它就挪到了末尾（变成最新）；"
            "写完以后如果长度超过 capacity，删掉最前面那个键；\n"
            "3. get：未命中就往结果里记 -1；命中时同样先删除再重新赋值来刷新新鲜度，"
            "然后把值追加进结果列表。漏掉这一步，LRU 就退化成 FIFO；\n"
            "4. two_sum(nums, target)：一次遍历，边扫边把「值 → 下标」记进字典，"
            "每步先查 target - nums[i] 是否已经在字典里，命中就返回 [旧下标, i]，"
            "扫完无解返回空列表。\n\n"
            "容易踩的坑：先记下当前下标再查，会把同一个元素用两次；"
            "淘汰时删的是字典最前面的键，不是最新那个。"
        ),
    }
    _IMPL_NOTES_CPP = {
        "1-1": (
            "C++ 要点：\n"
            "1. index 的合法范围是 0..items.size()（size() 本身合法，表示追加到末尾），"
            "越界就 throw std::out_of_range；\n"
            "2. 参数是按值传入的，函数体内的 items 已经是副本，但请明确写一行 "
            "std::vector<int> result = items; 再插入——把「不改动入参」写成代码，"
            "而不是依赖语言恰好帮你做到了；\n"
            "3. 插入用 result.insert(result.begin() + index, value)，"
            "不要用 push_back（那只能追加到末尾）；\n"
            "4. 注意 index 是 int，items.size() 是 size_t，比较前先 "
            "static_cast<int>(items.size())，避免有符号/无符号比较的坑。"
        ),
        "1-2": (
            "C++ 要点：\n"
            "1. head 是 Node*（公共类型 struct Node { int value; Node* next; }），"
            "nullptr 表示空链表，先处理 head == nullptr 直接返回 nullptr；\n"
            "2. 用 prev / node 两个指针遍历：node 从 head 出发，每步用 "
            "new Node{node->value, prev} 构造新节点（值复制、next 指向已经反转好的前半段），"
            "再把 node 移到 node->next；\n"
            "3. 必须 new 出新节点，绝不能改写 node->next 的指向——题目要求不修改传入的原链表，"
            "改动了会被 immutable 用例抓到。"
        ),
        "1-3": (
            "C++ 要点：\n"
            "1. tokens 是 std::vector<std::string>，用一个 std::vector<int> 当栈："
            "入栈 push_back，出栈先 back() 取值再 pop_back()；\n"
            "2. 遇到运算符必须先弹右操作数、再弹左操作数（顺序反了减法和除法全错）；\n"
            "3. 除法直接写 left / right——C++ 整数除法天然向零截断（-7 / 2 == -3），"
            "不要手动实现成向下取整；\n"
            "4. 数字 token 用 std::stoi(token, &pos) 解析并检查 pos == token.size()，"
            "否则 \"1.5\" 会被 stoi 截成 1 而不是报错；\n"
            "5. 除零、未知运算符、操作数不足、结束时栈里不是恰好一个值，"
            "都要 throw std::invalid_argument。"
        ),
        "2-1": (
            "C++ 要点：\n"
            "1. 树用公共类型 struct TreeNode { int value; TreeNode* left; TreeNode* right; }，nullptr 表示空树；\n"
            "2. 先写一个校验函数，用中序遍历确认树是合法 BST（严格递增），不满足就 throw std::invalid_argument；\n"
            "3. bst_insert 递归下降：走到 nullptr 就 new TreeNode{value, nullptr, nullptr}；"
            "比当前节点小走左、大走右；相等 throw std::invalid_argument（不允许重复值）；\n"
            "4. 沿途 new 新节点（形如 new TreeNode{root->value, 新左子树, root->right}），"
            "不要改 root->left 的指向；\n"
            "5. bst_search 用 while 沿一条路径比较，命中返回 true，走空返回 false。"
        ),
        "2-2": (
            "C++ 要点：\n"
            "1. 树用 TreeNode，nullptr 表示空树；\n"
            "2. bst_inorder：递归顺序「左子树 → 当前节点 value → 右子树」，用 std::vector<int> 收集结果；\n"
            "3. bst_level_order：维护「当前层 / 下一层」两个 std::vector<TreeNode*>，"
            "每轮收集本层的 value，再把非空左右孩子依次放进下一层；\n"
            "4. 空树两个函数都返回空容器；为 nullptr 的孩子不要放进下一层。"
        ),
        "2-3": (
            "C++ 要点：\n"
            "1. 大顶堆用 std::vector<int> 按层序存储：下标 i 的父节点 (i-1)/2，左孩子 2i+1，右孩子 2i+2；\n"
            "2. heap_shift_up：先校验 index 在 [0, size) 内（越界 throw std::invalid_argument），"
            "复制一份 result，不断与父节点比较、比父节点大就交换；\n"
            "3. heap_shift_down：先校验 size 在 [1, heap.size()] 内、index 在 [0, size) 内，"
            "复制后下沉——在 2*index+1 与 2*index+2 里挑较大的孩子交换，注意子节点下标必须 < size。"
        ),
        "2-4": (
            "C++ 要点：\n"
            "1. 先复制一份 result = items，不要改传入的容器；\n"
            "2. 建堆：从最后一个非叶子节点 total/2 - 1 倒着往前逐个下沉；\n"
            "3. 排序：让 end 从 total-1 递减到 1，每轮交换 result[0] 与 result[end]，"
            "再对 result[0] 在 [0, end) 范围内下沉——边界传 end 而不是 total，否则排好的最大值会被卷回堆里；\n"
            "4. 下沉写成带 size 参数的版本，建堆和排序共用同一个函数。"
        ),
        "3-1": (
            "C++ 要点：\n"
            "1. 邻接表用 std::vector<std::vector<int>>，第 i 项是节点 i 的邻居，升序；\n"
            "2. build_adjacency 先校验 node_count 为正、每条边长度为 2、端点不越界、不允许自环（否则 throw std::invalid_argument），"
            "再对每条边 [u,v] 在 u 侧和 v 侧各登记一次（去重），最后对每个邻居列表 std::sort；\n"
            "3. dfs_order 用递归（或栈）做深度优先：维护 visited 数组，按升序访问邻居，只访问 start 所在连通分量。"
        ),
        "3-2": (
            "C++ 要点：\n"
            "1. parent[i] == i 表示 i 是根，否则 parent[i] 是 i 的父亲；\n"
            "2. uf_find_root：while (parent[x] != x) x = parent[x]; 一路爬到根，只读不写；\n"
            "3. uf_compress：先爬到根，再复制一份 result = parent，沿原路径把每个节点的父指针改写成根，返回新容器；\n"
            "4. count_components：初始化 parent[i]=i、sizes[i]=1，逐条边找根、根相同跳过、否则按 size 合并（小树挂大树），"
            "最后统计 parent[i]==i 的个数。越界、自环、node_count<=0 都 throw std::invalid_argument。"
        ),
        "3-3": (
            "C++ 要点：\n"
            "1. 无权图 BFS 第一次到达某节点的边数就是最短距离；\n"
            "2. 先建邻接表（校验自环/越界/node_count），start==end 直接返回 {start}；\n"
            "3. 用 std::queue 做 BFS，维护 previous 数组记录前驱、visited 数组标记访问（入队即标记）；\n"
            "4. 命中 end 时从 end 沿 previous 回溯到 start，再 std::reverse 得到正序路径；队列空仍未命中返回空容器 {}。"
        ),
        "4-1": (
            "C++ 要点：\n"
            "1. 注册表用 std::map<std::string, std::function<std::vector<int>(const std::vector<int>&)>>，在函数内部构造；\n"
            "2. 登记三个操作：sort（std::sort 升序）、reverse（std::reverse）、dedup（去重，保留首次出现）；\n"
            "3. describe_toolbox 遍历注册表返回操作名（std::map 天然升序）；\n"
            "4. toolbox_call 用 registry.find(name) 查表，未登记 throw std::invalid_argument，命中则调用并返回结果。"
        ),
        "4-2": (
            "C++ 要点：\n"
            "1. merge_sorted(left, right)：双指针 i/j 同时扫，每次取较小的一端 push_back 并推进对应指针，"
            "某侧耗尽后把另一侧剩余整段接上；先校验两侧各自有序（否则 throw std::invalid_argument）；\n"
            "2. merge_sort：递归出口 size<=1（返回副本），否则从中间切开、分别排序后 merge_sorted 合并；\n"
            "3. is_sorted_ascending：扫一遍，发现 items[i] < items[i-1] 就返回 false（相等允许，用 < 不用 <=）。"
        ),
        "4-3": (
            "C++ 要点：\n"
            "1. lru_simulate(capacity, operations)：operations 是 std::vector<std::vector<int>>，[0,k]=get、[1,k,v]=put；\n"
            "2. 用 std::list<int> 维护访问顺序（最久未使用在前），std::unordered_map<int, pair<值, list迭代器>> 做 O(1) 查找；\n"
            "3. get 命中：取值、把该键从 list 中移除再 push 到末尾（刷新新鲜度）；未命中记 -1；\n"
            "4. put：写入或更新并刷新，超出 capacity 时淘汰 list 头部（最久未使用）；capacity<=0 或操作格式非法 throw std::invalid_argument；\n"
            "5. two_sum：一次遍历，unordered_map 记录「值 → 下标」，查 target - nums[i] 是否见过，命中返回 {旧下标, i}，无解返回 {}。"
        ),
    }
    notes_source = _IMPL_NOTES_CPP if language == "cpp" else _IMPL_NOTES
    impl_notes = notes_source.get(exercise_id, "")

    # ── 实验专属「先跑通再提取」阶段（仅 Track 1 实验有此阶段）──
    _FIRST_RUN_STAGES = {
        "1-1": {
            "id": "first_llm_call", "title": "跑通第一段容器操作", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，写下你的第一段容器操作代码（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 定义一个待处理的容器，例如 std::vector<int> items = {1, 2, 3}\n"
                "2. 用 items.insert(items.begin() + 1, 9) 在中间位置插入一个新元素\n"
                "3. 用 std::cout 打印插入前后的结果\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：插入后，插入位置之后的每个元素都往后挪了一格——这就是顺序表插入的代价。"
                "把这段逻辑提取成函数是下一步的事。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "1-2": {
            "id": "first_llm_call", "title": "手工串一条链表", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工构造一条单链表并遍历它（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 用 new Node{值, nullptr} 构造节点：例如 new Node{1, nullptr}\n"
                "2. 手工把三个节点的 next 串起来，形成 1 → 2 → 3\n"
                "3. 用 while 循环沿着 next 逐个 std::cout 打印 value\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：链表没有下标，只能顺着 next 一个一个走——所以想反转整条链，"
                "就必须在走的过程中把指针逐个掉头。下一阶段实现 reverse_list 解决这个问题。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "1-3": {
            "id": "first_llm_call", "title": "用 vector 当栈试试", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，用 vector 当栈做一次手工求值（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 准备一个空栈：std::vector<int> stack\n"
                "2. 依次 push_back 压入 3、4\n"
                "3. 用 back() 取值再 pop_back() 弹出两个值并相加，观察弹出的先后顺序\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：最后压进去的最先弹出来（LIFO）——这正是逆波兰表达式求值不需要括号的原因。"
                "下一阶段实现 eval_rpn 把这个过程自动化。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "2-1": {
            "id": "first_llm_call", "title": "手工搭一棵小 BST", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工搭一棵小 BST 并走一遍查找（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 根节点 10、左孩子 5、右孩子 15，用 new TreeNode{10, new TreeNode{5, nullptr, nullptr}, new TreeNode{15, nullptr, nullptr}} 搭起来\n"
                "2. 手工插入一个 12：从根出发比 10 大往右、比 15 小往左，成为 15 的左孩子\n"
                "3. 再手工找一次 7：比 10 小往左走到 5，比 5 大往右是 nullptr——说明不在树里\n"
                "4. 用 std::cout 打印每一步的走向\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：每次比较都能砍掉一半可能的范围，所以查找走的路径长度取决于树高，"
                "而不是节点个数。下一阶段实现 bst_insert / bst_search 把这个过程自动化。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "2-2": {
            "id": "first_llm_call", "title": "手写一次中序遍历", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工遍历一棵二叉树（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 搭出 10 为根、5 为左孩子、15 为右孩子的小树\n"
                "2. 按「先左、再自己、后右」的顺序，手工写出访问序列，应当是 5 → 10 → 15\n"
                "3. 用递归函数跑一遍，std::cout 打印访问到的 value\n"
                "4. 再按「先自己、再左、后右」打印一次，对比两次输出的差别\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：同一棵树换个访问次序，输出完全不同；中序恰好把 BST 的值按从小到大列出来——"
                "这就是判断一棵树是不是合法 BST 的判据。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "2-3": {
            "id": "first_llm_call", "title": "手工做一次下沉", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工修一次被破坏的堆（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 取出 {5, 3, 8}：下标 0 的 5 比下标 2 的 8 还小，它已经不是大顶堆了\n"
                "2. 用 (i-1)/2 和 2i+1、2i+2 算出 5 的子节点下标，确认哪边更大\n"
                "3. 把 5 和较大的那个子节点交换，得到 {8, 3, 5}\n"
                "4. 交换后检查：8 已经不小于它的子节点，调整可以停下来了\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：一次下沉最多沿一条路径往下走，所以代价是树高而不是节点数——"
                "这正是堆能在 O(log n) 内修复单个位置的原因。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "2-4": {
            "id": "first_llm_call", "title": "手工走一轮堆排序", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工模拟堆排序的一轮（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 准备一个已经是合法大顶堆的容器 {9, 5, 8, 1, 3}\n"
                "2. 把堆顶 9 与最后一个元素交换，得到 {3, 5, 8, 1, 9}\n"
                "3. 把堆的有效长度减一（只看前四个），对新的堆顶 3 做一次下沉\n"
                "4. 确认最大的 9 已经落在最终位置上\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：每轮都能把当前最大值「挤」到末尾的最终位置，重复 n 轮就排好了——"
                "这也解释了为什么排序时必须缩小堆的有效范围。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "3-1": {
            "id": "first_llm_call", "title": "手工画一张邻接表", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工把一张图写成邻接表（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 图有三个节点 0、1、2，边是 0-1、1-2、0-2\n"
                "2. 手工写出每个节点的邻居，应当是 {{1, 2}, {0, 2}, {0, 1}}\n"
                "3. 用 std::vector<std::vector<int>> 写进代码，逐行打印每个节点的邻居\n"
                "4. 再加一条重复边 1-0，确认邻居列表不变——无向边两侧就是同一条边\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：图没有天然顺序，必须先选定一种表示才能动手遍历；"
                "邻接表用「谁的邻居」把结构说清楚了。下一阶段实现 build_adjacency 自动建表。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "3-2": {
            "id": "first_llm_call", "title": "手工沿父指针爬一次根", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工演示并查集的爬根过程（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 用 parent = {1, 2, 2} 表示三个节点：0 的父亲是 1，1 的父亲是 2，2 是根\n"
                "2. 从节点 0 出发：先看 parent[0]=1，再到 parent[1]=2，最后 parent[2]=2 停下\n"
                "3. 用 while 循环把这个过程写成代码，打印访问过的每个节点\n"
                "4. 再手工把 parent 改写成 {2, 2, 2}，从 0 出发再爬一次，比较步数\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：路径压缩让第二次查找只走一步——这就是它把「一层层往上问」"
                "摊还到近乎 O(1) 的原理。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "3-3": {
            "id": "first_llm_call", "title": "手工跑一遍 BFS 队列", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工用队列做一次广度优先搜索（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 用 {{1}, {0, 2}, {1}} 表示一条 0-1-2 的链\n"
                "2. 队列里先放起点 0，用 std::queue 逐个出队\n"
                "3. 取出 0 时把未访问的邻居 1 记进队列；取出 1 时再把 2 记进去\n"
                "4. 每一步都记录「这个节点是从谁那里来的」，打印队列状态\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：按层推进的过程中，每个节点第一次被访问时走过的一定是最少步数——"
                "把每步的来路串起来就是最短路径。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "4-1": {
            "id": "first_llm_call", "title": "先把一个操作当工具调用", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，演示「按名字调用函数」（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 在本文件里写一个最小操作，例如把 std::vector<int> 排序后返回\n"
                "2. 把「名称 → 函数」写成一个 std::map<std::string, std::function<...>>，注意要在函数内部构造\n"
                "3. 写一个按名字查表并调用它的入口函数\n"
                "4. 用 std::cout 打印调用结果，再试一个表里没有的名字，看会抛什么异常\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：调用方从此只需要知道「名字」和「参数」，不再关心操作怎么实现——"
                "这就是把散装操作收拢成工具箱的意义。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "4-2": {
            "id": "first_llm_call", "title": "手工合并两个有序容器", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工把两个有序容器并成一个（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 准备 left = {1, 3, 5} 和 right = {2, 4, 6}\n"
                "2. 用两个下标 i、j 分别指向两个容器开头，每次取较小的那个放进结果\n"
                "3. 每取一个就推进对应的下标，直到某一侧走完\n"
                "4. 打印每一步取到了谁、结果容器现在是什么样\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：每个元素只被看一次就被放进结果，所以合并的代价与总长度成正比；"
                "把这步和「对半切开再递归」接起来，就是归并排序。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
        "4-3": {
            "id": "first_llm_call", "title": "手工模拟一个 LRU 缓存", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，手工模拟容量为 2 的 LRU 缓存（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 用 std::list + std::unordered_map 当缓存，容量设为 2\n"
                "2. 依次写入 1 → 1、2 → 2，此时缓存是 {1: 1, 2: 2}\n"
                "3. 读取 1：命中，把它「刷新」成最新（先从 list 移除再 push 到末尾）\n"
                "4. 再写入 3 → 3：容量超出，淘汰最久未使用的那个（此时是 2）\n\n"
                "写好后点【自测】跑一次样例，确认你观察到的现象与下面描述一致。\n"
                "观察：如果第 3 步忘了刷新，被淘汰的就会是 1——LRU 会退化成 FIFO。"
                "「谁最久没用过」这件事必须显式维护。"
            ),
            "command": "",
            "checks": ["solution.cpp 语法正确", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
    }

    # ── C++ 关卡的热身阶段。与 Python 版的区别：热身不写 main()，因为判题会把
    # 学生的 solution.cpp 和自动生成的 main.cpp 一起编译，多一个 main 会重复定义。
    _FIRST_RUN_STAGES_CPP = {
        "1-1": {
            "id": "first_llm_call", "title": "跑通第一段顺序表操作", "icon": "ChatDotSquare",
            "instruction": (
                "先在 solution.cpp 里热身，用最朴素的方式把这件事做一遍（这一步只求看懂现象，不必写成最终形态）：\n"
                "1. 打开 solution.cpp，找到 array_insert 的骨架\n"
                "2. 先不管边界和值语义，直接在函数体里写：把 value 插到 items 的 index 位置后返回\n"
                "   （例如 items.insert(items.begin() + index, value); return items;）\n"
                "3. 点【自测】跑一次公开样例，看看通过了几条、错在哪一条\n"
                "4. 想一想：返回值对不对？换成越界的下标会发生什么？这些是下个阶段要解决的事\n\n"
                "热身阶段不要求做对，只要动过骨架、跑过一次自测就能进入下一阶段。"
                "注意不要在 solution.cpp 里写 main()——判题会另外生成一个 main。"
            ),
            "command": "",
            "checks": ["solution.cpp 编译通过", "已运行过一次自测"],
            "check_mode": "sample_run",
        },
    }

    # ── 实现阶段标题按实验定制 ──
    _IMPL_TITLES = {
        "1-1": "实现顺序表插入函数",
        "1-2": "实现单链表反转函数",
        "1-3": "实现栈求值函数",
        "2-1": "实现二叉搜索树插入与查找函数",
        "2-2": "实现中序与层序遍历函数",
        "2-3": "实现堆的上浮与下沉函数",
        "2-4": "实现堆排序函数",
        "3-1": "实现邻接表与深度优先遍历函数",
        "3-2": "实现并查集与路径压缩函数",
        "3-3": "实现广度优先最短路径函数",
        "4-1": "把前三阶段函数收拢成工具箱",
        "4-2": "实现归并与有序性判定函数",
        "4-3": "实现 LRU 缓存与两数之和函数",
    }
    impl_title = _IMPL_TITLES.get(exercise_id, f"实现 {', '.join(targets)} 函数")

    # 零依赖、零框架：常驻项目文件只有一个（Python 是 solution.py，C++ 是
    # solution.cpp）。故障修复与变式迁移阶段会另行生成 repair_target.* /
    # VARIANT_TASK.md，但那由 capability_service 负责，不进入这里的结构检查。
    project_files = [solution_file]
    stages = [
        {
            "id": "doc_intro", "title": "文档讲解入门", "icon": "Reading",
            "instruction": (
                f"写代码之前先读文档：点击下方「查看文档讲解」，打开本关配套教程"
                f"（{knowledge_label}）。\n\n"
                "重点通读『我们要解决什么问题』和『本节目标』两节，搞清楚：\n"
                "1. 这一步要实现什么（目标函数 / 项目产物）\n"
                "2. 输入输出契约是什么、验收标准有哪些\n"
                "3. 文档里的示例代码可以点「插入编辑器」放进编辑器，但先理解再动手\n\n"
                "读完文档后点击「AI 检查本阶段」完成入门，再开始搭项目骨架。"
            ),
            "command": "", "checks": ["已打开并阅读配套文档讲解"],
            "target_file": "",
        },
        {
            "id": "structure", "title": "确认题目文件", "icon": "FolderOpened",
            "instruction": (
                f"本关的项目文件是 {', '.join(project_files)}，文件名必须完全一致。\n\n"
                f"打开 {solution_file}，里面已经给出目标函数的骨架与返回值契约，"
                "你的任务就是把它实现出来。不需要创建虚拟环境、不需要声明或安装依赖——"
                f"本关只用 {language_label} 标准库。"
            ),
            "command": "", "checks": [f"{solution_file} 存在", "文件名大小写一致"],
            "target_file": solution_file,
        },
    ]

    # 热身阶段：13 关都有（旧注释曾写「仅 Track 1」，与代码不符）。让学生在写正式
    # 实现之前先把这件事手工做一遍、点自测看现象，再进入 solution.py 的正式实现。
    first_run_source = _FIRST_RUN_STAGES_CPP if language == "cpp" else _FIRST_RUN_STAGES
    first_run = first_run_source.get(exercise_id)
    if first_run is not None:
        first_run["hints"] = _stage_hints(
            "first_llm_call", exercise, targets, track,
            solution_file=solution_file, language=language,
        )
        first_run["target_file"] = solution_file
        first_run["checks"] = [
            f"{solution_file} 编译通过" if language == "cpp" else f"{solution_file} 语法正确",
            "已运行过一次自测",
        ]
        stages.append(first_run)

    implementation_checks = (
        [f"{language_label} 编译通过", f"{test_count} 个业务测试点通过"]
        if language == "cpp"
        # C++ 下「目标函数已定义」不用单独检查：未定义符号就是链接失败，
        # 走同一条编译错误路径，比 Python 时代的 ast 名字扫描更可靠。
        else [f"{language_label} 语法正确", "目标函数已定义", f"{test_count} 个业务测试点通过"]
    )
    stages.append({
        "id": "implementation", "title": impl_title, "icon": "EditPen",
        "instruction": (
            f"创建 {solution_file}，实现 {', '.join(targets)} 函数。"
            f"{implementation_hint}"
            f"{chr(10) + chr(10) + impl_notes if impl_notes else ''}"
        ),
        "command": "", "test_count": test_count,
        "checks": implementation_checks,
        "target_file": solution_file,
        "micro_steps": [
            {
                "id": f"implementation-{index}",
                "title": step,
                "description": "先完成这一小步并用一个最小输入自测，再继续下一步。",
            }
            for index, step in enumerate(implementation_steps, 1)
        ],
    })
    stages.append({
        "id": "acceptance", "title": "AI 工程验收", "icon": "CircleCheck",
        "instruction": (
            "AI 助教将检查代码契约和服务端私有业务场景；"
            "全部通过后再进入能力答辩。你可以多次重试，直到所有检查点通过。"
        ),
        "command": "", "checks": ["前置阶段全部通过", "私有业务场景通过"],
        "target_file": solution_file,
    })

    for stage in stages:
        stage["hints"] = _stage_hints(
            stage["id"], exercise, targets, track,
            solution_file=solution_file, language=language,
        )
    # 阶段文案是 13 关共用的一套模板，里面写死了 solution.py 与「Python 标准库」。
    # 在这里统一按语言替换，而不是去改 13 处字面量——模板加一句新话不用再想一遍
    # 「C++ 关卡要不要另写一份」。替换是幂等的：Python 关卡 solution_file 就是
    # solution.py，替换是空操作。
    for stage in stages:
        for key in ("instruction", "title"):
            if isinstance(stage.get(key), str):
                stage[key] = _localize_text(stage[key], solution_file, language_label)
        stage["checks"] = [_localize_text(str(item), solution_file, language_label) for item in stage.get("checks", [])]
    return {
        "exercise_id": exercise_id,
        "title": exercise.get("title", exercise_id),
        "language": language,
        "language_label": language_label,
        "solution_file": solution_file,
        "repair_target_file": repair_file,
        "module": exercise.get("module", "数据结构实战"),
        "description": exercise.get("description", ""),
        "framework": f"{language_label} 标准库" if language != "python" else track["framework"],
        "packages": [] if language != "python" else track["packages"],
        "framework_imports": [] if language != "python" else track["imports"],
        "targets": targets,
        "carried_targets": carried_targets,
        "carries_from": carries_from,
        "project_files": project_files,
        "starter_code": exercise.get("starter_code", ""),
        "input_output": exercise.get("input_output", ""),
        "acceptance": exercise.get("acceptance", []),
        "skills": exercise.get("skills", []),
        "prerequisites": exercise.get(
            "prerequisites",
            [f"{language_label} 基础", "函数与异常处理"] if language != "python"
            else TRACK_PREREQUISITES.get(exercise_id.split("-", 1)[0], ["Python 基础"]),
        ),
        "reflection_prompts": [
            f"不用看代码，你能解释 {', '.join(targets) or '核心模块'} 的输入、输出与失败条件吗？",
            "如果业务规则发生一个小变化，你会先修改实现、测试还是调用方？为什么？",
        ],
        "knowledge_tag": knowledge_tag,
        "stages": stages,
        # 题面里展示的样例，与「自测」按钮执行的是同一批用例。隐藏用例不下发。
        "samples": public_sample_views(exercise_id),
    }


def _read_files(root: Path) -> list[dict]:
    items = []
    env_names = set(_virtual_envs(root))
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts) or (relative.parts and relative.parts[0] in env_names):
            continue
        if path.is_file() and path.name != ".lab-state.json":
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            items.append({"path": relative.as_posix(), "content": content[:MAX_FILE_SIZE]})
    return items[:100]


def _passed_project_snapshot(root: Path) -> dict[str, str]:
    """Capture the passed project without persisting secrets or virtual envs."""
    snapshot: dict[str, str] = {}
    for item in _read_files(root):
        path = str(item.get("path", ""))
        parts = PurePosixPath(path).parts
        if (
            not path
            or path == "VARIANT_TASK.md"
            or any(part == ".env" or part.startswith(".env.") for part in parts)
            or any(part.lower().endswith((".pem", ".key", ".p12", ".pfx")) for part in parts)
        ):
            continue
        # 存入快照前脱敏，防止硬编码的真实 Key 随快照持久化或被后续判题/展示带出
        snapshot[path] = redact_secrets(str(item.get("content", "")))
    return snapshot


def _restore_passed_project_snapshot(root: Path, snapshot: dict[str, str]) -> None:
    """恢复通关快照中的项目文件，不删除快照之外的本地文件。"""
    if not snapshot:
        return
    for relative, content in snapshot.items():
        target = _safe_path(root, relative, allow_hidden=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        # “全部测试通过”状态必须展示可信快照，而不是当前可能已改坏的同名文件。
        # .env 和密钥类文件不会进入 snapshot，因此不会被这里覆盖。
        target.write_text(str(content), encoding="utf-8")


def _persistable_stage_result(result: dict) -> dict:
    checks = []
    for item in result.get("checks", []):
        saved = {
            key: item[key]
            for key in ("label", "passed", "detail", "category", "next_action")
            if key in item
        }
        if item.get("cases"):
            saved["cases"] = [
                {
                    key: case[key]
                    for key in (
                        "label", "passed", "detail", "category", "next_action",
                        "duration_ms", "input_args", "expected_value", "actual_value",
                    )
                    if key in case
                }
                for case in item["cases"]
            ]
        checks.append(saved)
    return {
        "title": result.get("title", ""),
        "passed": bool(result.get("passed")),
        "summary": result.get("summary", ""),
        "checks": checks,
    }


def _legacy_passed_stage_results(course: dict) -> dict[str, dict]:
    """Make old trusted pass records visible after upgrading snapshot support."""
    return {
        stage["id"]: {
            "title": stage["title"],
            "passed": True,
            "summary": "已恢复此前全部测试通过时的记录",
            "checks": [
                {
                    "label": label,
                    "passed": True,
                    "detail": "该测试点已在此前实验推进中通过",
                }
                for label in stage.get("checks", [])
            ],
        }
        for stage in course["stages"]
    }


def _canonical_passed_project_files(course: dict, solution_code: str) -> dict[str, str]:
    """Build the project snapshot for pass records created before full snapshots.

    单文件模式：整个项目就是本关的实现文件（solution.py / solution.cpp），
    不再补 app.py / requirements.txt。
    """
    return {_course_solution_file(course): solution_code}


def _enrich_passed_stage_results(
    root: Path,
    course: dict,
    stage_results: dict[str, dict],
) -> dict[str, dict]:
    """Attach every real private case to restored pass records."""
    enriched = json.loads(json.dumps(stage_results, ensure_ascii=False))
    solution = root / _course_solution_file(course)
    if not solution.is_file():
        return enriched
    judged = judge_submission(
        str(course.get("exercise_id", "")),
        solution.read_text(encoding="utf-8"),
    )
    cases = _judge_case_feedback(judged)
    if not judged.get("passed") or not cases:
        return enriched

    label_hints = {
        "implementation": ("业务测试点", "核心函数行为"),
        "integration": ("核心业务测试", "核心模块业务测试"),
        "acceptance": ("私有业务场景",),
    }
    for stage_id, hints in label_hints.items():
        stage = enriched.get(stage_id)
        if not isinstance(stage, dict):
            continue
        checks = stage.setdefault("checks", [])
        target_check = next(
            (
                item
                for item in checks
                if any(hint in str(item.get("label", "")) for hint in hints)
            ),
            None,
        )
        if target_check is None:
            target_check = {
                "label": "全部私有业务测试点",
                "passed": True,
            }
            checks.append(target_check)
        target_check.update({
            "passed": True,
            "detail": f"通过 {judged['passed_count']}/{judged['total']} 个真实业务测试点",
            "cases": cases,
        })
    return enriched


def _read_directories(root: Path) -> list[str]:
    directories = []
    env_names = set(_virtual_envs(root))
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        relative = path.relative_to(root)
        if (any(part in SKIP_PARTS or part.startswith(".") for part in relative.parts)
                or (relative.parts and relative.parts[0] in env_names)):
            continue
        directories.append(relative.as_posix())
    return directories[:100]


def _virtual_envs(root: Path) -> list[str]:
    """历史工作区里遗留的虚拟环境目录名，仅用于从文件树中隐藏它们。"""
    result = []
    for cfg in root.glob("*/pyvenv.cfg"):
        if cfg.is_file():
            result.append(cfg.parent.name)
    return sorted(result)


def _read_state(root: Path) -> dict:
    path = root / ".lab-state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"completed_stages": [], "commands": []}


def _write_state(root: Path, state: dict) -> None:
    (root / ".lab-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _assistant_runtime(user_id: int) -> dict:
    """Return safe model availability metadata without exposing credentials."""
    from services.ai_service import _llm_mode

    if _llm_mode(user_id) == "local":
        return {
            "status": "ready",
            "available": True,
            "model": os.getenv("LOCAL_GPU_MODEL_NAME", "edu-ta-qwen3-1.7b-local"),
            "provider": "project_local_gpu",
        }
    try:
        from database import get_db

        conn = get_db()
        row = conn.execute(
            "SELECT provider, model_name, api_key FROM user_llm_config WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
        row = decrypt_config(dict(row)) if row else None
    except Exception:
        # Some isolated service tests intentionally do not initialize the user tables.
        # Treat that state like an unconfigured model instead of polluting logs.
        return {"status": "setup_required", "available": False, "model": "", "provider": ""}
    configured = bool(row and str(row["api_key"] or "").strip())
    return {
        "status": "ready" if configured else "setup_required",
        "available": configured,
        "model": str(row["model_name"] or "") if row else "",
        "provider": str(row["provider"] or "") if row else "",
    }


def _tutor_history(state: dict) -> list[dict]:
    history = []
    for item in state.get("tutor_history", []):
        role = str(item.get("role", ""))
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            history.append({"role": role, "content": content[:6000]})
    return history[-TUTOR_HISTORY_LIMIT:]


def _append_tutor_turn(state: dict, question: str, answer: str) -> None:
    history = _tutor_history(state)
    history.extend([
        {"role": "user", "content": question[:4000]},
        {"role": "assistant", "content": answer[:6000]},
    ])
    state["tutor_history"] = history[-TUTOR_HISTORY_LIMIT:]


def _next_course_stage(course: dict, completed_stages: list[str]) -> dict:
    completed = set(completed_stages)
    return next(
        (stage for stage in course["stages"] if stage["id"] not in completed),
        course["stages"][-1],
    )


def _assistant_welcome(course: dict, stage: dict, runtime: dict) -> str:
    if runtime["available"]:
        return (
            f"我已连接 {runtime['model'] or '你配置的模型'}，并会读取项目、阶段检查和最近对话。"
            f"当前先聚焦“{stage['title']}”；你可以让我诊断、给分级提示，或用问题检查你的理解。"
        )
    return (
        f"当前处于静态项目引导，“{stage['title']}”是下一步。"
        "配置大模型后才会启用能读取项目状态、记住对话并动态追问的 Agent 导师。"
    )


def reset_assistant(user_id: int, exercise_id: str) -> dict:
    root = _root(user_id, exercise_id)
    course = _course(exercise_id)
    state = _read_state(root)
    state["tutor_history"] = []
    state["tutor_hint_levels"] = {}
    _write_state(root, state)
    runtime = _assistant_runtime(user_id)
    stage = _next_course_stage(course, state.get("completed_stages", []))
    return {
        **runtime,
        "history": [],
        "welcome": _assistant_welcome(course, stage, runtime),
    }


def _carry_over_toolbox(root: Path, course: dict) -> None:
    """把上一关通过后的实现文件带进本关，形成累积的「算法工具箱」。

    只在本地还没有实现文件时写入，绝不覆盖学生已经写好的代码。
    优先取上一关的通关快照，没有快照时退回读它的工作区文件。
    """
    previous = str(course.get("carries_from") or "")
    if not previous:
        return
    target = root / _course_solution_file(course)
    if target.is_file():
        return
    source_root = root.parent / _safe_part(previous)
    code = str(_read_state(source_root).get("passed_solution_code") or "")
    if not code.strip():
        legacy = source_root / lab_solution_file(previous)
        if legacy.is_file():
            code = legacy.read_text(encoding="utf-8")
    if code.strip():
        target.write_text(code, encoding="utf-8")


def _seed(root: Path, course: dict, preserved_state: dict | None = None) -> None:
    solution_file = _course_solution_file(course)
    language_label = str(course.get("language_label") or "Python")
    conventions = [f"- 全部实现写在 `{solution_file}` 里，本关不需要其他文件"]
    if course.get("carries_from"):
        conventions.append(
            f"- 本关会在上一关（{course['carries_from']}）的 `{solution_file}` 基础上继续累积："
            "已经写好的函数请保留，不要删掉"
        )
    if str(course.get("language") or "python") == "cpp":
        conventions += [
            "- 判题会把你的 `solution.cpp` 和一份自动生成的 `main.cpp` 一起用 "
            "`g++ -std=c++17` 编译，编译不过就没有分数",
            "- 不要在自己的文件里写 `main()`，也不要改动函数的签名、参数顺序和返回值类型",
            "- 只用 C++17 标准库，不需要 CMake，也不需要安装任何第三方库",
        ]
    readme = (
        f"# {course['title']}\n\n"
        "这是你的独立实验项目。请跟随左侧阶段清单，从读题开始完成本关。\n\n"
        "## 项目目标\n\n"
        f"{course['description']}\n\n"
        "## 约定\n\n"
        + "\n".join(conventions)
        + "\n"
    )
    (root / "README.md").write_text(readme, encoding="utf-8")
    preserved_state = preserved_state or {}
    state = {
        "completed_stages": [],
        "commands": [],
        "project_state": "initial",
    }
    # “初始化项目”只重置工作区，不抹掉用户曾经通过实验推进的事实。
    # 通过快照只保存 solution.py，不复制 .env 等可能含密钥的文件。
    for key in (
        "acceptance_ever_passed",
        "passed_solution_code",
        "passed_project_files",
        "passed_stage_results",
    ):
        if key in preserved_state:
            state[key] = preserved_state[key]
    _write_state(root, state)
    # 累积式关卡（阶段一）初始化后，把上一关的算法工具箱带进本关
    _carry_over_toolbox(root, course)
    # 没能继承到工具箱时，落一份目标函数骨架。structure 阶段要求「打开 solution.py
    # 就能看到返回值契约」，first_llm_call 阶段也要拿它当「还没动过」的比较基准；
    # 缺了这一步，学生一进关就只看到 README，两处判定都无从谈起。
    solution = root / _course_solution_file(course)
    starter = str(course.get("starter_code") or "")
    if not solution.is_file() and starter.strip():
        solution.write_text(starter, encoding="utf-8")


def _completed_stages(state: dict, course: dict) -> list[str]:
    """只返回当前课程仍然开设的阶段，顺序与 course["stages"] 一致。

    数据结构与算法关卡已不再开设 environment / dependencies / integration，
    但旧工作区的 .lab-state.json 里可能还留着这三个 id。原样返回会让前端
    算出「8/5」这种超过总数的进度，所以读取路径也必须过滤一遍。
    """
    done = set(state.get("completed_stages", []))
    return [item["id"] for item in course["stages"] if item["id"] in done]


def get_workspace(user_id: int, exercise_id: str, reset: bool = False) -> dict:
    root = _root(user_id, exercise_id)
    course = _course(exercise_id)
    preserved_state = _read_state(root) if reset else {}
    if reset:
        for child in list(root.iterdir()):
            # 保留 .env 系列（可能含学生自己的配置），其余全部清掉——包括
            # 旧课程遗留的 .venv 与 app.py，它们在单文件模式下已无意义。
            if child.name == ".env" or child.name.startswith(".env."):
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        _seed(root, course, preserved_state)
    elif not any(root.iterdir()):
        _seed(root, course, preserved_state)
    state = _read_state(root)
    if "acceptance" in state.get("completed_stages", []):
        state["acceptance_ever_passed"] = True
        solution = root / _course_solution_file(course)
        if solution.is_file() and not state.get("passed_solution_code"):
            state["passed_solution_code"] = solution.read_text(encoding="utf-8")
        _write_state(root, state)
    # #28：静态提示阶梯按 stage 写死，把最近一次真实报错压成最深一级提示追加到
    # implementation 阶段末尾，让学生卡住时能看到"针对你上次的报错"的具体指引。
    failure_text = str(state.get("last_failure_text") or "").strip()
    if failure_text:
        target_stage = next(
            (s for s in course.get("stages", []) if s.get("id") == "implementation"),
            None,
        )
        if target_stage is not None:
            hints = target_stage.setdefault("hints", [])
            hints.append({
                "level": len(hints) + 1,
                "title": "针对你上次的报错",
                "content": failure_text,
            })
    runtime = _assistant_runtime(user_id)
    completed_stages = _completed_stages(state, course)
    next_stage = _next_course_stage(course, completed_stages)
    return {
        "project_name": f"dsa-lab-{exercise_id}",
        "files": _read_files(root),
        "directories": _read_directories(root),
        "course": course,
        "completed_stages": completed_stages,
        "stage_results": state.get("stage_results", {}),
        "project_state": state.get("project_state", "initial"),
        "state_options": {
            "can_switch_to_passed": bool(
                state.get("acceptance_ever_passed")
                and str(state.get("passed_solution_code", "")).strip()
            ),
            "acceptance_ever_passed": bool(state.get("acceptance_ever_passed")),
        },
        "assistant": {
            **runtime,
            "history": _tutor_history(state),
            "welcome": _assistant_welcome(course, next_stage, runtime),
        },
    }


def get_progress_overview(user_id: int) -> dict:
    """Return lightweight stage progress for course trees and document badges,
    including scores from capability sessions."""
    user_root = WORKSPACE_ROOT / f"user-{int(user_id)}"
    # ── 查询能力验证分数 ──
    try:
        from services.capability_service import get_exercise_scores
        scores = get_exercise_scores(user_id)
    except Exception:
        scores = {}
    overview = {}
    for exercise_id in sorted(SPECS):
        root = user_root / _safe_part(exercise_id)
        state = _read_state(root) if root.is_dir() else {"completed_stages": []}
        course = _course(exercise_id)
        completed_stages = _completed_stages(state, course)
        score_info = scores.get(exercise_id, {})
        overview[exercise_id] = {
            "session_id": score_info.get("session_id"),
            "completed_stages": completed_stages,
            "total_stages": len(course["stages"]),
            "acceptance_passed": "acceptance" in completed_stages,
            "score": score_info.get("score"),
            "test_score": score_info.get("test_score"),
            "defense_score": score_info.get("defense_score"),
            "repair_score": score_info.get("repair_score"),
            "variant_score": score_info.get("variant_score"),
            "verified": score_info.get("verified", False),
            "skipped": score_info.get("skipped", False),
            "status": score_info.get("status", ""),
            "dimensions": score_info.get("dimensions", {}),
            "defense_feedback": score_info.get("defense_feedback", []),
        }
    return overview


def save_file(user_id: int, exercise_id: str, path: str, content: str) -> dict:
    root = _root(user_id, exercise_id)
    target = _safe_path(root, path, allow_hidden=True)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_FILE_SIZE:
        raise ValueError("单个文件不能超过 300KB")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    return {"path": target.relative_to(root).as_posix(), "saved": True}


def create_directory(user_id: int, exercise_id: str, path: str) -> dict:
    root = _root(user_id, exercise_id)
    target = _safe_path(root, path, allow_hidden=True)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": target.relative_to(root).as_posix(), "created": True}


def delete_file(user_id: int, exercise_id: str, path: str) -> dict:
    root = _root(user_id, exercise_id)
    target = _safe_path(root, path, allow_hidden=True)
    if not target.is_file():
        raise ValueError("文件不存在")
    target.unlink()
    return {"path": path, "deleted": True}


def move_entry(user_id: int, exercise_id: str, path: str, destination: str) -> dict:
    root = _root(user_id, exercise_id)
    source = _safe_path(root, path, allow_hidden=True)
    target = _safe_path(root, destination, allow_hidden=True)
    if not source.exists():
        raise ValueError("文件或文件夹不存在")
    if target.exists():
        raise ValueError("目标名称已经存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return {"path": path, "destination": target.relative_to(root).as_posix(), "moved": True}


def duplicate_entry(user_id: int, exercise_id: str, path: str, destination: str) -> dict:
    root = _root(user_id, exercise_id)
    source = _safe_path(root, path, allow_hidden=True)
    target = _safe_path(root, destination, allow_hidden=True)
    if not source.exists():
        raise ValueError("文件或文件夹不存在")
    if target.exists():
        raise ValueError("目标名称已经存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    return {"path": target.relative_to(root).as_posix(), "duplicated": True}


def delete_entry(user_id: int, exercise_id: str, path: str) -> dict:
    root = _root(user_id, exercise_id)
    target = _safe_path(root, path, allow_hidden=True)
    if not target.exists():
        raise ValueError("文件或文件夹不存在")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"path": path, "deleted": True}


def list_entries(user_id: int, exercise_id: str, path: str = "") -> dict:
    """List one project directory, including hidden and virtual-env entries."""
    root = _root(user_id, exercise_id)
    directory = root if not str(path or "").strip("/\\") else _safe_path(root, path, allow_hidden=True)
    if not directory.is_dir():
        raise ValueError("目录不存在")
    entries = []
    for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name == ".lab-state.json":
            continue
        relative = child.relative_to(root).as_posix()
        try:
            size = child.stat().st_size if child.is_file() else 0
        except OSError:
            size = 0
        entries.append({
            "name": child.name,
            "path": relative,
            "is_directory": child.is_dir(),
            "size": size,
            "virtual": child.is_dir() and (child / "pyvenv.cfg").is_file(),
        })
    return {"path": "" if directory == root else directory.relative_to(root).as_posix(), "entries": entries}


def read_file(user_id: int, exercise_id: str, path: str) -> dict:
    """Read a project file on demand so large environments do not block loading."""
    root = _root(user_id, exercise_id)
    target = _safe_path(root, path, allow_hidden=True)
    if not target.is_file():
        raise ValueError("文件不存在")
    size = target.stat().st_size
    if size > 2_000_000:
        return {"path": path, "content": "", "binary": True, "size": size, "message": "文件过大，无法在编辑器中预览"}
    raw = target.read_bytes()
    if b"\x00" in raw:
        return {"path": path, "content": "", "binary": True, "size": size, "message": "二进制文件无法作为文本预览"}
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = raw.decode("gb18030")
        except UnicodeDecodeError:
            return {"path": path, "content": "", "binary": True, "size": size, "message": "该文件不是可识别的文本格式"}
    return {"path": path, "content": content, "binary": False, "size": size}


def _clean_output(value: str, limit: int = 12_000) -> str:
    return (value or "").replace(str(WORKSPACE_ROOT), "<workspace>")[-limit:]


def _redact_tutor_context(value: str, limit: int = 3_000) -> str:
    """Keep useful diagnostics while removing common credential shapes."""
    text = _clean_output(value, limit=limit)
    text = re.sub(
        r"(?i)((?:api[_-]?key|authorization|token|secret|password)\s*[:=]\s*)[^\s]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(r"\b(?:sk|key)-[A-Za-z0-9_-]{12,}\b", "<redacted>", text)
    return text




def apply_project_state(
    user_id: int,
    exercise_id: str,
    target_state: str,
    *,
    solution_code: str = "",
    variant_scenario: str = "",
    variant_target: str = "",
) -> dict:
    """Switch the visible project to a deliberate learning-stage snapshot."""
    if target_state not in {"initial", "passed", "repair", "variant"}:
        raise ValueError("不支持的项目状态")

    if target_state == "initial":
        return get_workspace(user_id, exercise_id, reset=True)

    root = _root(user_id, exercise_id)
    course = _course(exercise_id)
    if not any(root.iterdir()):
        _seed(root, course)
    state = _read_state(root)

    if target_state == "passed":
        # original_code 只会在服务端确认全部测试通过后写入能力会话，
        # 可作为旧工作区缺少本地通关标记时的可信迁移依据。
        if not state.get("acceptance_ever_passed") and str(solution_code).strip():
            state["acceptance_ever_passed"] = True
            state["passed_solution_code"] = solution_code
        if not state.get("acceptance_ever_passed"):
            raise ValueError("只有曾经通过实验推进后，才能跳转到全部测试通过状态")
        solution_code = str(state.get("passed_solution_code") or solution_code)
        if not solution_code.strip():
            raise ValueError("没有找到已通过全部测试点的项目快照")
        snapshot = state.get("passed_project_files")
        if not isinstance(snapshot, dict):
            snapshot = {}
        # 兼容升级前只保存 solution.py 或不完整文件集的通关记录：优先保留
        # 用户仍在的文件，再补齐可运行入口和依赖清单。
        current_files = _passed_project_snapshot(root)
        snapshot = dict(snapshot)
        support_paths = {
            "README.md",
            ".gitignore",
            "app.py",
            "requirements.txt",
            *[str(path) for path in course.get("project_files", [])],
        }
        for path in support_paths:
            if path in current_files:
                snapshot.setdefault(path, current_files[path])
        for path, content in _canonical_passed_project_files(course, solution_code).items():
            snapshot.setdefault(path, content)
        snapshot[_course_solution_file(course)] = solution_code
        state["passed_project_files"] = snapshot
        _restore_passed_project_snapshot(root, snapshot)
    elif target_state != "repair" and not str(solution_code).strip():
        raise ValueError("目标阶段没有可用的项目代码快照")

    # ── 写入目标文件 ──
    if target_state == "repair":
        # 故障修复：将含错代码写入独立文件 repair_target.*
        # solution 文件和其他文件一概不动，保证用户写的代码不会被覆盖
        repair_content = str(solution_code)
        if not repair_content.strip():
            # C++ 写法没有命中变异规则时 mutation_code 为空：留一句人话给学生，
            # 别让「找出被注入的故障」配上一个空文件。
            repair_content = "// 本关暂无可注入的故障：你的实现写法没有命中本关的变异规则。\n"
        (root / (course.get("repair_target_file") or "repair_target.py")).write_text(repair_content, encoding="utf-8")
    elif target_state == "passed":
        # 通关后不动 solution 文件——上面的 _restore_passed_project_snapshot 已补齐支持文件
        pass
    else:
        (root / _course_solution_file(course)).write_text(solution_code, encoding="utf-8")
    variant_task = root / "VARIANT_TASK.md"
    if target_state == "variant":
        task_body = (
            "# 变式迁移任务\n\n"
            f"{variant_scenario.strip()}\n\n"
            "## 当前工作区\n\n"
            f"`{course.get('solution_file') or 'solution.py'}` 已切换为 `{variant_target or '变式目标函数'}` 的独立实现骨架。"
            "请按新场景重新完成，不要在原题答案上直接追加补丁。\n"
        )
        variant_task.write_text(task_body, encoding="utf-8")
    elif variant_task.exists():
        variant_task.unlink()

    state["project_state"] = target_state
    if target_state == "passed":
        state["completed_stages"] = [item["id"] for item in course["stages"]]
        saved_results = state.get("passed_stage_results")
        state["stage_results"] = (
            saved_results
            if isinstance(saved_results, dict) and saved_results
            else _legacy_passed_stage_results(course)
        )
        state["stage_results"] = _enrich_passed_stage_results(
            root,
            course,
            state["stage_results"],
        )
        state["passed_stage_results"] = state["stage_results"]
    elif target_state in {"repair", "variant"}:
        state["completed_stages"] = [item["id"] for item in course["stages"]]
    _write_state(root, state)
    return get_workspace(user_id, exercise_id, reset=False)




def _stage_result(stage: dict, checks: list[dict]) -> dict:
    passed = all(item["passed"] for item in checks)
    return {**stage, "passed": passed, "checks": checks, "summary": "检查通过，可以进入下一步" if passed else "还有项目项需要完善"}


def _judge_check_detail(judged: dict) -> str:
    """Turn private judge output into concise, actionable learner feedback."""
    passed_count = judged.get("passed_count", 0)
    total = judged.get("total", 0)
    if judged.get("passed"):
        return f"通过 {passed_count}/{total} 个业务场景，函数已有可运行的真实行为"
    if judged.get("compile_error"):
        return f"业务测试无法运行：{judged['compile_error']}"
    failed = [
        str(item.get("description", "")).strip()
        for item in judged.get("results", [])
        if not item.get("passed") and str(item.get("description", "")).strip()
    ]
    suffix = f"；请先修正：{'、'.join(failed[:3])}" if failed else ""
    return f"仅通过 {passed_count}/{total} 个业务场景{suffix}"


def _judge_case_feedback(judged: dict) -> list[dict]:
    if judged.get("compile_error"):
        return []
    feedback = []
    for item in judged.get("results", []):
        label = str(item.get("description") or f"测试点 {item.get('case_index', '?')}")[:80]
        passed = bool(item.get("passed"))
        error_raw = str(item.get("error") or "")
        # 解析错误消息中的输入/期望/实际值
        input_args = ""
        expected_val = ""
        actual_val = ""
        if not passed and error_raw:
            for line in error_raw.split("\n"):
                stripped = line.strip()
                if stripped.startswith("输入:"):
                    input_args = stripped[3:].strip()
                elif stripped.startswith("期望:"):
                    expected_val = stripped[3:].strip()
                elif stripped.startswith("实际:"):
                    actual_val = stripped[3:].strip()
            # 取纯错误描述（第一行）
            detail = error_raw.split("\n")[0].strip()[:240]
        else:
            detail = "通过"
        category, next_action = _feedback_guidance(label, detail)
        case_feedback = {
            "label": label,
            "passed": passed,
            "detail": detail,
            "category": category,
            "next_action": "" if passed else next_action,
        }
        # 失败时附带调试信息
        if not passed and (input_args or expected_val or actual_val):
            case_feedback["input_args"] = input_args
            case_feedback["expected_value"] = expected_val
            case_feedback["actual_value"] = actual_val
            case_feedback["duration_ms"] = item.get("duration_ms", 0)
        elif passed:
            case_feedback["duration_ms"] = item.get("duration_ms", 0)
        feedback.append(case_feedback)
    return feedback




def mark_doc_viewed(user_id: int, exercise_id: str) -> dict:
    """记录学生已打开过本关的文档讲解（doc_intro 阶段的判定依据）。"""
    root = _root(user_id, exercise_id)
    state = _read_state(root)
    state["doc_viewed"] = True
    _write_state(root, state)
    return {"doc_viewed": True}


def run_samples(user_id: int, exercise_id: str) -> dict:
    """自测：拿当前的解决方案文件跑一遍公开样例。

    只执行公开样例，隐藏用例既不下发也不执行。运行记录写进 .lab-state.json，
    供 first_llm_call 阶段判定「是否真的跑过一次」。
    """
    if not is_flagship_exercise(exercise_id):
        raise ValueError(f"{exercise_id} 不是项目制私有场景判题任务")
    root = _root(user_id, exercise_id)
    solution_file = _course_solution_file(_course(exercise_id))
    path = root / solution_file
    if not path.is_file():
        raise ValueError(f"还没有 {solution_file}，请先把它写出来再自测")

    outcome = judge_samples(exercise_id, path.read_text(encoding="utf-8"))
    state = _read_state(root)
    state["sample_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state["sample_run_passed"] = bool(outcome.get("passed"))
    state["last_failure_text"] = "" if outcome.get("passed") else _failure_hint_text(outcome)
    state["last_failure_at"] = state["sample_run_at"]
    _write_state(root, state)
    return outcome


def submit_judge(user_id: int, exercise_id: str) -> dict:
    """提交评测：跑本关全部测试点，含不下发的隐藏用例。

    与自测走同一个子进程判题器，区别只在用例集合。不做阶段推进——推进由
    check_stage 负责，这里只是把成绩单交给学生看。
    """
    if not is_flagship_exercise(exercise_id):
        raise ValueError(f"{exercise_id} 不是项目制私有场景判题任务")
    root = _root(user_id, exercise_id)
    solution_file = _course_solution_file(_course(exercise_id))
    path = root / solution_file
    if not path.is_file():
        raise ValueError(f"还没有 {solution_file}，请先把它写出来再提交评测")

    outcome = judge_submission(exercise_id, path.read_text(encoding="utf-8"))
    state = _read_state(root)
    state["last_judge_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state["last_judge_passed"] = bool(outcome.get("passed"))
    if not outcome.get("passed"):
        state["last_failure_text"] = _failure_hint_text(outcome)
        state["last_failure_at"] = state["last_judge_at"]
    _write_state(root, state)
    return outcome


async def explain_judge_failure(user_id: int, exercise_id: str, outcome: dict) -> str | None:
    """判题未通过时，结合学生代码与失败用例生成一次个性化讲解（#20）。

    固定规则的「考点归类 + 下一步」继续兜底；这里补的是「你的代码为什么错」
    这层个性化解释。LLM 不可用（未配 Key、超时、返回异常）时返回 None，
    判题结果原样返回，前端只展示规则反馈——讲解是增强，不是阻塞项。
    """
    from services.ai_service import call_llm

    try:
        exercise = get_flagship_exercise(exercise_id) or {}
        root = _root(user_id, exercise_id)
        path = root / _course_solution_file(_course(exercise_id))
        if not path.is_file():
            return None
        code = redact_secrets(path.read_text(encoding="utf-8"))[:4000]

        failed = [c for c in (outcome.get("cases") or []) if not c.get("passed")][:4]
        if outcome.get("compile_error"):
            failure_lines = [f"代码无法运行：{str(outcome['compile_error'])[:400]}"]
        elif failed:
            failure_lines = [
                "测试点「{desc}」未通过｜输入 {inp}｜期望 {exp}｜实际 {act}｜报错：{detail}｜规则归类：{cat}".format(
                    desc=item.get("description", ""),
                    inp=item.get("input", ""),
                    exp=item.get("expected", ""),
                    act=item.get("actual", ""),
                    detail=item.get("detail", "") or "无",
                    cat=item.get("category", "") or "无",
                )
                for item in failed
            ]
        else:
            return None

        system = (
            "你是 Python 实训平台的判题讲解助手。学生提交的代码未通过服务端私有测试，"
            "请生成一段个性化中文讲解。要求："
            "1. 结合学生代码指出最可能导致失败的具体位置（引用行号或函数名，不要整段复制代码）；"
            "2. 用学生能懂的语言解释期望与实际的差距为什么会发生；"
            "3. 给出修改方向和一个可自查的最小示例，但不要直接给出完整答案代码；"
            "4. 250 字以内，纯文本，可用「-」分点，不要 markdown 标题，不要开场白。"
        )
        user = (
            f"题目：{exercise.get('title', exercise_id)}\n"
            f"题面要求：{str(exercise.get('description', ''))[:600]}\n"
            f"失败情况：\n- " + "\n- ".join(failure_lines) + "\n"
            f"学生代码（疑似密钥已脱敏）：\n```\n{code}\n```"
        )
        text = await call_llm(
            user_id,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=600,
            request_timeout=(10.0, 30.0),
        )
        text = (text or "").strip()
        if not text or text.startswith("LLM调用异常"):
            return None
        return text
    except Exception as exc:
        logger.warning("判题失败讲解生成失败 exercise=%s: %s", exercise_id, exc)
        return None


def check_stage(
    user_id: int,
    exercise_id: str,
    stage_id: str,
    *,
    persist: bool = True,
    allow_runtime: bool = True,
) -> dict:
    root = _root(user_id, exercise_id)
    course = _course(exercise_id)
    stage = next((item for item in course["stages"] if item["id"] == stage_id), None)
    if not stage:
        raise ValueError("未找到该阶段")
    checks: list[dict] = []
    invalidated_stage_ids: list[str] = []
    prior_stage_results: dict[str, dict] = {}

    def add(label: str, passed: bool, detail: str, cases: list[dict] | None = None) -> None:
        item = {"label": label, "passed": bool(passed), "detail": detail}
        if cases:
            item["cases"] = cases
        checks.append(item)

    if stage_id == "doc_intro":
        state = _read_state(root)
        viewed = bool(state.get("doc_viewed"))
        add("已阅读配套文档讲解", viewed,
            "已打开并阅读文档，可以开始搭项目" if viewed else "请先点击「查看文档讲解」打开本关配套教程，读完后回来点检查")
    elif stage_id == "structure":
        for name in course["project_files"]:
            ok = (root / name).is_file()
            add(name, ok, "文件存在，名称完全一致" if ok else f"请在项目根目录创建 {name}")
    elif stage_id == "first_llm_call":
        solution_file = _course_solution_file(course)
        path = root / solution_file
        if not path.is_file():
            add(solution_file, False, f"请先创建 {solution_file}")
        else:
            source = path.read_text(encoding="utf-8")
            if str(course.get("language") or "python") == "cpp":
                # C++ 用「能编译」代替 ast.parse。热身阶段学生还没实现目标函数，
                # 一旦链接就会 undefined reference，所以只做 -fsyntax-only。
                from services.cpp_judge import compile_cpp_only

                compiled = compile_cpp_only(source)
                add(f"{solution_file} 编译", compiled["ok"],
                    "语法检查通过" if compiled["ok"] else compiled["error"])
            else:
                try:
                    ast.parse(source)
                    add(f"{solution_file} 语法", True, "AST 解析成功")
                except SyntaxError as exc:
                    add(f"{solution_file} 语法", False,
                        f"第 {exc.lineno or '?'} 行：{exc.msg}")
            starter = str(course.get("starter_code") or "").strip()
            moved = bool(source.strip()) and source.strip() != starter
            add("已写下你的热身代码", moved,
                f"{solution_file} 内容已超出初始骨架" if moved
                else f"请先在 {solution_file} 里用最朴素的方式把这件事做一遍，不必写成最终形态")
            state = _read_state(root)
            ran = bool(state.get("sample_run_at"))
            add("已运行过一次自测", ran,
                "已检测到自测运行记录" if ran
                else "点面板上的【自测】跑一次样例，观察现象后再进入下一阶段")
    elif stage_id == "implementation":
        solution_file = _course_solution_file(course)
        language = str(course.get("language") or "python")
        path = root / solution_file
        if not path.is_file():
            add(solution_file, False, f"请先创建 {solution_file}")
        else:
            source = path.read_text(encoding="utf-8")
            names: set[str] = set()
            if language == "cpp":
                # C++ 不做名字扫描：目标函数没定义就是链接失败，judge 会连同
                # 编译错误一起报回来，比这里猜一遍更准。
                from services.cpp_judge import compile_cpp_only

                compiled = compile_cpp_only(source)
                add(f"{_language_label_of(course)} 语法", compiled["ok"],
                    "编译单元检查通过" if compiled["ok"] else compiled["error"])
                names = set(course["targets"]) if compiled["ok"] else set()
            else:
                try:
                    tree = ast.parse(source)
                except SyntaxError as exc:
                    add("Python 语法", False, f"第 {exc.lineno or '?'} 行：{exc.msg}")
                else:
                    add("Python 语法", True, "AST 解析成功")
                    names = {
                        node.name for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
            if language != "cpp":
                carried = set(course.get("carried_targets") or [])
                for target in course["targets"]:
                    if target in names:
                        add(target, True, "目标函数已定义")
                    elif target in carried:
                        add(target, False,
                            f"算法工具箱里还缺上一关的 {target}；"
                            f"请先完成上一关让它带过来，或者在本关把它一起补上")
                    else:
                        add(target, False, f"还没有定义 {target}")
            if all(target in names for target in course["targets"]):
                judged = judge_submission(exercise_id, source)
                if judged.get("compile_error"):
                    add("编译与链接", False, judged["compile_error"],
                        _judge_case_feedback(judged))
                add(
                    "核心函数行为", judged.get("passed", False), _judge_check_detail(judged),
                    _judge_case_feedback(judged),
                )
    elif stage_id == "acceptance":
        prior = [
            check_stage(
                user_id,
                exercise_id,
                item["id"],
                persist=False,
                allow_runtime=allow_runtime,
            )
            for item in course["stages"][:-1]
        ]
        prior_stage_results = {
            item["id"]: _persistable_stage_result(item)
            for item in prior
        }
        for item in prior:
            if not item["passed"]:
                invalidated_stage_ids.append(item["id"])
            failed_details = [
                str(check.get("detail", "")).strip()
                for check in item.get("checks", [])
                if not check.get("passed") and str(check.get("detail", "")).strip()
            ]
            detail = item["summary"]
            if failed_details:
                detail = "；".join(failed_details[:3])
            add(item["title"], item["passed"], detail)
        solution = root / _course_solution_file(course)
        if solution.is_file():
            judged = judge_submission(exercise_id, solution.read_text(encoding="utf-8"))
            add(
                "私有业务场景", judged.get("passed", False), _judge_check_detail(judged),
                _judge_case_feedback(judged),
            )
        else:
            add("私有业务场景", False, f"缺少 {_course_solution_file(course)}")

    result = _stage_result(stage, checks)
    state = _read_state(root)
    if persist:
        completed = set(state.get("completed_stages", []))
        if stage_id == "acceptance":
            completed.difference_update(invalidated_stage_ids)
        if result["passed"]:
            completed.add(stage_id)
            if stage_id == "acceptance":
                completed.update(item["id"] for item in course["stages"])
        else:
            completed.discard(stage_id)
        state["completed_stages"] = [item["id"] for item in course["stages"] if item["id"] in completed]
        if stage_id == "acceptance" and result["passed"]:
            state["acceptance_ever_passed"] = True
            solution = root / _course_solution_file(course)
            if solution.is_file():
                state["passed_solution_code"] = solution.read_text(encoding="utf-8")
            state["project_state"] = "passed"
        stage_results = state.setdefault("stage_results", {})
        if stage_id == "acceptance":
            stage_results.update(prior_stage_results)
        stage_results[stage_id] = _persistable_stage_result(result)
        if stage_id == "acceptance" and result["passed"]:
            state["passed_project_files"] = _passed_project_snapshot(root)
            state["passed_stage_results"] = {
                item["id"]: stage_results[item["id"]]
                for item in course["stages"]
                if item["id"] in stage_results
            }
        _write_state(root, state)
    result["completed_stages"] = _completed_stages(state, course)
    return result


def _stage_observation(stage_result: dict) -> tuple[str, list[dict]]:
    checks = stage_result.get("checks", [])
    failed = [item for item in checks if not item.get("passed")]
    lines = [
        f"阶段：{stage_result.get('title', '')}",
        f"检查结论：{'通过' if stage_result.get('passed') else '未通过'}",
    ]
    for item in failed[:6]:
        lines.append(f"- {item.get('label', '检查项')}：{item.get('detail', '')}")
    events = [{
        "tool": "stage_inspector",
        "label": f"检查“{stage_result.get('title', '当前阶段')}”",
        "status": "passed" if stage_result.get("passed") else "attention",
        "detail": f"{len(checks) - len(failed)}/{len(checks)} 项通过",
    }]
    return "\n".join(lines), events


async def ask_assistant(
    user_id: int,
    exercise_id: str,
    question: str,
    active_file: str = "",
    mode: str = "agent",
    stage_id: str = "",
) -> dict:
    root = _root(user_id, exercise_id)
    course = _course(exercise_id)
    question = str(question or "").strip()
    if not question:
        raise ValueError("请先输入问题")
    mode = "chat" if mode == "chat" else "agent"
    from services.guidance_context_service import build_learning_context, public_learning_context
    learning_context = build_learning_context(user_id, question, exercise_id)
    state = _read_state(root)
    history = _tutor_history(state)
    current_stage = next(
        (item for item in course["stages"] if item["id"] == stage_id),
        _next_course_stage(course, state.get("completed_stages", [])),
    )
    snippets = _tutor_code_snippets(_read_files(root), _course_solution_file(course), mode, active_file)
    observations = [{
        "tool": "workspace_reader",
        "label": "读取项目文件",
        "status": "completed",
        "detail": f"已读取 {len(snippets)} 个文本文件",
    }]
    stage_context = "Chat 模式未执行阶段检查"
    if mode == "agent":
        inspected = check_stage(
            user_id,
            exercise_id,
            current_stage["id"],
            persist=False,
            allow_runtime=False,
        )
        stage_context, stage_events = _stage_observation(inspected)
        observations.extend(stage_events)
        sample_run_at = str(state.get("sample_run_at") or "")
        if sample_run_at:
            sample_passed = bool(state.get("sample_run_passed"))
            verdict = "全部样例通过" if sample_passed else "有样例未通过"
            stage_context += f"\n最近自测：{verdict}（{sample_run_at}）"
            observations.append({
                "tool": "sample_observer",
                "label": "读取最近自测结果",
                "status": "completed" if sample_passed else "attention",
                "detail": verdict,
            })
    from services.teaching_policy_service import (
        classify_move, diagnosis_focus, log_decision, mastery_hint_level,
    )
    decision = await classify_move(user_id, question, history)
    teaching_move = decision["move"]
    hint_level = 0
    if teaching_move == "progressive_hint":
        levels = state.setdefault("tutor_hint_levels", {})
        hint_level = mastery_hint_level(
            state, current_stage["id"], int(levels.get(current_stage["id"], 0))
        )
    focus_note = diagnosis_focus(state)
    role_hint = (
        "你处于 Chat 问答模式：直接解释学生的问题，不规划或声称执行项目操作。"
        if mode == "chat" else
        "你处于 Agent 项目模式：先依据工具观察进行诊断，再选择一个最合适的教学动作。"
    )
    prompt = f"""当前实验：{course['title']}，框架：{course['framework']}。
{role_hint}
学生问题：{question}
当前文件：{active_file or '未选择'}
当前阶段：{current_stage['title']}（{current_stage['id']}）
教学动作：{teaching_move}
提示级别：{hint_level or '不适用'}
{focus_note}
工具观察：
{stage_context}

项目内容：
{chr(10).join(snippets)[:9000]}

要求：
1. 必须依据“工具观察”和项目内容回答，不能声称执行了未列出的操作。
2. 一次只推进一个学习目标：先说判断依据，再给下一步和验证方法。
3. progressive_hint 只给当前级别提示；1级只提方向，2级定位结构，3级才给局部示例，禁止直接贴完整答案。
4. socratic_question 只问一个能暴露理解程度的问题，等待学生回答；evaluate_response 要先评价上一问的回答。
5. 重点解释数据结构与算法的对象、参数、边界条件和复杂度作用；Python 基础语法仅在它是根因时解释。
6. 代码和命令必须放进带语言标识的 Markdown 围栏；用中文，控制在 500 字以内。"""
    prompt = prompt.replace("Python 基础语法", f"{course['language_label']} 基础语法")
    runtime = _assistant_runtime(user_id)
    if not runtime["available"]:
        return {
            "answer": "",
            "available": False,
            "status": "setup_required",
            "error": "尚未配置可用的大模型。当前仅提供左侧静态课程引导。",
            "mode": mode,
            "observations": observations,
            "learning_context": public_learning_context(learning_context),
        }
    try:
        from services.ai_service import call_llm
        from services.personalization_service import build_personalized_system_prompt
        system_prompt = build_personalized_system_prompt(
            user_id,
            question,
            "你是编程实验室中的结对导师。只提供与当前实验相关的分步诊断，不直接替学生完成整个项目。",
        )
        system_prompt += (
            "\n\n" + learning_context["prompt"]
            + "\n\n你是有状态的苏格拉底式导师。参考多轮对话判断学生是在提问、求提示，还是回答了你上一轮的问题。"
            "不得重复已经给过的固定话术。"
        )
        llm_messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": prompt},
        ]
        answer = await call_llm(
            user_id,
            llm_messages,
            temperature=0.2,
            max_tokens=900,
        )
        if answer.startswith("LLM调用异常:"):
            raise ValueError(answer)
        from services.answer_guard_service import (
            evaluate_release, log_guard_event, regenerate_and_recheck,
        )

        async def _retry_after_guard(feedback: str) -> str:
            retry_answer = await call_llm(
                user_id,
                [*llm_messages, {"role": "user", "content": feedback}],
                temperature=0.2,
                max_tokens=900,
            )
            if retry_answer.startswith("LLM调用异常:"):
                raise ValueError(retry_answer)
            return retry_answer

        # 时机释放阀：学生贴了自己的代码 / 已被拦多轮 → 放行完整参考讲解
        _release, _release_reason = evaluate_release(user_id, exercise_id, question)
        answer, guard, _regen_attempts = await regenerate_and_recheck(
            answer,
            _retry_after_guard,
            exercise_id,
            log_context={"channel": "assistant", "exercise": exercise_id, "user": user_id},
            release=_release, release_reason=_release_reason,
        )
        if guard.severity == "ok" and _regen_attempts == 0:
            # 保持原口径：每轮都记一条判定（helper 只在 partial/blocked/重生成时记）
            log_guard_event(guard, {"channel": "assistant", "exercise": exercise_id, "user": user_id})
        if hint_level:
            state.setdefault("tutor_hint_levels", {})[current_stage["id"]] = hint_level
        log_decision(state, decision, question, current_stage["id"])
        _append_tutor_turn(state, question, answer)
        _write_state(root, state)
        return {
            "answer": answer,
            "available": True,
            "status": "ready",
            "mode": mode,
            "notice": f"已观察项目与“{current_stage['title']}”阶段",
            "pedagogical_move": teaching_move,
            "hint_level": hint_level,
            "decision_confidence": decision.get("confidence"),
            "guard": guard.to_dict(),
            "observations": observations,
            "learning_context": public_learning_context(learning_context),
        }
    except Exception as exc:
        error_msg = str(exc)
        if "Timeout" in error_msg or "APITimeoutError" in error_msg:
            logger.warning("Lab tutor timeout for user=%s exercise=%s model=%s: %s", user_id, exercise_id, runtime.get('model', 'unknown'), exc)
            return {
                "answer": "",
                "available": False,
                "status": "error",
                "error": (
                    f"模型 {runtime.get('model', '')} 响应超时（5分钟）。可能原因：\n"
                    "1. API 服务当前繁忙，请稍后重试\n"
                    "2. API 接口地址配置有误\n"
                    "3. 网络连接不稳定\n"
                    "建议：稍等片刻后重试，若持续超时请检查 API 配置。"
                ),
                "mode": mode,
                "observations": observations,
                "learning_context": public_learning_context(learning_context),
            }
        logger.warning("Lab tutor model call failed for user=%s exercise=%s: %s", user_id, exercise_id, exc)
        return {
            "answer": "",
            "available": False,
            "status": "error",
            "error": "模型连接失败，本次没有生成导师回答。请检查模型配置后重试。",
            "mode": mode,
            "observations": observations,
            "learning_context": public_learning_context(learning_context),
        }


# ── Lab Assistant Tool Definitions ──

def _lab_tool_schemas(*, allow_writes: bool = False, solution_file: str = "solution.py") -> list[dict]:
    """Build OpenAI Function Calling tool schemas for the lab assistant."""
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "read_project_file",
                "description": (
                    "读取学生项目工作区中的指定代码文件内容。"
                    "在需要查看学生代码、检查实现细节时调用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": f"文件路径，如 {solution_file}、README.md"
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_project_files",
                "description": (
                    "列出学生项目工作区中的所有文件。"
                    "在需要了解项目结构、确认有哪些文件时调用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_stage_status",
                "description": (
                    "检查学生项目某个阶段的完成情况。返回测试通过/失败的详细信息。"
                    "在需要了解学生当前进度、哪些测试点未通过时调用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stage_id": {
                            "type": "string",
                            "description": "阶段标识符，如 structure, environment, dependencies, first_llm_call, implementation, integration, acceptance"
                        }
                    },
                    "required": ["stage_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sample_run_result",
                "description": (
                    f"用当前 {solution_file} 跑一遍本关公开样例，返回逐条的输入、期望与实际结果。"
                    "在学生报告「跑不过」「结果不对」或需要诊断运行时问题时调用此工具。"
                    "隐藏用例不在此工具可见范围内，不要臆测。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_exercise_info",
                "description": (
                    "获取当前关卡的元数据信息，包括所有阶段的标题、完成状态、框架和技能标签。"
                    "在需要了解关卡整体结构、学生进度时调用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
    ]
    if allow_writes:
        schemas.extend([
            {
                "type": "function",
                "function": {
                    "name": "write_project_file",
                    "description": (
                        "创建或完整覆盖项目内的文本文件。用户要求创建文件、填写代码、"
                        "修改配置或修复实现时直接调用；路径只能位于当前项目内。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": f"项目内相对路径，如 {solution_file}"},
                            "content": {"type": "string", "description": "要写入文件的完整文本内容"},
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_project_directory",
                    "description": "在当前项目内创建目录及所需父目录。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "项目内相对目录，如 src/tools"},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            },
        ])
    return schemas


def _execute_lab_tool(tool_name: str, tool_args: dict, user_id: int, exercise_id: str) -> str:
    """Execute a lab assistant tool and return the result as a string."""
    root = _root(user_id, exercise_id)
    state = _read_state(root)

    if tool_name == "read_project_file":
        path = str(tool_args.get("path", "")).strip().lstrip("/")
        if not path:
            return "错误：未指定文件路径"
        file_path = root / path
        if not file_path.exists():
            hint = ", ".join(
                f['path'] for f in _read_files(root)
                if f['path'].endswith((Path(lab_solution_file(exercise_id)).suffix, ".txt", ".md", ".json", ".yml", ".yaml", ".env", ".toml"))
            )
            return f"文件 {path} 不存在。可用文件：{hint}"
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return f"文件 {path} 无法以文本方式读取"
        if len(content) > 2000:
            return content[:2000] + f"\n\n... （文件共 {len(content)} 字符，已截断至前 2000 字符）"
        return content

    elif tool_name == "list_project_files":
        files = _read_files(root)
        if not files:
            return "项目工作区中没有文件"
        lines = []
        for f in files:
            lines.append(f"- {f['path']} ({len(f['content'])} 字符)")
        return "\n".join(lines)

    elif tool_name == "check_stage_status":
        stage_id = str(tool_args.get("stage_id", "")).strip()
        if not stage_id:
            return "错误：未指定阶段 ID"
        course = _course(exercise_id)
        stage = next((s for s in course["stages"] if s["id"] == stage_id), None)
        if not stage:
            valid = ", ".join(s["id"] for s in course["stages"])
            return f"未知阶段 {stage_id}。当前关卡的阶段：{valid}"
        try:
            result = check_stage(user_id, exercise_id, stage_id, persist=False, allow_runtime=False)
        except Exception as exc:
            return f"阶段检查失败：{exc}"
        checks = result.get("checks", [])
        failed = [c for c in checks if not c.get("passed")]
        lines = [
            f"阶段「{stage['title']}」({stage_id})",
            f"检查结论：{'✓ 通过' if result.get('passed') else '✗ 未通过'}",
            f"通过 {len(checks) - len(failed)}/{len(checks)} 项",
        ]
        if failed:
            lines.append("\n未通过的项目：")
            for c in failed[:8]:
                lines.append(f"- {c['label']}：{c.get('detail', '')}")
        return "\n".join(lines)

    elif tool_name == "get_sample_run_result":
        solution_file = _course_solution_file(_course(exercise_id))
        solution = root / solution_file
        if not solution.is_file():
            return f"学生还没有创建 {solution_file}，没有可自测的代码"
        # 现跑一次，而不是回放 .lab-state.json 里的旧记录——助手需要的是学生
        # 此刻代码的真实表现，不是他们上一次点自测时的表现。
        outcome = judge_samples(exercise_id, solution.read_text(encoding="utf-8"))
        if outcome.get("compile_error"):
            return f"样例无法运行：{outcome['compile_error']}"
        lines = [f"公开样例自测：通过 {outcome['passed_count']}/{outcome['total']}"]
        for item in outcome["cases"]:
            lines.append(f"- [{'通过' if item['passed'] else '未通过'}] {item['description']}")
            if not item["passed"]:
                lines.append(f"    输入 {item['input']} / 期望 {item['expected']} / 实际 {item['actual']}")
        return "\n".join(lines)

    elif tool_name == "get_exercise_info":
        course = _course(exercise_id)
        completed = set(state.get("completed_stages", []))
        lines = [
            f"关卡：{course['title']}",
            f"框架：{course['framework']}",
            f"技能：{', '.join(course.get('skills', []))}",
            f"目标文件：{', '.join(course.get('targets', []) or [])}",
            "\n阶段列表：",
        ]
        for s in course["stages"]:
            status = "✓" if s["id"] in completed else "○"
            lines.append(f"  {status} {s['title']} ({s['id']})")
        return "\n".join(lines)

    elif tool_name == "write_project_file":
        path = str(tool_args.get("path", "")).strip()
        content = tool_args.get("content", "")
        if not isinstance(content, str):
            return "错误：文件内容必须是文本"
        saved = save_file(user_id, exercise_id, path, content)
        return f"已写入 {saved['path']}（{len(content.encode('utf-8'))} 字节）"

    elif tool_name == "create_project_directory":
        path = str(tool_args.get("path", "")).strip()
        created = create_directory(user_id, exercise_id, path)
        return f"已创建目录 {created['path']}"

    return f"未知工具：{tool_name}"


def _normalized_lab_tool_calls(message) -> list[dict]:
    """Return complete tool calls after LangChain has merged streamed chunks."""
    calls = []
    for index, raw_call in enumerate(getattr(message, "tool_calls", None) or []):
        if isinstance(raw_call, dict):
            name = str(raw_call.get("name") or "").strip()
            arguments = raw_call.get("args") or {}
            call_id = str(raw_call.get("id") or "").strip()
        else:
            name = str(getattr(raw_call, "name", "") or "").strip()
            arguments = getattr(raw_call, "args", {}) or {}
            call_id = str(getattr(raw_call, "id", "") or "").strip()

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (TypeError, ValueError):
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        if name:
            calls.append({
                "name": name,
                "args": arguments,
                "id": call_id or f"call_{index}",
            })
    return calls


async def ask_assistant_streaming(
    user_id: int,
    exercise_id: str,
    question: str,
    active_file: str = "",
    mode: str = "agent",
    stage_id: str = "",
):
    """Stream lab assistant response with Function Calling tool support via SSE.

    Yields SSE-formatted JSON lines: {"type":"text","content":"..."},
    {"type":"tool_call",...}, {"type":"tool_result",...}, {"type":"done",...}
    """
    import json as _json
    import uuid as _uuid
    from services.ai_service import _build_llm

    root = _root(user_id, exercise_id)
    course = _course(exercise_id)
    question = str(question or "").strip()
    if not question:
        yield _json.dumps({"type": "done", "status": "error", "error": "请先输入问题"}, ensure_ascii=False) + "\n"
        return
    mode = "chat" if mode == "chat" else "agent"

    state = _read_state(root)
    history = _tutor_history(state)
    current_stage = next(
        (item for item in course["stages"] if item["id"] == stage_id),
        _next_course_stage(course, state.get("completed_stages", [])),
    )
    completed = state.get("completed_stages", [])
    from services.teaching_policy_service import (
        classify_move, diagnosis_focus, log_decision, mastery_hint_level,
    )
    decision = await classify_move(user_id, question, history)
    teaching_move = decision["move"]
    hint_level = 0
    if teaching_move == "progressive_hint":
        levels = state.setdefault("tutor_hint_levels", {})
        hint_level = mastery_hint_level(
            state, current_stage["id"], int(levels.get(current_stage["id"], 0))
        )
    focus_note = diagnosis_focus(state)

    # Runtime check
    runtime = _assistant_runtime(user_id)
    if not runtime["available"]:
        yield _json.dumps({
            "type": "done", "status": "setup_required",
            "error": "尚未配置可用的大模型。当前仅提供左侧静态课程引导。",
        }, ensure_ascii=False) + "\n"
        return

    # Build lean system prompt (NOT injecting all project files)
    hints_instruction = ""
    if mode == "agent":
        hints_instruction = (
            f"教学动作：{teaching_move}。"
            + (f"提示级别：{hint_level}（1=方向, 2=结构, 3=局部示例）。" if hint_level else "")
        )

    system_prompt = f"""你是编程实验室中的结对导师（苏格拉底式教学）。

【当前关卡】{course['title']}（框架：{course['framework']}）
【当前阶段】{current_stage['title']}（{current_stage['id']}，{len(completed)}/{len(course['stages'])} 已完成）
【学生问题】{question}
【当前打开文件】{active_file or '无'}
{hints_instruction}
{focus_note}

【可用工具】使用工具按需查看代码和项目状态，不要猜测：
- read_project_file(path): 读取项目中的代码文件
- list_project_files(): 浏览项目文件列表
- check_stage_status(stage_id): 查看某阶段的测试通过情况
- get_sample_run_result(): 用当前代码跑一遍公开样例，看逐条通过情况
- get_exercise_info(): 获取关卡元数据和阶段列表
{'''- write_project_file(path, content): 创建文件或写入完整代码
- create_project_directory(path): 创建项目目录''' if mode == 'agent' else ''}

【教学规则】
1. 先诊断，再引导。用工具查看代码/测试结果后，再给建议
2. Agent 模式下，用户明确要求创建、修改、修复时，直接使用工具完成；普通求助仍采用渐进提示
3. 苏格拉底式提问：一次只问一个能暴露理解程度的问题
4. 重点解释数据结构与算法的对象、参数、边界条件和复杂度作用；Python 基础语法仅在它是根因时解释
5. 代码和命令放进 Markdown 围栏，中文回答控制在 500 字以内
6. progressive_hint 按要求给提示；socratic_question 只提问等待回答；evaluate_response 先评价再引导"""
    system_prompt = system_prompt.replace("Python 基础语法", f"{course['language_label']} 基础语法")

    # Build messages with LangChain format for bind_tools
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
    from langchain_openai import ChatOpenAI

    def _to_lc(msg: dict):
        """Convert saved history dict to LangChain message, preserving tool metadata."""
        role = msg.get("role", "user")
        content = str(msg.get("content", "")).strip()
        # Ensure non-empty content for user/assistant; skip truly empty messages
        if not content and role != "system":
            content = " "  # single space avoids empty-content coercion issues
        if role == "system":
            return SystemMessage(content=content)
        elif role == "assistant":
            # Preserve tool_calls and additional_kwargs if they were saved
            extra_kwargs = {}
            tc_list = msg.get("tool_calls")
            if tc_list:
                extra_kwargs["tool_calls"] = tc_list
            if msg.get("additional_kwargs"):
                extra_kwargs.update(msg["additional_kwargs"])
            return AIMessage(content=content, additional_kwargs=extra_kwargs)
        elif role == "tool":
            return ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", "unknown"))
        else:
            return HumanMessage(content=content)

    llm_messages = [SystemMessage(content=system_prompt)]
    for h in history:
        lc_msg = _to_lc(h)
        if lc_msg:
            llm_messages.append(lc_msg)
    llm_messages.append(HumanMessage(content=question))

    schemas = _lab_tool_schemas(allow_writes=mode == "agent", solution_file=course.get("solution_file") or "solution.py")
    observations = []
    collected_answer = ""

    from services.answer_guard_service import (
        GuardVerdict, GuardedStreamFilter, REGEN_FEEDBACK, apply_guard, evaluate_release,
        load_guard_references, log_guard_event,
    )
    # 时机释放阀：学生贴了自己的代码 / 已被拦多轮 → 流式与持久化兜底都放行
    _stream_release, _stream_release_reason = evaluate_release(
        user_id, exercise_id, question,
    )
    guard_filter = GuardedStreamFilter(
        load_guard_references(exercise_id),
        release=_stream_release,
        release_reason=_stream_release_reason,
        log_context={"channel": "stream", "exercise": exercise_id, "user": user_id},
    )

    def _guarded_events(parts):
        """过滤器产物 → SSE 行序列（text 原样下发，guard 事件单独下发）。"""
        for kind, payload in parts:
            if kind == "event":
                yield _json.dumps(payload, ensure_ascii=False) + "\n"
            else:
                yield _json.dumps({"type": "text", "content": payload}, ensure_ascii=False) + "\n"

    try:
        # Disable DeepSeek thinking mode — prevents reasoning_content which
        # requires round-trip preservation across all messages in conversation.
        # Without this, any AIMessage missing its reasoning_content causes
        # "The reasoning_content in the thinking mode must be passed back to the API."
        llm = _build_llm(user_id, temperature=0.2, max_tokens=900,
                         extra_body={"thinking": {"type": "disabled"}})
        llm_with_tools = llm.bind_tools(schemas, tool_choice="auto")

        # Tool calling loop (max 5 rounds to allow multi-step reasoning)
        for _round in range(5):
            full_content = ""
            full_reasoning = ""  # DeepSeek reasoning_content — must be passed back to API
            tool_calls_buffer: list[dict] = []
            merged_chunk = None

            try:
                async for chunk in llm_with_tools.astream(llm_messages):
                    # Tool names, IDs and JSON arguments commonly arrive in
                    # separate chunks. LangChain reconstructs the complete call
                    # when chunks are added together.
                    merged_chunk = chunk if merged_chunk is None else merged_chunk + chunk

                    # Text content
                    chunk_content = chunk.content if hasattr(chunk, 'content') and chunk.content else ""
                    if chunk_content:
                        full_content += chunk_content
                        for guard_line in _guarded_events(guard_filter.feed(chunk_content)):
                            yield guard_line

                    # Reasoning content (DeepSeek thinking mode) — must preserve for API
                    try:
                        if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
                            reasoning = chunk.additional_kwargs.get('reasoning_content', '')
                            if reasoning:
                                full_reasoning += reasoning
                    except Exception:
                        pass  # additional_kwargs can be any type; ignore on access failure

                if merged_chunk is not None:
                    tool_calls_buffer = _normalized_lab_tool_calls(merged_chunk)
                # 轮次边界：结算未闭合围栏，防止跨轮错位
                for guard_line in _guarded_events(guard_filter.end_round()):
                    yield guard_line
            except Exception as stream_err:
                logger.warning("Lab tutor stream error in round %s: %s", _round, stream_err)
                for guard_line in _guarded_events(guard_filter.end_round()):
                    yield guard_line
                if merged_chunk is not None:
                    tool_calls_buffer = _normalized_lab_tool_calls(merged_chunk)
                # If we have tool calls accumulated, try to execute them and continue
                if not tool_calls_buffer or not tool_calls_buffer[0].get("name"):
                    raise  # No tool calls to salvage — re-raise

            # Check if LLM wants to call tools
            if tool_calls_buffer and tool_calls_buffer[0].get("name"):
                # Build AIMessage with tool_calls (ensure valid IDs)
                from langchain_core.messages import AIMessage as LCAIMessage
                lc_tool_calls = []
                for tc in tool_calls_buffer:
                    if tc.get("name"):
                        # Use `or` to properly fallback when id is "" (empty string)
                        valid_id = tc.get("id") or f"call_{_uuid.uuid4().hex[:12]}"
                        tool_args = tc.get("args", {})
                        if tc["name"] == "read_project_file" and not tool_args.get("path"):
                            fallback_path = active_file if active_file and (root / active_file).is_file() else ""
                            if not fallback_path and (root / _course_solution_file(course)).is_file():
                                fallback_path = _course_solution_file(course)
                            if fallback_path:
                                tool_args = {**tool_args, "path": fallback_path}
                        lc_tool_calls.append({
                            "name": tc["name"],
                            "args": tool_args,
                            "id": valid_id,
                        })

                # Preserve reasoning_content for DeepSeek API compatibility
                ai_additional_kwargs = {}
                if full_reasoning:
                    ai_additional_kwargs["reasoning_content"] = full_reasoning

                ai_msg = LCAIMessage(
                    content=full_content or "",
                    tool_calls=lc_tool_calls,
                    additional_kwargs=ai_additional_kwargs,
                )
                llm_messages.append(ai_msg)

                # Execute tools
                for tc in lc_tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("args", {})
                    tool_call_id = tc["id"]  # Guaranteed non-empty

                    yield _json.dumps({
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args,
                    }, ensure_ascii=False) + "\n"

                    # get_sample_run_result 只读代码不改工作区，不算改动类工具。
                    mutating_tool = tool_name in {
                        "write_project_file", "create_project_directory",
                    }

                    # #29 行为通道护栏：AI 直改学生代码（写文件/建目录）与内容通道共用
                    # 同一释放阀（evaluate_release）。未释放时拒绝执行，改为引导，杜绝
                    # "绕过文本护栏、直接调工具把答案写进学生代码"。
                    if mutating_tool and not _stream_release:
                        yield _json.dumps({
                            "type": "tool_result",
                            "tool": tool_name,
                            "status": "blocked",
                            "detail": "护栏拦截：未达释放条件，拒绝直接改写学生代码",
                            "preview": "",
                            "workspace_changed": False,
                        }, ensure_ascii=False) + "\n"
                        observations.append({
                            "tool": tool_name,
                            "label": f"调用 {tool_name}",
                            "status": "blocked",
                            "detail": "护栏拦截：未达释放条件",
                        })
                        log_guard_event(
                            GuardVerdict(blocked=True, severity="full", reasons=["tool_write_blocked"]),
                            {"channel": "tool_guard", "exercise": exercise_id, "user": user_id,
                             "tool": tool_name},
                        )
                        # 回灌拒绝说明，让模型转向引导式教学而非直接改代码
                        llm_messages.append(ToolMessage(
                            content=_TOOL_GUARD_DENY_MESSAGE, tool_call_id=tool_call_id,
                        ))
                        continue

                    try:
                        result = _execute_lab_tool(tool_name, tool_args, user_id, exercise_id)
                    except Exception as tool_err:
                        result = f"工具执行失败: {tool_err}"
                        logger.warning("Lab tool %s failed: %s", tool_name, tool_err)

                    yield _json.dumps({
                        "type": "tool_result",
                        "tool": tool_name,
                        "status": "completed",
                        "detail": f"已执行 {tool_name}",
                        "preview": _redact_tutor_context(result[:500], limit=500),
                        "workspace_changed": mutating_tool,
                    }, ensure_ascii=False) + "\n"

                    observations.append({
                        "tool": tool_name,
                        "label": f"调用 {tool_name}",
                        "status": "completed",
                        "detail": f"已执行 {tool_name}",
                    })

                    # Use the same valid ID for ToolMessage
                    # 发给 AI 前脱敏工具结果，防止 read_project_file 等返回文件里的真实 Key 外泄
                    llm_messages.append(ToolMessage(content=redact_secrets(result), tool_call_id=tool_call_id))

                continue  # Another round for LLM to process tool results

            # No tool calls — final text response
            collected_answer = full_content
            break

        else:
            # Max rounds exceeded — ask LLM to summarize
            collected_answer = full_content if full_content else ""
            if not collected_answer:
                try:
                    llm_messages.append(HumanMessage(content="请根据以上工具调用结果，给出简短总结和建议。"))
                    summary = await llm_with_tools.ainvoke(llm_messages)
                    collected_answer = summary.content or ""
                    if collected_answer:
                        for guard_line in _guarded_events(guard_filter.feed(collected_answer)):
                            yield guard_line
                        for guard_line in _guarded_events(guard_filter.end_round()):
                            yield guard_line
                except Exception:
                    collected_answer = "（工具调用完成，请根据结果继续提问）"

    except Exception as exc:
        error_msg = str(exc)
        logger.warning("Lab tutor streaming failed for user=%s exercise=%s: %s", user_id, exercise_id, exc)
        yield _json.dumps({
            "type": "done",
            "status": "error",
            "available": True,
            "error": error_msg,
            "observations": observations,
        }, ensure_ascii=False) + "\n"
        return

    # Persist conversation（持久化前兜底过一遍护栏，防止泄漏答案进入对话历史）
    final_guard = None
    regen_status = None
    if collected_answer:
        collected_answer, final_guard = apply_guard(
            collected_answer, load_guard_references(exercise_id),
            release=_stream_release,
        )
        if final_guard.blocked and not guard_filter.blocked_count:
            log_guard_event(final_guard, {"channel": "assistant_stream", "exercise": exercise_id, "user": user_id})
        # 重生成再检：兜底复检仍被拦时，带纠正反馈重新生成一次并复检；
        # 通过则用新答案替换（流式已下发的占位拦截文本不撤回，新答案追加下发）
        if final_guard.blocked:
            try:
                retry_msg = await llm.ainvoke(
                    [*llm_messages, HumanMessage(content=REGEN_FEEDBACK)]
                )
                retry_text = str(getattr(retry_msg, "content", "") or "")
                retry_text, retry_verdict = apply_guard(
                    retry_text, load_guard_references(exercise_id)
                )
                if not retry_verdict.blocked:
                    collected_answer = retry_text
                    final_guard = retry_verdict
                    regen_status = "passed"
                    log_guard_event(retry_verdict, {
                        "channel": "assistant_stream_regen", "exercise": exercise_id,
                        "user": user_id, "attempts": 1, "status": "passed",
                    })
                    yield _json.dumps({
                        "type": "guard_regen", "status": "passed", "attempts": 1,
                    }, ensure_ascii=False) + "\n"
                    note = "\n\n---\n**【防泄题护栏·重新生成】** 上一版回答被拦截，以下是按引导重新生成并通过复检的回答：\n\n"
                    yield _json.dumps({
                        "type": "text", "content": note + retry_text,
                    }, ensure_ascii=False) + "\n"
                else:
                    regen_status = "failed"
                    log_guard_event(retry_verdict, {
                        "channel": "assistant_stream_regen", "exercise": exercise_id,
                        "user": user_id, "attempts": 1, "status": "failed",
                    })
                    yield _json.dumps({
                        "type": "guard_regen", "status": "failed", "attempts": 1,
                    }, ensure_ascii=False) + "\n"
            except Exception as regen_err:
                # 重生成失败不影响已完成的主回答与持久化
                logger.warning("Lab tutor guard regen failed for user=%s exercise=%s: %s", user_id, exercise_id, regen_err)
        if hint_level:
            state.setdefault("tutor_hint_levels", {})[current_stage["id"]] = hint_level
        log_decision(state, decision, question, current_stage["id"])
        _append_tutor_turn(state, question, collected_answer)
        _write_state(root, state)

    for guard_line in _guarded_events(guard_filter.close()):
        yield guard_line

    done_payload = {
        "type": "done",
        "status": "ready",
        "available": True,
        "mode": mode,
        "notice": f"已观察项目与“{current_stage['title']}”阶段",
        "pedagogical_move": teaching_move,
        "hint_level": hint_level,
        "decision_confidence": decision.get("confidence"),
        "observations": observations,
    }
    if final_guard is not None:
        done_payload["guard"] = {
            **final_guard.to_dict(),
            "blocked_blocks": guard_filter.blocked_count,
        }
        if regen_status is not None:
            done_payload["guard"]["regen_status"] = regen_status
    yield _json.dumps(done_payload, ensure_ascii=False) + "\n"
