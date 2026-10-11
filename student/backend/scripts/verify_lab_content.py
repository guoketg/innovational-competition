"""校验 13 个编程实验室关卡的私有判题用例与对应参考答案是否自洽。

用法（在 student/backend 目录下）：
    python scripts/verify_lab_content.py               # 13 关正课 + 10 关变式
    python scripts/verify_lab_content.py --variants    # 只校验变式迁移

每道关卡都有一份参考答案，脚本把它当作学生代码提交给 judge_submission，
必须 13 关全部通过，才说明题目契约、隐藏用例与判题链路三者一致。
「变式迁移」另有一组参考答案，走服务端真实的 _judge_variant_code 判题入口。

沙箱提示：judge 的 RUNNER 只暴露 SAFE_BUILTINS 白名单，
reversed / map / filter / divmod 等都不在其中，参考答案因此不使用它们；
变式沙箱同样禁止 import collections，且不允许模块级变量引用函数对象。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ══════════════════════════════════════════════════════════════
#  阶段一：线性结构与基础容器
# ══════════════════════════════════════════════════════════════

REF_1_1 = '''
#include <vector>
#include <stdexcept>
#include <string>

std::vector<int> array_insert(std::vector<int> items, int index, int value) {
  if (index < 0 || index > static_cast<int>(items.size())) {
    throw std::out_of_range("index 越界：合法范围是 0..size()");
  }
  std::vector<int> result = items;
  result.insert(result.begin() + index, value);
  return result;
}
'''

REF_1_2 = '''
Node* reverse_list(Node* head) {
  Node* prev = nullptr;
  Node* node = head;
  while (node) {
    prev = new Node{node->value, prev};
    node = node->next;
  }
  return prev;
}
'''

REF_1_3 = '''
#include <vector>
#include <string>
#include <stdexcept>

int eval_rpn(std::vector<std::string> tokens) {
  std::vector<int> stack;
  for (const std::string& token : tokens) {
    if (token == "+" || token == "-" || token == "*" || token == "/") {
      if (stack.size() < 2) throw std::invalid_argument("操作数不足");
      int right = stack.back(); stack.pop_back();
      int left = stack.back(); stack.pop_back();
      if (token == "+") stack.push_back(left + right);
      else if (token == "-") stack.push_back(left - right);
      else if (token == "*") stack.push_back(left * right);
      else {
        if (right == 0) throw std::invalid_argument("除数不能为 0");
        stack.push_back(left / right);
      }
    } else {
      std::size_t pos = 0;
      int value;
      try {
        value = std::stoi(token, &pos);
      } catch (const std::exception&) {
        throw std::invalid_argument("非法数字 token");
      }
      if (pos != token.size()) throw std::invalid_argument("非法数字 token");
      stack.push_back(value);
    }
  }
  if (stack.size() != 1) throw std::invalid_argument("表达式非法");
  return stack[0];
}
'''


# ══════════════════════════════════════════════════════════════
#  阶段二：树与堆
# ══════════════════════════════════════════════════════════════

_BST_HELPERS = '''
def _validate_tree(tree):
    if tree is None:
        return []
    if not isinstance(tree, list) or len(tree) != 3:
        raise ValueError("节点必须是长度为 3 的列表")
    value = tree[0]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("节点值必须是非布尔整数")
    return _validate_tree(tree[1]) + [value] + _validate_tree(tree[2])


def _check_bst(tree):
    values = _validate_tree(tree)
    for i in range(1, len(values)):
        if values[i] <= values[i - 1]:
            raise ValueError("不满足二分搜索树性质")
    return values


def _validate_value(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("值必须是非布尔整数")
'''

REF_2_1 = '''
#include <stdexcept>

static bool bst_check(const TreeNode* node, const TreeNode*& prev) {
  if (!node) return true;
  if (!bst_check(node->left, prev)) return false;
  if (prev && prev->value >= node->value) return false;
  prev = node;
  return bst_check(node->right, prev);
}

static void validate_bst(const TreeNode* root) {
  const TreeNode* prev = nullptr;
  if (!bst_check(root, prev)) throw std::invalid_argument("不满足二分搜索树性质");
}

TreeNode* bst_insert(TreeNode* root, int value) {
  validate_bst(root);
  if (!root) return new TreeNode{value, nullptr, nullptr};
  if (value == root->value) throw std::invalid_argument("二分搜索树不允许重复值");
  if (value < root->value) {
    return new TreeNode{root->value, bst_insert(root->left, value), root->right};
  }
  return new TreeNode{root->value, root->left, bst_insert(root->right, value)};
}

bool bst_search(TreeNode* root, int value) {
  validate_bst(root);
  const TreeNode* node = root;
  while (node) {
    if (value == node->value) return true;
    node = value < node->value ? node->left : node->right;
  }
  return false;
}
'''

REF_2_2 = '''
#include <vector>

static void inorder_walk(const TreeNode* node, std::vector<int>& result) {
  if (!node) return;
  inorder_walk(node->left, result);
  result.push_back(node->value);
  inorder_walk(node->right, result);
}

std::vector<int> bst_inorder(TreeNode* root) {
  std::vector<int> result;
  inorder_walk(root, result);
  return result;
}

std::vector<std::vector<int>> bst_level_order(TreeNode* root) {
  std::vector<std::vector<int>> levels;
  if (!root) return levels;
  std::vector<TreeNode*> current{root};
  while (!current.empty()) {
    std::vector<int> values;
    std::vector<TreeNode*> next;
    for (TreeNode* node : current) {
      values.push_back(node->value);
      if (node->left) next.push_back(node->left);
      if (node->right) next.push_back(node->right);
    }
    levels.push_back(values);
    current = next;
  }
  return levels;
}
'''

_HEAP_HELPERS = '''
def _validate_heap(heap):
    if not isinstance(heap, list):
        raise ValueError("heap 必须是列表")
    for item in heap:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError("堆元素必须是非布尔整数")


def _validate_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + " 必须是整数")


def _sift_down(heap, index, size):
    while True:
        left = 2 * index + 1
        right = 2 * index + 2
        largest = index
        if left < size and heap[left] > heap[largest]:
            largest = left
        if right < size and heap[right] > heap[largest]:
            largest = right
        if largest == index:
            break
        heap[index], heap[largest] = heap[largest], heap[index]
        index = largest
'''

REF_2_3 = '''
#include <vector>
#include <stdexcept>

static void sift_down(std::vector<int>& heap, int index, int size) {
  while (true) {
    int left = 2 * index + 1;
    int right = 2 * index + 2;
    int largest = index;
    if (left < size && heap[left] > heap[largest]) largest = left;
    if (right < size && heap[right] > heap[largest]) largest = right;
    if (largest == index) break;
    int tmp = heap[index]; heap[index] = heap[largest]; heap[largest] = tmp;
    index = largest;
  }
}

std::vector<int> heap_shift_up(std::vector<int> heap, int index) {
  if (index < 0 || index >= static_cast<int>(heap.size())) throw std::invalid_argument("index 越界");
  std::vector<int> result = heap;
  while (index > 0) {
    int parent = (index - 1) / 2;
    if (result[parent] >= result[index]) break;
    int tmp = result[parent]; result[parent] = result[index]; result[index] = tmp;
    index = parent;
  }
  return result;
}

std::vector<int> heap_shift_down(std::vector<int> heap, int index, int size) {
  if (size <= 0 || size > static_cast<int>(heap.size())) throw std::invalid_argument("size 越界");
  if (index < 0 || index >= size) throw std::invalid_argument("index 越界");
  std::vector<int> result = heap;
  sift_down(result, index, size);
  return result;
}
'''

REF_2_4 = '''
#include <vector>

static void sift_down(std::vector<int>& heap, int index, int size) {
  while (true) {
    int left = 2 * index + 1;
    int right = 2 * index + 2;
    int largest = index;
    if (left < size && heap[left] > heap[largest]) largest = left;
    if (right < size && heap[right] > heap[largest]) largest = right;
    if (largest == index) break;
    int tmp = heap[index]; heap[index] = heap[largest]; heap[largest] = tmp;
    index = largest;
  }
}

std::vector<int> heap_sort(std::vector<int> items) {
  std::vector<int> result = items;
  int total = static_cast<int>(result.size());
  for (int start = total / 2 - 1; start >= 0; --start) {
    sift_down(result, start, total);
  }
  for (int end = total - 1; end > 0; --end) {
    int tmp = result[0]; result[0] = result[end]; result[end] = tmp;
    sift_down(result, 0, end);
  }
  return result;
}
'''


# ══════════════════════════════════════════════════════════════
#  阶段三：图与并查集
# ══════════════════════════════════════════════════════════════

_GRAPH_HELPERS = '''
def _validate_graph(node_count, edges):
    if isinstance(node_count, bool) or not isinstance(node_count, int):
        raise ValueError("节点数必须是整数")
    if node_count <= 0:
        raise ValueError("节点数必须是正整数")
    if not isinstance(edges, list):
        raise ValueError("edges 必须是列表")
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("每条边必须是长度为 2 的列表")
        left, right = edge
        for node in (left, right):
            if isinstance(node, bool) or not isinstance(node, int):
                raise ValueError("端点必须是整数")
            if node < 0 or node >= node_count:
                raise ValueError("端点越界")
        if left == right:
            raise ValueError("不允许自环")
'''

REF_3_1 = '''
#include <vector>
#include <stdexcept>
#include <algorithm>

static void validate_graph(int node_count, const std::vector<std::vector<int>>& edges) {
  if (node_count <= 0) throw std::invalid_argument("节点数必须是正整数");
  for (const auto& edge : edges) {
    if (edge.size() != 2) throw std::invalid_argument("每条边必须是长度为 2 的容器");
    int left = edge[0], right = edge[1];
    if (left < 0 || left >= node_count || right < 0 || right >= node_count) throw std::invalid_argument("端点越界");
    if (left == right) throw std::invalid_argument("不允许自环");
  }
}

std::vector<std::vector<int>> build_adjacency(int node_count, std::vector<std::vector<int>> edges) {
  validate_graph(node_count, edges);
  std::vector<std::vector<int>> adjacency(node_count);
  for (const auto& edge : edges) {
    int left = edge[0], right = edge[1];
    if (std::find(adjacency[left].begin(), adjacency[left].end(), right) == adjacency[left].end()) {
      adjacency[left].push_back(right);
    }
    if (std::find(adjacency[right].begin(), adjacency[right].end(), left) == adjacency[right].end()) {
      adjacency[right].push_back(left);
    }
  }
  for (auto& neighbors : adjacency) std::sort(neighbors.begin(), neighbors.end());
  return adjacency;
}

static void dfs_visit(int node, const std::vector<std::vector<int>>& adjacency,
                      std::vector<bool>& visited, std::vector<int>& order) {
  visited[node] = true;
  order.push_back(node);
  for (int next : adjacency[node]) {
    if (!visited[next]) dfs_visit(next, adjacency, visited, order);
  }
}

std::vector<int> dfs_order(std::vector<std::vector<int>> adjacency, int start) {
  if (start < 0 || start >= static_cast<int>(adjacency.size())) throw std::invalid_argument("起点越界");
  std::vector<bool> visited(adjacency.size(), false);
  std::vector<int> order;
  dfs_visit(start, adjacency, visited, order);
  return order;
}
'''

_UF_HELPERS = '''
def _validate_parent(parent):
    if not isinstance(parent, list):
        raise ValueError("parent 必须是列表")
    for value in parent:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("parent 元素必须是整数")


def _validate_node(parent, node):
    if isinstance(node, bool) or not isinstance(node, int):
        raise ValueError("节点必须是整数")
    if node < 0 or node >= len(parent):
        raise ValueError("节点越界")
'''

REF_3_2 = '''
#include <vector>
#include <stdexcept>

int uf_find_root(std::vector<int> parent, int x) {
  if (x < 0 || x >= static_cast<int>(parent.size())) throw std::invalid_argument("节点越界");
  while (parent[x] != x) x = parent[x];
  return x;
}

std::vector<int> uf_compress(std::vector<int> parent, int x) {
  if (x < 0 || x >= static_cast<int>(parent.size())) throw std::invalid_argument("节点越界");
  int root = x;
  while (parent[root] != root) root = parent[root];
  std::vector<int> result = parent;
  int cursor = x;
  while (result[cursor] != root) {
    int nxt = result[cursor];
    result[cursor] = root;
    cursor = nxt;
  }
  return result;
}

int count_components(int node_count, std::vector<std::vector<int>> edges) {
  if (node_count <= 0) throw std::invalid_argument("节点数必须是正整数");
  std::vector<int> parent(node_count);
  std::vector<int> sizes(node_count, 1);
  for (int i = 0; i < node_count; ++i) parent[i] = i;
  for (const auto& edge : edges) {
    if (edge.size() != 2) throw std::invalid_argument("每条边必须是长度为 2 的容器");
    int left = edge[0], right = edge[1];
    if (left < 0 || left >= node_count || right < 0 || right >= node_count) throw std::invalid_argument("端点越界");
    if (left == right) throw std::invalid_argument("不允许自环");
    int root_left = left, root_right = right;
    while (parent[root_left] != root_left) root_left = parent[root_left];
    while (parent[root_right] != root_right) root_right = parent[root_right];
    if (root_left == root_right) continue;
    if (sizes[root_left] < sizes[root_right]) {
      int tmp = root_left; root_left = root_right; root_right = tmp;
    }
    parent[root_right] = root_left;
    sizes[root_left] += sizes[root_right];
  }
  int roots = 0;
  for (int node = 0; node < node_count; ++node) {
    if (parent[node] == node) ++roots;
  }
  return roots;
}
'''

REF_3_3 = '''
#include <vector>
#include <stdexcept>
#include <algorithm>
#include <queue>

static void validate_graph(int node_count, const std::vector<std::vector<int>>& edges) {
  if (node_count <= 0) throw std::invalid_argument("节点数必须是正整数");
  for (const auto& edge : edges) {
    if (edge.size() != 2) throw std::invalid_argument("每条边必须是长度为 2 的容器");
    int left = edge[0], right = edge[1];
    if (left < 0 || left >= node_count || right < 0 || right >= node_count) throw std::invalid_argument("端点越界");
    if (left == right) throw std::invalid_argument("不允许自环");
  }
}

static std::vector<std::vector<int>> build_adjacency(int node_count, const std::vector<std::vector<int>>& edges) {
  std::vector<std::vector<int>> adjacency(node_count);
  for (const auto& edge : edges) {
    int left = edge[0], right = edge[1];
    if (std::find(adjacency[left].begin(), adjacency[left].end(), right) == adjacency[left].end()) adjacency[left].push_back(right);
    if (std::find(adjacency[right].begin(), adjacency[right].end(), left) == adjacency[right].end()) adjacency[right].push_back(left);
  }
  for (auto& neighbors : adjacency) std::sort(neighbors.begin(), neighbors.end());
  return adjacency;
}

std::vector<int> bfs_shortest_path(std::vector<std::vector<int>> edges, int node_count, int start, int end) {
  validate_graph(node_count, edges);
  if (start < 0 || start >= node_count) throw std::invalid_argument("起点越界");
  if (end < 0 || end >= node_count) throw std::invalid_argument("终点越界");
  if (start == end) return {start};
  auto adjacency = build_adjacency(node_count, edges);
  std::vector<int> previous(node_count, -1);
  std::vector<bool> visited(node_count, false);
  std::queue<int> queue;
  queue.push(start);
  visited[start] = true;
  while (!queue.empty()) {
    int node = queue.front(); queue.pop();
    for (int neighbor : adjacency[node]) {
      if (visited[neighbor]) continue;
      visited[neighbor] = true;
      previous[neighbor] = node;
      if (neighbor == end) {
        std::vector<int> path;
        for (int cur = end; cur != -1; cur = previous[cur]) path.push_back(cur);
        std::reverse(path.begin(), path.end());
        return path;
      }
      queue.push(neighbor);
    }
  }
  return {};
}
'''


# ══════════════════════════════════════════════════════════════
#  阶段四：算法工具箱工程化
# ══════════════════════════════════════════════════════════════

REF_4_1 = '''
#include <vector>
#include <string>
#include <stdexcept>
#include <functional>
#include <map>
#include <algorithm>

static std::map<std::string, std::function<std::vector<int>(const std::vector<int>&)>> make_registry() {
  std::map<std::string, std::function<std::vector<int>(const std::vector<int>&)>> registry;
  registry["sort"] = [](const std::vector<int>& data) {
    std::vector<int> result = data;
    std::sort(result.begin(), result.end());
    return result;
  };
  registry["reverse"] = [](const std::vector<int>& data) {
    std::vector<int> result = data;
    std::reverse(result.begin(), result.end());
    return result;
  };
  registry["dedup"] = [](const std::vector<int>& data) {
    std::vector<int> result;
    for (int value : data) {
      if (std::find(result.begin(), result.end(), value) == result.end()) result.push_back(value);
    }
    return result;
  };
  return registry;
}

std::vector<std::string> describe_toolbox() {
  auto registry = make_registry();
  std::vector<std::string> names;
  for (const auto& entry : registry) names.push_back(entry.first);
  return names;
}

std::vector<int> toolbox_call(std::string name, std::vector<int> data) {
  auto registry = make_registry();
  auto it = registry.find(name);
  if (it == registry.end()) throw std::invalid_argument("工具箱中没有这个操作：" + name);
  return it->second(data);
}
'''

_INT_LIST_HELPER = '''
def _validate_int_list(items, label):
    if not isinstance(items, list):
        raise ValueError(label + " 必须是列表")
    for item in items:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError("元素必须是非布尔整数")
'''

REF_4_2 = '''
#include <vector>
#include <stdexcept>

std::vector<int> merge_sorted(std::vector<int> left, std::vector<int> right) {
  for (size_t i = 1; i < left.size(); ++i) if (left[i] < left[i - 1]) throw std::invalid_argument("输入必须各自有序");
  for (size_t i = 1; i < right.size(); ++i) if (right[i] < right[i - 1]) throw std::invalid_argument("输入必须各自有序");
  std::vector<int> merged;
  size_t i = 0, j = 0;
  while (i < left.size() && j < right.size()) {
    if (left[i] <= right[j]) merged.push_back(left[i++]);
    else merged.push_back(right[j++]);
  }
  while (i < left.size()) merged.push_back(left[i++]);
  while (j < right.size()) merged.push_back(right[j++]);
  return merged;
}

std::vector<int> merge_sort(std::vector<int> items) {
  if (items.size() <= 1) return items;
  size_t middle = items.size() / 2;
  std::vector<int> left(items.begin(), items.begin() + middle);
  std::vector<int> right(items.begin() + middle, items.end());
  return merge_sorted(merge_sort(left), merge_sort(right));
}

bool is_sorted_ascending(std::vector<int> items) {
  for (size_t i = 1; i < items.size(); ++i) {
    if (items[i] < items[i - 1]) return false;
  }
  return true;
}
'''

REF_4_3 = '''
#include <vector>
#include <stdexcept>
#include <unordered_map>
#include <list>
#include <iterator>

std::vector<int> lru_simulate(int capacity, std::vector<std::vector<int>> operations) {
  if (capacity <= 0) throw std::invalid_argument("capacity 必须为正整数");
  std::unordered_map<int, std::pair<int, std::list<int>::iterator>> cache;
  std::list<int> order;  // 最久未使用在前，最新在后
  std::vector<int> results;
  for (const auto& op : operations) {
    if (op.empty()) throw std::invalid_argument("操作不能为空");
    if (op[0] == 0) {  // get(key)
      if (op.size() != 2) throw std::invalid_argument("get 操作需要一个键");
      int key = op[1];
      auto it = cache.find(key);
      if (it == cache.end()) {
        results.push_back(-1);
      } else {
        int value = it->second.first;
        order.erase(it->second.second);
        order.push_back(key);
        it->second.second = std::prev(order.end());
        results.push_back(value);
      }
    } else if (op[0] == 1) {  // put(key, value)
      if (op.size() != 3) throw std::invalid_argument("put 操作需要键和值");
      int key = op[1], value = op[2];
      auto it = cache.find(key);
      if (it != cache.end()) order.erase(it->second.second);
      order.push_back(key);
      cache[key] = {value, std::prev(order.end())};
      if (static_cast<int>(order.size()) > capacity) {
        int oldest = order.front();
        order.pop_front();
        cache.erase(oldest);
      }
    } else {
      throw std::invalid_argument("未知操作码");
    }
  }
  return results;
}

std::vector<int> two_sum(std::vector<int> nums, int target) {
  std::unordered_map<int, int> seen;
  for (int i = 0; i < static_cast<int>(nums.size()); ++i) {
    int need = target - nums[i];
    auto it = seen.find(need);
    if (it != seen.end()) return {it->second, i};
    if (seen.find(nums[i]) == seen.end()) seen[nums[i]] = i;
  }
  return {};
}
'''


# ══════════════════════════════════════════════════════════════
#  变式迁移参考答案（1-1 ~ 4-3）
#  走 _judge_variant_code，沙箱同样只有 SAFE_BUILTINS 白名单。
# ══════════════════════════════════════════════════════════════

REF_V_1_1 = '''
#include <vector>
#include <stdexcept>
#include <string>

std::vector<std::vector<int>> insert_interval(
    std::vector<std::vector<int>> intervals, std::vector<int> new_interval) {
  // 先整体校验，再合并：两条非法用例分别考「新日程非法」与「已有日程非法」，
  // 所以两边都要过一遍。
  auto validate = [](const std::vector<int>& item) {
    if (item.size() != 2) throw std::invalid_argument("区间必须是长度为 2 的容器");
    if (item[0] > item[1]) throw std::invalid_argument("区间起点不能大于终点");
  };
  for (const auto& item : intervals) validate(item);
  validate(new_interval);

  // 按 start 插进有序表；start 相同时插在后面也无妨——它们必然重叠，会合并。
  std::vector<std::vector<int>> ordered;
  bool placed = false;
  for (const auto& item : intervals) {
    if (!placed && new_interval[0] < item[0]) {
      ordered.push_back(new_interval);
      placed = true;
    }
    ordered.push_back(item);
  }
  if (!placed) ordered.push_back(new_interval);

  // 从左往右合并相邻区间：后一个的 start 小于等于前一个的 end 就并（端点相接也算）。
  std::vector<std::vector<int>> merged;
  for (const auto& interval : ordered) {
    if (!merged.empty() && interval[0] <= merged.back()[1]) {
      if (interval[1] > merged.back()[1]) merged.back()[1] = interval[1];
    } else {
      merged.push_back(interval);
    }
  }
  return merged;
}
'''

REF_V_1_2 = '''
#include <stdexcept>

// 校验一条链按 value 非降序，返回链长。
static int check_chain(const Node* head) {
  int length = 0;
  bool has_previous = false;
  int previous = 0;
  for (const Node* node = head; node; node = node->next) {
    if (has_previous && node->value < previous) {
      throw std::invalid_argument("链表必须按值非降序");
    }
    previous = node->value;
    has_previous = true;
    ++length;
  }
  return length;
}

Node* merge_two_lists(Node* a, Node* b) {
  check_chain(a);
  check_chain(b);

  Node dummy{0, nullptr};
  Node* tail = &dummy;
  Node* p = a;
  Node* q = b;
  while (p && q) {
    if (p->value <= q->value) {
      tail->next = new Node{p->value, nullptr};
      p = p->next;
    } else {
      tail->next = new Node{q->value, nullptr};
      q = q->next;
    }
    tail = tail->next;
  }
  while (p) {
    tail->next = new Node{p->value, nullptr};
    tail = tail->next;
    p = p->next;
  }
  while (q) {
    tail->next = new Node{q->value, nullptr};
    tail = tail->next;
    q = q->next;
  }
  return dummy.next;
}
'''

REF_V_1_3 = '''
#include <vector>
#include <stdexcept>
#include <cmath>

std::vector<double> moving_average(int window, std::vector<double> events) {
  if (window < 1) throw std::invalid_argument("window 必须不小于 1");
  std::vector<double> result;
  std::vector<double> current;
  double total = 0.0;
  for (double event : events) {
    current.push_back(event);
    total += event;
    if (static_cast<int>(current.size()) > window) {
      total -= current.front();
      current.erase(current.begin());
    }
    result.push_back(std::round(total / current.size() * 1000.0) / 1000.0);
  }
  return result;
}
'''

_V_BST_VALIDATOR = '''
def _validate_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + " 必须是非布尔整数")


def _check_bst(tree):
    """校验节点结构并返回中序序列（升序才满足 BST 性质）。"""
    values = []

    def walk(node):
        if node is None:
            return
        if not isinstance(node, list) or len(node) != 3:
            raise ValueError("节点必须是长度为 3 的列表")
        value = node[0]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("节点值必须是非布尔整数")
        walk(node[1])
        values.append(value)
        walk(node[2])

    walk(tree)
    for i in range(1, len(values)):
        if values[i] <= values[i - 1]:
            raise ValueError("不满足二分搜索树性质")
    return values
'''

REF_V_2_1 = '''
#include <vector>
#include <stdexcept>

static bool bst_check(const TreeNode* node, const TreeNode*& prev) {
  if (!node) return true;
  if (!bst_check(node->left, prev)) return false;
  if (prev && prev->value >= node->value) return false;
  prev = node;
  return bst_check(node->right, prev);
}

static void range_walk(const TreeNode* node, int low, int high, std::vector<int>& result) {
  if (!node) return;
  if (node->value > low) range_walk(node->left, low, high, result);
  if (low <= node->value && node->value <= high) result.push_back(node->value);
  if (node->value < high) range_walk(node->right, low, high, result);
}

std::vector<int> bst_range_values(TreeNode* tree, int low, int high) {
  if (low > high) throw std::invalid_argument("low 不能大于 high");
  const TreeNode* prev = nullptr;
  if (!bst_check(tree, prev)) throw std::invalid_argument("不满足二分搜索树性质");
  std::vector<int> result;
  range_walk(tree, low, high, result);
  return result;
}
'''

REF_V_2_2 = '''
#include <vector>
#include <algorithm>

std::vector<std::vector<int>> bst_reverse_level_order(TreeNode* tree) {
  std::vector<std::vector<int>> levels;
  if (!tree) return levels;
  std::vector<TreeNode*> current{tree};
  while (!current.empty()) {
    std::vector<int> values;
    std::vector<TreeNode*> next;
    for (TreeNode* node : current) {
      values.push_back(node->value);
      if (node->left) next.push_back(node->left);
      if (node->right) next.push_back(node->right);
    }
    levels.push_back(values);
    current = next;
  }
  std::reverse(levels.begin(), levels.end());
  return levels;
}
'''

REF_V_2_3 = '''
#include <vector>

static void sift_down(std::vector<int>& heap, int index, int size) {
  while (true) {
    int left = 2 * index + 1;
    int right = 2 * index + 2;
    int largest = index;
    if (left < size && heap[left] > heap[largest]) largest = left;
    if (right < size && heap[right] > heap[largest]) largest = right;
    if (largest == index) break;
    int tmp = heap[index]; heap[index] = heap[largest]; heap[largest] = tmp;
    index = largest;
  }
}

std::vector<int> heap_build(std::vector<int> items) {
  std::vector<int> result = items;
  int total = static_cast<int>(result.size());
  for (int start = total / 2 - 1; start >= 0; --start) {
    sift_down(result, start, total);
  }
  return result;
}
'''

REF_V_2_4 = '''
#include <vector>
#include <stdexcept>

static void sift_down(std::vector<int>& heap, int index, int size) {
  while (true) {
    int left = 2 * index + 1;
    int right = 2 * index + 2;
    int largest = index;
    if (left < size && heap[left] > heap[largest]) largest = left;
    if (right < size && heap[right] > heap[largest]) largest = right;
    if (largest == index) break;
    int tmp = heap[index]; heap[index] = heap[largest]; heap[largest] = tmp;
    index = largest;
  }
}

std::vector<int> k_largest(std::vector<int> items, int k) {
  if (k <= 0 || k > static_cast<int>(items.size())) throw std::invalid_argument("k 必须落在 1..size 之间");
  std::vector<int> heap = items;
  int total = static_cast<int>(heap.size());
  for (int start = total / 2 - 1; start >= 0; --start) sift_down(heap, start, total);
  std::vector<int> result;
  int size = total;
  for (int i = 0; i < k; ++i) {
    result.push_back(heap[0]);
    --size;
    heap[0] = heap[size];
    sift_down(heap, 0, size);
  }
  return result;
}
'''

_V_GRAPH_VALIDATOR = '''
def _validate_graph(edges, node_count):
    if isinstance(node_count, bool) or not isinstance(node_count, int):
        raise ValueError("节点数必须是整数")
    if node_count <= 0:
        raise ValueError("节点数必须是正整数")
    if not isinstance(edges, list):
        raise ValueError("edges 必须是列表")
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("每条边必须是长度为 2 的列表")
        left, right = edge
        for node in (left, right):
            if isinstance(node, bool) or not isinstance(node, int):
                raise ValueError("端点必须是整数")
            if node < 0 or node >= node_count:
                raise ValueError("端点越界")
        if left == right:
            raise ValueError("不允许自环")
'''

REF_V_3_1 = '''
#include <vector>
#include <stdexcept>
#include <algorithm>

static int find_root(std::vector<int>& parent, int node) {
  int root = node;
  while (parent[root] != root) root = parent[root];
  while (parent[node] != root) {
    int nxt = parent[node];
    parent[node] = root;
    node = nxt;
  }
  return root;
}

static void validate_graph(const std::vector<std::vector<int>>& edges, int node_count) {
  if (node_count <= 0) throw std::invalid_argument("节点数必须是正整数");
  for (const auto& edge : edges) {
    if (edge.size() != 2) throw std::invalid_argument("每条边必须是长度为 2 的容器");
    int left = edge[0], right = edge[1];
    if (left < 0 || left >= node_count || right < 0 || right >= node_count) throw std::invalid_argument("端点越界");
    if (left == right) throw std::invalid_argument("不允许自环");
  }
}

bool has_cycle(std::vector<std::vector<int>> edges, int node_count) {
  validate_graph(edges, node_count);
  std::vector<int> parent(node_count);
  for (int i = 0; i < node_count; ++i) parent[i] = i;
  std::vector<std::pair<int, int>> seen;
  for (const auto& edge : edges) {
    int left = edge[0], right = edge[1];
    int low = left < right ? left : right;
    int high = left < right ? right : left;
    auto key = std::make_pair(low, high);
    if (std::find(seen.begin(), seen.end(), key) != seen.end()) continue;
    seen.push_back(key);
    int rl = find_root(parent, left);
    int rr = find_root(parent, right);
    if (rl == rr) return true;
    parent[rr] = rl;
  }
  return false;
}
'''

REF_V_3_2 = '''
#include <vector>
#include <stdexcept>

static int find_root(std::vector<int>& parent, int node) {
  while (parent[node] != node) {
    parent[node] = parent[parent[node]];
    node = parent[node];
  }
  return node;
}

int count_provinces(std::vector<std::vector<int>> matrix) {
  int size = static_cast<int>(matrix.size());
  if (size == 0) throw std::invalid_argument("矩阵不能为空");
  for (const auto& row : matrix) {
    if (static_cast<int>(row.size()) != size) throw std::invalid_argument("矩阵必须是 n x n 的方阵");
    for (int value : row) {
      if (value != 0 && value != 1) throw std::invalid_argument("矩阵元素只能是 0 或 1");
    }
  }
  for (int i = 0; i < size; ++i) {
    if (matrix[i][i] != 1) throw std::invalid_argument("对角线必须为 1");
    for (int j = 0; j < size; ++j) {
      if (matrix[i][j] != matrix[j][i]) throw std::invalid_argument("矩阵必须是对称的");
    }
  }
  std::vector<int> parent(size);
  for (int i = 0; i < size; ++i) parent[i] = i;
  for (int i = 0; i < size; ++i) {
    for (int j = i + 1; j < size; ++j) {
      if (matrix[i][j] == 1) {
        int left = find_root(parent, i);
        int right = find_root(parent, j);
        if (left != right) parent[right] = left;
      }
    }
  }
  int roots = 0;
  for (int node = 0; node < size; ++node) {
    if (find_root(parent, node) == node) ++roots;
  }
  return roots;
}
'''

REF_V_3_3 = '''
#include <vector>
#include <stdexcept>
#include <algorithm>
#include <queue>

static void validate_graph(const std::vector<std::vector<int>>& edges, int node_count) {
  if (node_count <= 0) throw std::invalid_argument("节点数必须是正整数");
  for (const auto& edge : edges) {
    if (edge.size() != 2) throw std::invalid_argument("每条边必须是长度为 2 的容器");
    int left = edge[0], right = edge[1];
    if (left < 0 || left >= node_count || right < 0 || right >= node_count) throw std::invalid_argument("端点越界");
    if (left == right) throw std::invalid_argument("不允许自环");
  }
}

std::vector<int> bfs_all_distances(std::vector<std::vector<int>> edges, int node_count, int start) {
  validate_graph(edges, node_count);
  if (start < 0 || start >= node_count) throw std::invalid_argument("起点越界");
  std::vector<std::vector<int>> adjacency(node_count);
  for (const auto& edge : edges) {
    int left = edge[0], right = edge[1];
    if (std::find(adjacency[left].begin(), adjacency[left].end(), right) == adjacency[left].end()) adjacency[left].push_back(right);
    if (std::find(adjacency[right].begin(), adjacency[right].end(), left) == adjacency[right].end()) adjacency[right].push_back(left);
  }
  std::vector<int> distances(node_count, -1);
  distances[start] = 0;
  std::queue<int> queue;
  queue.push(start);
  while (!queue.empty()) {
    int node = queue.front(); queue.pop();
    for (int neighbor : adjacency[node]) {
      if (distances[neighbor] != -1) continue;
      distances[neighbor] = distances[node] + 1;
      queue.push(neighbor);
    }
  }
  return distances;
}
'''

REF_V_4_1 = '''
#include <vector>
#include <string>
#include <stdexcept>
#include <functional>
#include <map>
#include <algorithm>

static std::map<std::string, std::function<std::vector<int>(const std::vector<int>&)>> make_registry() {
  std::map<std::string, std::function<std::vector<int>(const std::vector<int>&)>> registry;
  registry["sort"] = [](const std::vector<int>& data) {
    std::vector<int> result = data;
    std::sort(result.begin(), result.end());
    return result;
  };
  registry["reverse"] = [](const std::vector<int>& data) {
    std::vector<int> result = data;
    std::reverse(result.begin(), result.end());
    return result;
  };
  registry["dedup"] = [](const std::vector<int>& data) {
    std::vector<int> result;
    for (int value : data) {
      if (std::find(result.begin(), result.end(), value) == result.end()) result.push_back(value);
    }
    return result;
  };
  return registry;
}

std::vector<std::vector<int>> toolbox_call_many(std::vector<std::string> names, std::vector<std::vector<int>> datas) {
  if (names.size() != datas.size()) throw std::invalid_argument("names 与 datas 长度不一致");
  auto registry = make_registry();
  for (const auto& name : names) {
    if (registry.find(name) == registry.end()) throw std::invalid_argument("工具箱中没有这个操作：" + name);
  }
  std::vector<std::vector<int>> results;
  for (size_t i = 0; i < names.size(); ++i) {
    results.push_back(registry[names[i]](datas[i]));
  }
  return results;
}
'''

REF_V_4_2 = '''
#include <vector>
#include <utility>

static std::pair<std::vector<int>, int> sort_and_count(std::vector<int> values) {
  if (values.size() <= 1) return {values, 0};
  size_t middle = values.size() / 2;
  std::vector<int> left(values.begin(), values.begin() + middle);
  std::vector<int> right(values.begin() + middle, values.end());
  auto left_pair = sort_and_count(left);
  auto right_pair = sort_and_count(right);
  std::vector<int> merged;
  int count = left_pair.second + right_pair.second;
  size_t i = 0, j = 0;
  while (i < left_pair.first.size() && j < right_pair.first.size()) {
    if (left_pair.first[i] <= right_pair.first[j]) {
      merged.push_back(left_pair.first[i++]);
    } else {
      merged.push_back(right_pair.first[j++]);
      count += static_cast<int>(left_pair.first.size()) - static_cast<int>(i);
    }
  }
  while (i < left_pair.first.size()) merged.push_back(left_pair.first[i++]);
  while (j < right_pair.first.size()) merged.push_back(right_pair.first[j++]);
  return {merged, count};
}

int count_inversions(std::vector<int> items) {
  return sort_and_count(items).second;
}
'''

REF_V_4_3 = '''
#include <vector>
#include <unordered_map>

int subarray_sum_equals_k(std::vector<int> nums, int k) {
  std::unordered_map<int, int> counts;
  counts[0] = 1;
  int prefix = 0;
  int total = 0;
  for (int value : nums) {
    prefix += value;
    auto it = counts.find(prefix - k);
    if (it != counts.end()) total += it->second;
    counts[prefix] += 1;
  }
  return total;
}
'''

VARIANT_REFERENCE_SOLUTIONS = {
    "1-1": REF_V_1_1,
    "1-2": REF_V_1_2,
    "1-3": REF_V_1_3,
    "2-1": REF_V_2_1,
    "2-2": REF_V_2_2,
    "2-3": REF_V_2_3,
    "2-4": REF_V_2_4,
    "3-1": REF_V_3_1,
    "3-2": REF_V_3_2,
    "3-3": REF_V_3_3,
    "4-1": REF_V_4_1,
    "4-2": REF_V_4_2,
    "4-3": REF_V_4_3,
}

# 变式条目沿用与正课一致的排序键（阶段、小节）
VARIANT_IDS = tuple(sorted(VARIANT_REFERENCE_SOLUTIONS, key=lambda item: (item[0], item[2])))


REFERENCE_SOLUTIONS = {
    "1-1": REF_1_1,
    "1-2": REF_1_2,
    "1-3": REF_1_3,
    "2-1": REF_2_1,
    "2-2": REF_2_2,
    "2-3": REF_2_3,
    "2-4": REF_2_4,
    "3-1": REF_3_1,
    "3-2": REF_3_2,
    "3-3": REF_3_3,
    "4-1": REF_4_1,
    "4-2": REF_4_2,
    "4-3": REF_4_3,
}


# ══════════════════════════════════════════════════════════════
#  变式迁移校验：走服务端真实的 _judge_variant_code
# ══════════════════════════════════════════════════════════════

def _load_variant_judge():
    """返回 (判题函数, 说明文本)；导入失败时返回 (None, 原因)。

    capability_service 会连带导入 LLM / 加密 / HTTP 等第三方依赖。这些依赖
    缺失时，本函数**不会**用空壳模块顶替——伪造依赖会让"校验通过"变成一句
    无法验证的话。缺依赖就是没校验，如实报告，由调用方失败退出。
    完整校验请在 backend 容器内运行（依赖齐全）：
        docker exec ai-learning-backend python scripts/verify_lab_content.py
    """
    try:
        from services.capability_service import _judge_variant_code
    except ImportError as exc:
        return None, (f"无法导入 _judge_variant_code：{exc}"
                      "（本机缺少后端依赖，请在 backend 容器内运行本脚本）")
    return _judge_variant_code, "services.capability_service._judge_variant_code（直接导入）"


def run_variant_checks() -> list[str]:
    """逐条用真实判题入口校验变式参考答案，返回未通过的关卡列表。"""
    from services.agent_lab_variants import ADDITIONAL_VARIANT_SPECS

    judge, note = _load_variant_judge()
    print("变式判题入口：" + note)
    if judge is None:
        print(f"变式校验未能执行，按未通过计入 {len(VARIANT_IDS)} 项。")
        return list(VARIANT_IDS)

    missing = [item for item in VARIANT_IDS if item not in ADDITIONAL_VARIANT_SPECS]
    if missing:
        print("缺少变式规格的关卡：" + ", ".join(missing))
        return missing

    failures = []
    for exercise_id in VARIANT_IDS:
        spec = ADDITIONAL_VARIANT_SPECS[exercise_id]
        result = judge(VARIANT_REFERENCE_SOLUTIONS[exercise_id], spec)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] 变式 {exercise_id}  {result['passed_count']}/{result['total']}"
              f"  target={spec['target']}")
        if not result["passed"]:
            failures.append(exercise_id)
            if result.get("compile_error"):
                print("        编译/执行错误：" + str(result["compile_error"]))
            for item in result.get("results", []):
                if not item["passed"]:
                    print(f"        用例 {item['case_index']} 未通过：{item['error']}")
    return failures


def run_sample_checks() -> list[str]:
    """校验 PTA 式自测的公开样例，以及阶段表是否已彻底去终端化。

    三件事必须同时成立，否则自测要么没得跑、要么等于提前交卷：
      1. 每关都有 2–3 条公开样例；
      2. 每关至少还留着一条隐藏用例（公开样例不得覆盖全部考点）；
      3. 参考答案跑公开样例同样全过——样例与判题口径一致，学生照题面自测
         不会因为样例本身写错而被误导。
    """
    from services.agent_lab_specs import SPECS
    from services.judge_service import judge_samples, public_cases

    failures = []
    print("─" * 62)
    print("自测样例校验（public_cases / judge_samples）")
    for exercise_id in sorted(SPECS, key=lambda item: (item[0], item[2])):
        samples = public_cases(exercise_id)
        total = len(SPECS[exercise_id].get("cases") or [])
        hidden = total - len(samples)
        problems = []
        if not 2 <= len(samples) <= 3:
            problems.append(f"公开样例 {len(samples)} 条，应为 2–3 条")
        if hidden <= 0:
            problems.append("没有隐藏用例，自测等于提前交卷")

        judged = judge_samples(exercise_id, REFERENCE_SOLUTIONS[exercise_id])
        if not judged["passed"]:
            problems.append(
                f"参考答案未通过公开样例（{judged['passed_count']}/{judged['total']}）"
                + (f"：{judged['compile_error']}" if judged.get("compile_error") else "")
            )

        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {exercise_id}  公开 {len(samples)}  隐藏 {hidden}")
        for problem in problems:
            print("        " + problem)
        if problems:
            failures.append(f"{exercise_id}(自测样例)")
    return failures


def run_stage_checks() -> list[str]:
    """校验 13 关阶段表已去终端化：单文件项目，无工程化阶段与终端文案。"""
    from services.agent_lab_specs import lab_solution_file
    from services.judge_service import load_flagship_exercises
    from services.lab_workspace_service import _course

    banned_in_text = ("终端", "pip install", ".venv", "requirements.txt")
    failures = []
    print("─" * 62)
    print("阶段表校验（单文件 / 去终端化）")
    for exercise in load_flagship_exercises():
        exercise_id = str(exercise["id"])
        course = _course(exercise_id)
        stage_ids = [item["id"] for item in course["stages"]]
        problems = []
        expected_files = [lab_solution_file(exercise_id)]
        if course["project_files"] != expected_files:
            problems.append(f"project_files = {course['project_files']}，应为 {expected_files}")
        for removed in ("environment", "dependencies", "integration"):
            if removed in stage_ids:
                problems.append(f"仍保留工程化阶段 {removed}")
        for stage in course["stages"]:
            blob = " ".join([
                str(stage.get("instruction", "")),
                str(stage.get("command", "")),
                *[str(item) for item in stage.get("checks", [])],
                *[str(item.get("text", "")) for item in stage.get("hints", [])],
            ])
            for word in banned_in_text:
                if word in blob:
                    problems.append(f"{stage['id']} 仍提到「{word}」")

        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {exercise_id}  阶段 {' → '.join(stage_ids)}")
        for problem in problems:
            print("        " + problem)
        if problems:
            failures.append(f"{exercise_id}(阶段表)")
    return failures


def main() -> int:
    from services.agent_lab_specs import SPECS
    from services.judge_service import judge_submission

    variants_only = "--variants" in sys.argv[1:]
    failures = []

    if not variants_only:
        missing = sorted(set(SPECS) - set(REFERENCE_SOLUTIONS))
        if missing:
            print("缺少参考答案的关卡：" + ", ".join(missing))
            return 1

        for exercise_id in sorted(SPECS, key=lambda item: (item[0], item[2])):
            result = judge_submission(exercise_id, REFERENCE_SOLUTIONS[exercise_id])
            total = result["total"]
            passed = result["passed_count"]
            status = "PASS" if result["passed"] else "FAIL"
            print(f"[{status}] {exercise_id}  {passed}/{total}  ({result['execution_time']}s)")
            if not result["passed"]:
                failures.append(exercise_id)
                if result.get("compile_error"):
                    print("        编译/执行错误：" + str(result["compile_error"]))
                for item in result.get("results", []):
                    if not item["passed"]:
                        print(f"        用例 {item['case_index']} 未通过：{item['error']}")
        print()
        failures.extend(run_sample_checks())
        failures.extend(run_stage_checks())

    failures.extend(run_variant_checks())

    print()
    if failures:
        print(f"共 {len(failures)} 项未通过：" + ", ".join(failures))
        return 1
    if variants_only:
        print(f"全部 {len(VARIANT_IDS)} 道变式参考答案均通过变式判题器。")
    else:
        print(f"全部 {len(SPECS)} 关参考答案均通过隐藏用例，"
              f"公开样例与阶段表校验全过，"
              f"{len(VARIANT_IDS)} 道变式全部通过变式判题器。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
