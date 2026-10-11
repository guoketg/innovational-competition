"""C++ 关卡的判题执行路径。

Python 关卡把学生代码 exec 进一个受限命名空间；C++ 关卡换一套等价物：
按关卡声明的签名生成 main.cpp，和学生写的 solution.cpp 分两个编译单元一起
g++ 编译，逐条用例调用后把结果打成 __CASE__ 行回传。

**比对、归类、渲染仍然全部在 Python 侧完成**（judge_service._case_views 那条
管线一行不改）。C++ 只负责把 actual 或 threw 吐回来，因此现有 26 个工作区单测
继续覆盖同一套逻辑。

与 judge_service 一样，这是应用级隔离（拒绝明显的危险调用 + ulimit + 临时目录），
不是安全沙箱。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path


COMPILE_TIMEOUT = 20
CASE_MARKER = "__CASE__"

# ⚠️ 这条路径的边界，写在这里免得以后有人高估它（设计文档的措辞是「应用层隔离边界，
# 不是加固的多租户沙箱」）：
#   1) 判题结论**只在 Python 侧产生**。学生进程只回传观测（actual / threw / mutated /
#      ms），不回传「过没过」——曾经打过 "ok" 字段，那等于让学生进程自己宣布通过。
#   2) 同一个 index 的 payload **取最后一条**，且**出现重复即判该用例失败**：
#      判题器自己的结果行永远打在学生输出之后，所以「在函数体开头打一行伪造」盖不住
#      真结果；但只靠「取最后一条」还不够——学生可以在**后续用例的调用里**给**已经判完
#      的用例**再补一行伪造（该函数每用例都被调用一次，伪造语句也就重复执行），实测
#      能把 index 1..N-1 全部翻成通过。脚手架每条用例只打一行，重复即伪造。
#   3) 仍然关不掉的：学生代码与判题脚手架同进程、共享 stdout。它可以
#      `std::ifstream` 读 main.cpp（拿到用例入参）、可以 dup/freopen 重定向 stdout、
#      可以在全局析构里在判题器结果行之后再补一行伪造、也可以猜出异常类型名。
#      「提前收工」这一类（exit / terminate / 信号）由 returncode 门 + 重复检测 + 黑名单
#      三条挡着，但上面这些**无法在没有 OS 级隔离（独立进程 + 命名空间/seccomp）的前提下
#      彻底关掉**：把真结果行的 stdout 重定向走、再把伪造行写回原 fd，仍然能造出
#      「每条 index 恰好一行、进程正常退出」的假象。
#      本试点按设计文档的定位接受这一残留风险；据此不要说「C++ 判题防作弊」。

# 明显的危险调用直接拒绝。跟 Python 侧的 ast 白名单相比这是权宜之计：
# C++ 没有可用的标准库级沙箱，能做的是「把最危险的一小撮挡在门外」，
# 真正的边界是 ulimit + 临时工作目录 + 判题进程与业务进程分离。
#
# ⚠️ 别把这份清单当防线。它在两轮审查里各漏过一次（先是 exit(0)，再是 terminate()），
# 真正的防线是另外两条**结构性**规则：进程非正常退出即整份不算数（returncode 非 0）、
# 同一 index 出现两行结果即判伪造。黑名单只负责把常见的自杀写法在编译前点名，
# 报出人话——漏掉某个 token 不应该让攻击成立。
BANNED_CPP_TOKENS = (
    "system(", "popen(", "fork(", "execl(", "execv(", "execve(",
    "dlopen(", "setuid(", "chroot(",
    # 进程自杀类，与 Python 侧 ast 策略禁掉 exit/quit/SystemExit 对齐。
    # 少了这一组，「伪造 __CASE__ 行」就能直接变成「整份判题伪造」：学生先打一批
    # 伪造行、再 exit(0)，进程提前且**正常**退出，判题器自己的结果行一条都没来得及
    # 打出来，而 returncode==0 又让「没拿到结果就拒绝」那道兜底不触发。
    # atexit 一并禁掉，否则改由退出时回调打印假行，同样能绕到真结果之后。
    #
    # terminate( 必须一起进来：它把上面那条路换成**非零**返回码，正好绕开「returncode==0
    # 才需要挡」的思路（实测：全局构造里伪造 4 行再 std::terminate() → passed=True, 4/4）。
    # 顺带覆盖 set_terminate(。_exit( / longjmp( 同属「不抛异常、直接终止/跳走」的写法。
    # syscall( / dlsym( 是**同一类里的另一条**：绕开上面这些名字，直接发退出系统调用
    # （实测 syscall(SYS_exit, 0) 与 dlsym(RTLD_DEFAULT, "_exit")(0) 都能拿到
    # passed=True, 4/4，因为它们是**正常**退出、returncode 门不管）。这两个在这类
    # DSA 题里没有任何正当用途，所以收进来。
    # 没把 raise( / signal( / kill( 放进来：它们由 returncode 门覆盖，而 signal( 在
    # 将来用得上 <csignal> 的关卡里会误伤。
    # **仍然不要**把这份清单当防线：内联汇编、手写 `extern "C" void _exit(int);`
    # 之类都绕得过去（见上面第 3 条的说明）。
    "exit(", "_Exit(", "quick_exit(", "abort(", "atexit(",
    "terminate(", "_exit(", "longjmp(", "syscall(", "dlsym(",
)


class CppContractError(RuntimeError):
    """关卡声明的 C++ 契约有误。这是服务端配置问题，不是学生的代码问题。"""


_CPP_SUPPORT = r'''
// ── 判题支持代码（由判题器生成，学生不必也不应关心）──────────────
// 非模板重载必须写在模板之前：模板内部对 int / bool 这类内置类型的调用，只能
// 靠定义点可见的普通查找解析（内置类型没有关联命名空间，ADL 帮不上忙），
// 顺序颠倒会在编译期找不到匹配的重载。
static std::string json_escape(const std::string& s) {
  std::string out;
  for (char c : s) {
    switch (c) {
      case '"':  out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n";  break;
      case '\r': out += "\\r";  break;
      case '\t': out += "\\t";  break;
      default:   out += c;
    }
  }
  return out;
}

static void to_json(std::ostream& os, int v) { os << v; }
static void to_json(std::ostream& os, long v) { os << v; }
static void to_json(std::ostream& os, long long v) { os << v; }
static void to_json(std::ostream& os, double v) { os << v; }
static void to_json(std::ostream& os, bool v) { os << (v ? "true" : "false"); }
static void to_json(std::ostream& os, const std::string& v) { os << '"' << json_escape(v) << '"'; }

template <typename T>
static void to_json(std::ostream& os, const std::vector<T>& v) {
  os << '[';
  for (std::size_t i = 0; i < v.size(); ++i) {
    if (i) os << ',';
    to_json(os, v[i]);
  }
  os << ']';
}
'''.strip()

# 判题器生成的公共类型头文件：链表节点与二叉树节点。学生写的 solution.cpp 与
# 判题脚手架 main.cpp 都要 include 它，所以节点类型在两侧完全一致。学生代码在
# 编译前被前置 `#include "_types.hpp"`（见 run_cpp_judge / compile_cpp_only），
# 因此学生无需自己定义这些结构体，只需按骨架里的注释理解它们的字段即可。
_TYPES_HPP = '''\
#pragma once
// 判题器生成的公共类型：链表节点与二叉树节点（学生代码与判题脚手架共享）。
struct Node { int value; Node* next; };
struct TreeNode { int value; TreeNode* left; TreeNode* right; };
'''

# 链表/树节点的 JSON 序列化与深比较。紧跟 _CPP_SUPPORT 之后（放在 main.cpp 里），
# 复用上面的 json_escape 与基础 to_json 重载。Node 序列化成 {"value":…,"next":…}、
# TreeNode 序列化成 [值,左,右]，与 SPECS 用例里的 expected 完全同构。
_CPP_STRUCT_SUPPORT = r'''
// ── 链表/树节点的序列化与深比较（判题器生成）──────────────
static void to_json(std::ostream& os, const Node* n) {
  if (!n) { os << "null"; return; }
  os << "{\"value\":";
  to_json(os, n->value);
  os << ",\"next\":";
  to_json(os, n->next);
  os << "}";
}

static void to_json(std::ostream& os, const TreeNode* t) {
  if (!t) { os << "null"; return; }
  os << "[";
  to_json(os, t->value);
  os << ",";
  to_json(os, t->left);
  os << ",";
  to_json(os, t->right);
  os << "]";
}

// immutable 用例的深比较：指针按值传入，学生函数仍能改动 pointee，所以
// 不能用 `a != a_before`（那是地址比较），必须逐节点递归比较。
static Node* copy_node(const Node* n) {
  return n ? new Node{n->value, copy_node(n->next)} : nullptr;
}
static TreeNode* copy_tree(const TreeNode* t) {
  return t ? new TreeNode{t->value, copy_tree(t->left), copy_tree(t->right)} : nullptr;
}
static bool same_node(const Node* a, const Node* b) {
  if (a == b) return true;
  if (!a || !b) return false;
  return a->value == b->value && same_node(a->next, b->next);
}
static bool same_tree(const TreeNode* a, const TreeNode* b) {
  if (a == b) return true;
  if (!a || !b) return false;
  return a->value == b->value && same_tree(a->left, b->left) && same_tree(a->right, b->right);
}
'''.strip()


def cpp_policy_error(code: str) -> str | None:
    """最小安全扫描：学生代码里出现这些调用就直接拒绝。"""
    # 注释里出现 system( 是正常的（学生在讲解为什么不用它），先去掉注释再扫。
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", code, flags=re.S)
    # 报「最长」的那个命中项，而不是第一个：子串匹配下 `exit(` 会先命中 `atexit(` /
    # `quick_exit(`，于是学生写 std::atexit(nullptr) 会被告知「不允许调用 exit」——
    # 拒绝了是对的，但点名的不是他写的东西，读起来像判题器认错了。多个同长命中时
    # 取清单里靠前的那个（顺序即优先级），结果稳定。
    hit = max(
        (token for token in BANNED_CPP_TOKENS if token in stripped),
        key=lambda token: (len(token), -BANNED_CPP_TOKENS.index(token)),
        default=None,
    )
    if hit:
        return f"安全检查未通过：C++ 关卡不允许调用 {hit.rstrip('(')}"
    return None


# 类型关键字：出现在末尾说明它本身就是类型的一部分（unsigned int / long long），
# 不是形参名；struct/class/enum/union 属于「首词定调」，后面那个词也不能当形参名剥。
_TYPE_KEYWORDS = {
    "void", "bool", "char", "short", "int", "long", "float", "double",
    "signed", "unsigned", "wchar_t", "char8_t", "char16_t", "char32_t",
    "auto", "const", "volatile", "size_t",
}
_ELABORATED_HEAD = {"struct", "class", "enum", "union"}


def _strip_param_name(text: str) -> str:
    """剥掉签名里的形参名：`std::vector<int> items` → `std::vector<int>`。

    关卡声明的是完整 C++ 签名，而人写签名时一定会带形参名
    （`array_insert(std::vector<int> items, int index, int value)`）。生成的
    main.cpp 要用**纯类型**声明实参变量，留着名字会生成
    `std::vector<int> items a0 = {…};` 这种编译不过的东西。
    只剥「最后一个词是标识符、且它不是类型关键字」的情形，所以
    `unsigned int` / `long long` / `struct Foo` 都原样保留。
    """
    tokens = text.split(" ")
    if len(tokens) < 2:
        return text
    last = tokens[-1]
    if not re.fullmatch(r"[A-Za-z_]\w*", last):
        return text
    if last in _TYPE_KEYWORDS or tokens[0] in _ELABORATED_HEAD:
        return text
    return " ".join(tokens[:-1])


def _normalize_type(type_name: str) -> str:
    """去掉形参名、const 与引用修饰，得到可以直接用来声明变量的类型名。

    注意保留末尾的 `*`（指针是类型的一部分，`Node*` 去掉 `*` 就退化成 `Node`，
    声明 `Node a0` 会编译不过）；只去掉 `&`（引用在值语义签名里不会出现）。
    """
    text = re.sub(r"\s+", " ", type_name).strip()
    text = re.sub(r"^(const|volatile)\s+", "", text).strip()
    text = _strip_param_name(text)
    text = re.sub(r"[\s&]+$", "", text).strip()
    return text


def _cpp_param_types(signature: str) -> list[str]:
    """从签名里取出形参类型。只在最外层逗号处切分，尊重 <> () [] 的嵌套。"""
    if "(" not in signature or ")" not in signature:
        raise CppContractError(f"cpp.signature 不是合法签名：{signature!r}")
    inner = signature[signature.index("(") + 1: signature.rindex(")")]
    if not inner.strip():
        return []
    parts, depth, current = [], 0, ""
    for char in inner:
        if char in "<([":
            depth += 1
        elif char in ">)]":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    parts.append(current)
    return [_normalize_type(part) for part in parts]


def _cpp_element_type(type_name: str) -> str:
    """取 std::vector<T> 的 T；非容器原样返回。"""
    text = _normalize_type(type_name)
    match = re.fullmatch(r"std::vector\s*<\s*(.+?)\s*>", text)
    if not match:
        return text
    return _normalize_type(match.group(1))


def _struct_kind(type_name: str) -> str | None:
    """判断类型是否是判题器生成的链表/树节点。返回 "node" / "tree" / None。"""
    text = _normalize_type(type_name)
    if text == "Node*":
        return "node"
    if text == "TreeNode*":
        return "tree"
    return None


def _cpp_literal(value, type_name: str) -> str:
    """把用例里的 JSON 参数写成 C++ 字面量。不需要任何 JSON 解析库。"""
    kind = _struct_kind(type_name)
    if kind == "node":
        if value is None:
            return "nullptr"
        if isinstance(value, dict):
            val = _cpp_literal(value.get("value"), "int")
            nxt = _cpp_literal(value.get("next"), "Node*")
            return f"new Node{{{val}, {nxt}}}"
        raise CppContractError(f"链表用例参数必须是节点或 null：{value!r}")
    if kind == "tree":
        if value is None:
            return "nullptr"
        if isinstance(value, list) and len(value) == 3:
            v = _cpp_literal(value[0], "int")
            left = _cpp_literal(value[1], "TreeNode*")
            right = _cpp_literal(value[2], "TreeNode*")
            return f"new TreeNode{{{v}, {left}, {right}}}"
        raise CppContractError(f"树用例参数必须是 [值,左,右] 或 null：{value!r}")
    # 容器类型的参数必须用列表表达：标量值（如 int）配 std::vector<...> 是
    # 用例写错了（Python 时代的「传标量当列表」在 C++ 里类型不匹配、编译不过）。
    # 这里直接报服务端错误，而不是生成 {0} 这种编译失败的代码让页面静默翻车。
    if re.fullmatch(r"std::vector\s*<\s*.+?\s*>", _normalize_type(type_name)) and not isinstance(value, list):
        raise CppContractError(
            f"用例参数 {value!r} 与声明类型 {type_name!r} 不匹配：容器类型必须用列表表达"
        )
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if "double" in type_name or "float" in type_name:
            return f"{value}.0"
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        element = _cpp_element_type(type_name)
        return "{" + ", ".join(_cpp_literal(item, element) for item in value) + "}"
    raise CppContractError(
        f"C++ 关卡的用例暂不支持 {type(value).__name__} 类型的参数：{value!r}"
    )


def _cpp_case_block(
    index: int,
    item: dict,
    param_types: list[str],
    target: str,
    exception_types: list[str],
) -> list[str]:
    """生成一条用例的调用与结果打印。整条结果攒在 ostringstream 里最后一次性
    输出：学生代码里的 cout 调试输出就不会把 __CASE__ 行截断成两半。"""
    args = list(item.get("args", []))
    if len(args) != len(param_types):
        raise CppContractError(
            f"用例「{item.get('description')}」有 {len(args)} 个参数，"
            f"而签名声明了 {len(param_types)} 个"
        )
    lines = ["  {", "    std::ostringstream buf;", f'    buf << "{{\\"i\\":{index}";']
    for position, value in enumerate(args):
        ptype = param_types[position]
        lines.append(f"    {ptype} a{position} = {_cpp_literal(value, ptype)};")
        kind = _struct_kind(ptype)
        if kind:
            # 指针按值传入，学生仍能改动 pointee，所以 immutable 用例要深拷贝一份
            # 快照，调用后再逐节点比较。
            lines.append(f"    auto a{position}_before = copy_{kind}(a{position});")
        elif isinstance(value, list):
            # 值语义（vector 等）：拷贝构造就是深拷贝，!= 就是逐元素比较。
            lines.append(f"    auto a{position}_before = a{position};")
    lines.append("    bool mutated = false;")
    # 逐用例计时：评测面板在用例行尾显示「{duration_ms}ms」，Python runner 也是
    # 逐条给的，这条路径不能只有 C++ 关卡缺这一列。
    lines.append("    auto t0 = std::chrono::steady_clock::now();")
    lines.append("    try {")
    call = ", ".join(f"a{position}" for position in range(len(args)))
    lines.append(f"      auto actual = {target}({call});")
    for position, value in enumerate(args):
        ptype = param_types[position]
        kind = _struct_kind(ptype)
        if kind:
            lines.append(
                f"      if (!same_{kind}(a{position}, a{position}_before)) mutated = true;"
            )
        elif isinstance(value, list):
            lines.append(
                f"      if (a{position} != a{position}_before) mutated = true;"
            )
    # 只回传**观测**，不回传判题结论：这里曾经打过 "ok":true/false，等于让运行在
    # 学生机器上的这段代码自己宣布「本条通过」。学生只要伪造一批 __CASE__ 行就能
    # 全绿——而伪造的门槛极低，因为「是否通过」这个判断本来就是这段代码做的。
    # 现在所有结论都在 Python 侧由 _compare_case 从 actual/threw 重新算出来。
    lines.append('      buf << ",\\"actual\\":";')
    lines.append("      to_json(buf, actual);")
    for cpp_type in exception_types:
        lines.append(f"    }} catch (const {cpp_type}&) {{")
        lines.append(f'      buf << ",\\"threw\\":\\"{cpp_type}\\"";')
    lines.append("    } catch (const std::exception& e) {")
    lines.append(
        '      buf << ",\\"threw\\":\\"other\\",\\"what\\":\\""'
        ' << json_escape(e.what()) << "\\"";'
    )
    lines.append("    } catch (...) {")
    lines.append('      buf << ",\\"threw\\":\\"unknown\\"";')
    lines.append("    }")
    lines.append("    auto t1 = std::chrono::steady_clock::now();")
    lines.append(
        "    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();"
    )
    # mutated 在按值签名下**结构上永远为 false**：a{position} 是 main.cpp 的局部量，
    # 按值传给学生的函数，callee 改的是自己的副本，改不到这里。要让学生真改到调用方
    # 的容器，签名得改成引用——而那时链接期就挂了（判题声明的原型是按值）。
    # 保留这段是为了「声明改了签名语言却还允许」这种将来变化下仍能报出来，但要知道
    # 它现在零区分度：它对应的 immutable 用例在 C++ 下永远静默通过。
    lines.append('    if (mutated) buf << ",\\"mutated\\":true";')
    # 用 llround 而不是流格式化（std::fixed）取两位小数：fixed 是粘性状态，
    # 将来在这之后再加字段会被一起改掉。
    lines.append('    buf << ",\\"ms\\":" << std::llround(ms * 100.0) / 100.0 << "}";')
    lines.append(f'    std::cout << "{CASE_MARKER}" << buf.str() << std::endl;')
    lines.append("  }")
    return lines


def _cpp_signatures(contract: dict, target: str) -> dict[str, str]:
    """收集关卡的函数签名表（函数名 → 完整签名）。

    优先读 `cpp.signatures`（多函数关卡）；缺省回退到单函数的 `cpp.signature`，
    此时签名归属 `target`。保留单函数简写是为了不破坏 1-1 试点与既有单测。
    """
    signatures = contract.get("signatures")
    if isinstance(signatures, dict) and signatures:
        return {
            str(name).strip(): str(sig).strip().rstrip(";").strip()
            for name, sig in signatures.items()
        }
    single = str(contract.get("signature") or "").strip().rstrip(";").strip()
    if not single:
        raise CppContractError("关卡声明缺少 cpp.signature 或 cpp.signatures")
    return {target: single}


def build_main_cpp(spec: dict) -> str:
    """按关卡声明生成 main.cpp。"""
    contract = spec.get("cpp") or {}
    target = str(spec.get("target") or "").strip()
    signatures = _cpp_signatures(contract, target)
    if not target or target not in signatures:
        raise CppContractError(f"cpp 契约里找不到目标函数 {target!r}：{signatures}")
    for name, signature in signatures.items():
        if f"{name}(" not in signature.replace(" ", ""):
            raise CppContractError(
                f"cpp.signatures[{name!r}] 与签名不匹配：{signature!r}"
            )

    exception_map = contract.get("exception_map") or {}
    exception_types: list[str] = []
    for cpp_type in exception_map.values():
        text = _normalize_type(str(cpp_type))
        if text == "std::exception" or text in exception_types:
            continue
        exception_types.append(text)

    # 支持代码自己要用的头文件放最前，关卡声明的追加在后（去重）。
    # <chrono>/<cmath> 是判题脚手架自己要用的（逐用例计时），与关卡声明无关。
    # "_types.hpp" 是判题器生成的公共类型头（Node/TreeNode），main.cpp 与
    # solution.cpp 都要 include（solution.cpp 的 include 由 run_cpp_judge 前置）。
    includes = [
        "<iostream>", "<sstream>", "<string>", "<vector>", "<cstddef>",
        "<exception>", "<chrono>", "<cmath>", '"_types.hpp"',
    ]
    for name in list(contract.get("includes") or []):
        if name not in includes:
            includes.append(name)

    lines = [f"#include {name}" for name in includes]
    lines += [
        "",
        _CPP_SUPPORT,
        "",
        _CPP_STRUCT_SUPPORT,
        "",
        "// 关卡声明的函数原型。学生若改动了签名，这里会编译不过或链接不上——",
        "// 换 C++ 之后，「签名不许改」是编译器保证的，不再依赖静态检查。",
    ]
    for signature in signatures.values():
        lines.append(f"{signature};")
    lines += [
        "",
        "int main() {",
    ]
    for index, item in enumerate(spec.get("cases", []), start=1):
        func = str(item.get("func") or target)
        if func not in signatures:
            raise CppContractError(
                f"用例「{item.get('description')}」引用了未声明的函数 {func!r}"
            )
        param_types = _cpp_param_types(signatures[func])
        lines += _cpp_case_block(index, item, param_types, func, exception_types)
    lines += ["  return 0;", "}"]
    return "\n".join(lines) + "\n"


def _first_compiler_error(text: str) -> str:
    """取第一条 error 行。编译时传的是相对文件名，因此不会出现临时目录前缀。"""
    for line in (text or "").splitlines():
        if ": error:" in line or line.startswith("g++:") or ": fatal error:" in line:
            return line.strip()[:300]
        # 链接期诊断同样是「学生的错」，而且比 collect2 那句有用得多：改签名 → ld 报
        # undefined reference（带上判题方期望的完整签名）；学生自己写 main →
        # multiple definition。只认 "collect2: error: ld returned 1 exit status" 等于
        # 什么都没告诉学生，所以这里必须一并收进来。
        if "undefined reference to" in line or "multiple definition of" in line:
            return line.strip()[:300]
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:300]
    return "编译失败，但编译器没有给出错误信息"


def _run_limits() -> None:
    """给判题程序加上限。仅在 POSIX 上由 preexec_fn 调用。"""
    import resource

    cpu = COMPILE_TIMEOUT
    for name, value in (
        ("RLIMIT_CPU", (cpu, cpu)),
        ("RLIMIT_AS", (512 * 1024 * 1024, 512 * 1024 * 1024)),
        ("RLIMIT_FSIZE", (8 * 1024 * 1024, 8 * 1024 * 1024)),
        ("RLIMIT_NPROC", (64, 64)),
    ):
        limit = getattr(resource, name, None)
        if limit is not None:
            try:
                resource.setrlimit(limit, value)
            except (ValueError, OSError):
                pass


def _cpp_repr(value, max_len: int = 300) -> str:
    """与 RUNNER 里的 _safe_repr 保持一致。那份定义在 judge_service.RUNNER 的
    源码字符串里，只能被 runner 子进程使用，无法 import，因此这里镜像一份——
    改一处必须改两处。"""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) > max_len:
        text = text[:max_len] + "...(截断)"
    return text


def _compare_case(
    item: dict, payload: dict | None, exception_map: dict, duplicated: bool = False
) -> dict:
    """把 C++ 侧吐回的一条原始结果，整成与 Python runner 同构的一行。

    报错文案沿用 runner 的三段式（输入/期望/实际），因为评测面板的「实际」列
    就是靠 `_sample_actual` 去 error 里找 `实际:` 这一行取数的。
    """
    description = str(item.get("description", ""))
    if duplicated:
        # 判题脚手架每条用例只打一行。多出来的那一行只可能来自学生代码，
        # 而且它的存在本身就说明这次提交在试图伪造判题输出——这条用例直接判失败，
        # 不采信任何一条（采信「最后一条」会被后续调用里补的那一行翻盘，见
        # _parse_case_lines 的说明）。
        return {
            "description": description,
            "passed": False,
            "error": "这一条的结果行出现了多次，疑似伪造判题输出",
        }
    if payload is None:
        return {
            "description": description,
            "passed": False,
            "error": "程序在跑到这一条用例之前就退出了（可能是崩溃、死循环或提前 return）",
        }

    token = item.get("exception")
    if token:
        want = str(exception_map.get(token) or "")
        if not want:
            raise CppContractError(f"关卡声明缺少异常 {token} 的 C++ 类型映射")
        thrown = payload.get("threw")
        if thrown == want:
            return {"description": description, "passed": True, "error": None}
        if thrown == "other":
            actual = f"抛出了别的异常：{payload.get('what', '')}"
        elif thrown == "unknown":
            actual = "抛出了非 std::exception 的异常"
        elif thrown is None:
            actual = _cpp_repr(payload.get("actual"))
        else:
            actual = f"抛出了 {thrown}"
        return {
            "description": description,
            "passed": False,
            "error": f"该非法输入必须抛出 {token}\n实际: {actual}",
        }

    # payload 里没有「是否通过」这种字段：那是判题器的结论，不能由跑着学生代码的
    # 那个进程自己宣布。这里只读观测——threw 出现即「这次调用没有正常返回」。
    thrown = payload.get("threw")
    if thrown:
        what = str(payload.get("what") or "")
        detail = f"抛出了 {thrown}" + (f"：{what}" if what else "")
        return {
            "description": description,
            "passed": False,
            "error": f"这条用例不应该抛出异常\n实际: {detail}",
        }

    actual = payload.get("actual")
    if actual != item.get("expected"):
        return {
            "description": description,
            "passed": False,
            "error": (
                "返回结果不符合该业务场景\n"
                + "输入: " + _cpp_repr(item.get("args", [])) + "\n"
                + "期望: " + _cpp_repr(item.get("expected")) + "\n"
                + "实际: " + _cpp_repr(actual)
            ),
        }
    if item.get("fresh_result"):
        raise CppContractError("C++ 关卡暂不支持 fresh_result 用例（按身份比较无法直译）")
    if item.get("immutable") and payload.get("mutated"):
        return {
            "description": description,
            "passed": False,
            "error": "函数修改了输入对象\n实际: 入参容器在调用后被改动",
        }
    return {"description": description, "passed": True, "error": None}


def _parse_case_lines(stdout: str) -> tuple[dict[int, dict], set[int]]:
    """从学生程序的标准输出里挑出判题器自己打的结果行。

    学生代码里的 cout 调试输出会混在 stdout 里，所以用 __CASE__ 前缀做标记，
    而不是假设 stdout 只有判题输出。

    返回 `(payloads, duplicated)`：
    - `payloads[index]` 取**最后一条**同名行——判题器自己的结果行永远打在学生输出之后，
      所以「在函数体开头打一行伪造」盖不住真结果。
    - `duplicated` 是出现过 **多于一条**结果行的用例下标。判题脚手架每条用例**只打一行**，
      所以重复只可能来自学生伪造。这一条不能省：只靠「取最后一条」的话，学生可以在**后续
      用例的调用里**给**已经判完的用例**再补一行伪造，让它成为最后一条——实测过，这样
      index 1..N-1 全都能被翻成通过（只有最后一条用例因为不再有学生代码运行而安全）。
    """
    payloads: dict[int, dict] = {}
    seen: set[int] = set()
    duplicated: set[int] = set()
    for line in (stdout or "").splitlines():
        if not line.startswith(CASE_MARKER):
            continue
        try:
            payload = json.loads(line[len(CASE_MARKER):])
        except ValueError:
            continue
        index = payload.get("i")
        if isinstance(index, int):
            if index in seen:
                duplicated.add(index)
            seen.add(index)
            payloads[index] = payload
    return payloads, duplicated


def _payload_duration_ms(payload: dict | None) -> float | None:
    """取出这一条用例的耗时，统一成 float。

    C++ 侧打的是 double，但耗时恰好取整时 JSON 文本里就是 `0`，json.loads 会解析
    成 int；Python runner 那一侧永远是 float（`round(..., 2)`）。这里是判题面板的
    「{duration_ms}ms」与通过快照共用的字段，不统一类型就会时而 int 时而 float。
    """
    value = (payload or {}).get("ms")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compile_cpp_only(code: str, timeout: int = COMPILE_TIMEOUT) -> dict:
    """只做语法与语义检查，不链接。

    `first_llm_call`（热身阶段）用它替代 Python 关卡的 ast.parse：那时学生还没
    实现目标函数，链接必然失败，但「语法对不对」正是这一阶段要回答的问题。
    """
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "_types.hpp").write_text(_TYPES_HPP, encoding="utf-8")
            (Path(temp_dir) / "solution.cpp").write_text(
                f'#include "_types.hpp"\n{code}', encoding="utf-8"
            )
            proc = subprocess.run(
                ["g++", "-std=c++17", "-fsyntax-only", "solution.cpp"],
                cwd=temp_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
    except FileNotFoundError:
        return {"ok": False, "error": "服务器未安装 g++，无法检查 C++ 代码"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"编译检查超时（>{timeout} 秒）"}
    except Exception as exc:  # pragma: no cover - 兜底
        return {"ok": False, "error": f"编译检查失败：{str(exc)[:200]}"}
    if proc.returncode == 0:
        return {"ok": True, "error": ""}
    return {"ok": False, "error": _first_compiler_error(proc.stderr or proc.stdout)}


def run_cpp_judge(code: str, spec: dict, expected_total: int, timeout: int) -> dict:
    """跑一份 C++ spec，返回与 judge_service._run_judge 同构的逐用例结果。"""
    started = time.perf_counter()

    def _fail(message: str) -> dict:
        return {
            "passed": False, "total": expected_total, "passed_count": 0,
            "compile_error": message, "results": [],
            "execution_time": round(time.perf_counter() - started, 3),
            "judge_mode": "server_private_cases",
        }

    policy_error = cpp_policy_error(code)
    if policy_error:
        return _fail(policy_error)

    # 关卡声明写错就让它冒出去：那是服务端配置问题，不该伪装成学生的编译失败。
    main_source = build_main_cpp(spec)
    contract = spec.get("cpp") or {}
    cases = spec.get("cases", [])
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "_types.hpp").write_text(_TYPES_HPP, encoding="utf-8")
            (Path(temp_dir) / "solution.cpp").write_text(
                f'#include "_types.hpp"\n{code}', encoding="utf-8"
            )
            (Path(temp_dir) / "main.cpp").write_text(main_source, encoding="utf-8")
            # 编译单独 try：它的超时是 20 秒（COMPILE_TIMEOUT），与外层的运行超时
            # （timeout 参数，默认 6 秒）不是一回事。混在一起报的话，编译被拖死的学生
            # 会看到「运行超时（>6 秒）」——既指错了阶段，秒数也是错的。
            try:
                compile_proc = subprocess.run(
                    ["g++", "-std=c++17", "-O2", "-Wall", "main.cpp", "solution.cpp", "-o", "prog"],
                    cwd=temp_dir, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=COMPILE_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                return _fail(
                    f"编译超时（>{COMPILE_TIMEOUT} 秒）：提交的代码在编译阶段就耗尽了时间"
                    "（常见于病态模板递归或超大实例化）"
                )
            if compile_proc.returncode != 0:
                return _fail(_first_compiler_error(compile_proc.stderr or compile_proc.stdout))
            run_proc = subprocess.run(
                ["./prog"],
                cwd=temp_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
                preexec_fn=_run_limits if os.name == "posix" else None,
            )
    except FileNotFoundError:
        return _fail("服务器未安装 g++，无法评测 C++ 关卡")
    except subprocess.TimeoutExpired:
        return _fail(f"运行超时（>{timeout} 秒）")
    except Exception as exc:
        return _fail(f"判题执行失败：{str(exc)[:240]}")

    payloads, duplicated = _parse_case_lines(run_proc.stdout or "")
    # 进程**正常结束**是「stdout 上的东西可信」的前提，这条不能跟「拿到了几行结果」做与。
    #
    # 曾经写成 `returncode != 0 and not payloads`：谁都没想到「早退」有第二种死法——
    # 伪造一批 __CASE__ 行（每条用例恰好一行、不重复），然后 std::terminate() 或
    # std::raise(SIGABRT) 自杀。此时 payloads 非空 ⇒ 这道门不触发；每条 index 只出现
    # 一次 ⇒ 「重复即伪造」也不触发；进程在 main 的用例循环**开始之前**就死了，真结果行
    # 一条都不存在 —— 伪造的观测于是被逐条采信，整关判为通过，学生的函数零次调用。
    # （实测复现：terminate 与 raise(SIGABRT) 两条路都拿到 passed=True, 4/4。）
    #
    # 为什么 `returncode != 0` 就足以判定「这一趟不算数」：脚手架每条用例都包在
    # catch (const <映射类型>&) / catch (const std::exception&) / catch (...) 里，
    # **学生函数抛任何异常都不会让进程死**。所以非零返回码只可能来自「进程被杀」——
    # 段错误、terminate、被信号打死——此时 stdout 上的任何内容都不构成证据。
    # 处理方式与「编译返回非 0」对称：编译非 0 = 编译失败，运行非 0 = 运行失败。
    if run_proc.returncode != 0:
        error_lines = (run_proc.stderr or "提交代码未能完成执行").strip().splitlines()
        detail = error_lines[-1][:240] if error_lines else "提交代码未能完成执行"
        return _fail(
            f"判题进程异常退出（exit code {run_proc.returncode}）：{detail}"
        )

    exception_map = contract.get("exception_map") or {}
    results = [
        {
            "case_index": index,
            # 程序没跑到这条用例时 payload 缺失，给 None 让面板自己隐藏这个
            # 徽标，而不是显示一个假的 0ms。
            "duration_ms": _payload_duration_ms(payloads.get(index)),
            **_compare_case(
                item, payloads.get(index), exception_map, index in duplicated
            ),
        }
        for index, item in enumerate(cases, start=1)
    ]
    passed_count = sum(1 for item in results if item["passed"])
    return {
        "passed": bool(results) and passed_count == len(results),
        "total": len(results), "passed_count": passed_count,
        "compile_error": None, "results": results,
        "execution_time": round(time.perf_counter() - started, 3),
        "judge_mode": "server_private_cases",
    }
