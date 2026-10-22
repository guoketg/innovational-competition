// 项目制编程路线。题目正文与私有测试由后端提供，这里只负责课程导航。
// 四个阶段全部为数据结构与算法内容：线性结构 → 树与堆 → 图与并查集 → 算法工具箱工程化。
export const MODULES = [
  {
    id: 1,
    name: '阶段一：线性结构与基础容器',
    level: '入门',
    project: '算法工具箱',
    description: '从顺序表开始，用 C++ 标准库实现线性结构与基础容器；每关只做本关自己的那道题，代码互不影响。',
    tasks: [
      { id: '1-1', title: '实现顺序表插入', duration: '45分钟' },
      { id: '1-2', title: '反转单链表', duration: '60分钟' },
      { id: '1-3', title: '用栈求值逆波兰表达式', duration: '60分钟' },
    ],
  },
  {
    id: 2,
    name: '阶段二：树与堆',
    level: '进阶',
    project: '有序索引结构',
    description: '用二分搜索树把查找从「逐个比对」压缩到树高，再理解堆如何用数组表示完全二叉树——排序和优先队列都建立在它上面。',
    tasks: [
      { id: '2-1', title: '二分搜索树：插入与查找', duration: '90分钟' },
      { id: '2-2', title: '二分搜索树：中序与层序遍历', duration: '75分钟' },
      { id: '2-3', title: '堆的上浮与下沉', duration: '90分钟' },
      { id: '2-4', title: '堆排序', duration: '75分钟' },
    ],
  },
  {
    id: 3,
    name: '阶段三：图与并查集',
    level: '高级',
    project: '网络连通性分析',
    description: '先选定图的表示方式，再掌握两类基本武器：遍历回答「能不能走到」，并查集回答「是不是一组」。',
    tasks: [
      { id: '3-1', title: '图的邻接表表示与深度优先遍历', duration: '90分钟' },
      { id: '3-2', title: '并查集与路径压缩', duration: '90分钟' },
      { id: '3-3', title: '广度优先遍历与最短路径', duration: '75分钟' },
    ],
  },
  {
    id: 4,
    name: '阶段四：算法工具箱工程化',
    level: '工程',
    project: '可复用算法工具箱',
    description: '把前三阶段写完的散装函数收拢成有统一入口的工具箱，再用排序与缓存两个场景把「复杂度」从口号变成可验证的工程判断。',
    tasks: [
      { id: '4-1', title: '把散装算法收拢成 toolbox', duration: '90分钟' },
      { id: '4-2', title: '排序算法的性能基准与复杂度验证', duration: '90分钟' },
      { id: '4-3', title: '缓存与查找：LRU / 哈希表', duration: '120分钟' },
    ],
  },
]

for (const module of MODULES) module.taskCount = module.tasks.length

export const MOCK_PROGRESS = { 1: 0, 2: 0, 3: 0, 4: 0 }
