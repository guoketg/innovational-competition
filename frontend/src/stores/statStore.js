/**
 * statStore.js — 全局统计数据仓库（唯一数据源）
 *
 * 架构规则：
 * - 页面只读 state，不调 api
 * - refreshStatData() 一次性拉取 概览 + 掌握度 + 动态，全部完成后统一赋值
 * - 掌握度来自后端 get_user_knowledge_profile()，前端不写死任何数值
 */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import {
  fetchStats,              // GET /api/analytics/stats
  fetchKnowledgeMastery,   // GET /api/diagnosis/profile
  fetchWeeklyReport,
  fetchMonthlyReport,
  fetchGrowthData,
  fetchRecentActivity,
  submitQuizResult,
  refreshStats as refreshApi,
} from '../api/statistics'

export const useStatStore = defineStore('statistics', () => {
  // ===== 概览卡片 =====
  const studyDays = ref(0)
  const totalQuestions = ref(0)
  const avgCorrectRate = ref(0)
  const quizCount = ref(0)
  const quizAvgScore = ref(0)
  const errorCount = ref(0)

  // ===== 图表 =====
  const weeklyStats = ref([])
  const knowledgeMastery = ref({})
  const masteryHasData = ref({})  // 哪些标签有真实数据（非默认值）

  // ===== 动态 =====
  const recentActivity = ref([])

  // ===== 报告 =====
  const weeklyReport = ref(null)
  const monthlyReport = ref(null)
  const growthData = ref(null)

  // ===== 状态 =====
  const loading = ref(false)

  // ===== 计算 =====
  const hasMasteryData = computed(() => Object.keys(knowledgeMastery.value).length > 0)

  // ===== 知识点 → 模块映射 =====
  // 将后端返回的细粒度知识点掌握度聚合为六大模块
  const moduleNames = [
    '模块一：线性结构',
    '模块二：树与堆',
    '模块三：图与并查集',
    '模块四：排序算法',
    '模块五：哈希与缓存',
    '模块六：算法工具箱与综合',
  ]

  const tagToModule = {
    // 模块一：线性结构
    '线性结构：顺序表 / 链表 / 栈': 0,
    // 模块二：树与堆
    '二分搜索树：插入与查找': 1,
    '二分搜索树：中序与层序遍历': 1,
    '堆：上浮与下沉': 1,
    // 模块三：图与并查集
    '图的表示与深度优先遍历': 2,
    '并查集与路径压缩': 2,
    '广度优先遍历与最短路径': 2,
    // 模块四：排序算法
    '归并排序与性能基准': 3,
    '堆排序': 3,
    // 模块五：哈希与缓存
    '哈希表与 LRU 缓存': 4,
    // 模块六：算法工具箱与综合
    '算法工具箱：统一入口与分发': 5,
  }

  const moduleMastery = computed(() => {
    const raw = knowledgeMastery.value
    if (!raw || Object.keys(raw).length === 0) return {}

    // 按模块聚合
    const buckets = moduleNames.map(() => ({ sum: 0, count: 0 }))
    let totalDataPoints = 0

    for (const [tag, score] of Object.entries(raw)) {
      const modIdx = tagToModule[tag]
      if (modIdx === undefined) continue
      const num = Number(score)
      if (num == null || isNaN(num)) continue
      // 优先用后端 has_data 标记；没有则回退为「分数非零」
      const hasData = masteryHasData.value[tag]
      if (hasData === true) { /* 有明确标记，允许 0 分 */ }
      else if (hasData === false) continue
      else if (num <= 0) continue  // 兜底：无标记且分数为0，视为无数据
      buckets[modIdx].sum += num
      buckets[modIdx].count += 1
      totalDataPoints++
    }

    // 没有任何真实数据 → 返回空，前端显示空状态
    if (totalDataPoints === 0) return {}

    const result = {}
    moduleNames.forEach((name, i) => {
      if (buckets[i].count > 0) {
        result[name] = Math.round(buckets[i].sum / buckets[i].count * 100)
      } else {
        result[name] = 0  // 该模块无数据
      }
    })

    return result
  })

  // ===== 调试：监听 knowledgeMastery 每次变化 =====
  watch(knowledgeMastery, (newVal, oldVal) => {
    console.log('[statStore watch] mastery 变化: 旧', Object.keys(oldVal || {}).length, '→ 新', Object.keys(newVal || {}).length)
  })

  // ================================================================
  //  内部加载函数
  // ================================================================

  async function loadOverview() {
    const stats = await fetchStats()
    studyDays.value       = stats.study_days || 0
    totalQuestions.value  = stats.total_questions || 0
    avgCorrectRate.value  = stats.avg_correct_rate || 0
    quizCount.value       = stats.quiz_count || 0
    quizAvgScore.value    = stats.quiz_avg_score || 0
    errorCount.value      = stats.error_count || 0
    weeklyStats.value     = stats.weekly_stats || []
  }

  async function loadKnowledgeMastery() {
    const data = await fetchKnowledgeMastery()
    console.log('[statStore] 后端原始 mastery:', JSON.stringify(data).slice(0, 200))
    knowledgeMastery.value = data.mastery || data
    masteryHasData.value = data.has_data || {}
    console.log('[statStore] Pinia mastery 已存入, 标签数:', Object.keys(knowledgeMastery.value).length)
  }

  async function loadRecentActivity() {
    try {
      recentActivity.value = await fetchRecentActivity()
    } catch (e) {
      console.warn('[statStore] 学习动态加载失败，保留现有数据:', e.message)
      // recentActivity 保持现有值（可能为空数组），不中断其他数据加载
    }
  }

  async function loadWeeklyReport() {
    try {
      loading.value = true
      weeklyReport.value = await fetchWeeklyReport()
    } catch (e) {
      console.warn('[statStore] 周报加载失败:', e.message)
    } finally {
      loading.value = false
    }
  }

  async function loadMonthlyReport() {
    try {
      loading.value = true
      monthlyReport.value = await fetchMonthlyReport()
    } catch (e) {
      console.warn('[statStore] 月报加载失败:', e.message)
    } finally {
      loading.value = false
    }
  }

  async function loadGrowthData() {
    try {
      loading.value = true
      growthData.value = await fetchGrowthData()
    } catch (e) {
      console.warn('[statStore] 成长数据加载失败:', e.message)
    } finally {
      loading.value = false
    }
  }

  // ================================================================
  //  对外公共方法
  // ================================================================

  /**
   * 【核心】做题提交后调用
   * 依次请求：① 提交结果记录  ② 概览统计  ③ 知识点掌握度  ④ 学习动态
   * 各接口独立容错，单个失败不影响其他数据更新
   */
  async function refreshStatData(result) {
    // 通知后端记录测评结果（跨设备同步到 learning_records 表）
    try {
      await submitQuizResult(result)
    } catch (e) {
      console.warn('[statStore.refreshStatData] 提交结果记录失败:', e.message)
    }

    // 各接口独立调用
    const settle = (p) => p.catch(e => {
      console.warn('[statStore.refreshStatData] 接口失败:', e.message)
      return null
    })

    const [statsResult, masteryResult, activityResult] = await Promise.all([
      settle(fetchStats()),
      settle(fetchKnowledgeMastery()),
      settle(fetchRecentActivity()),
    ])

    if (statsResult) {
      const s = statsResult
      studyDays.value       = s.study_days || 0
      totalQuestions.value  = s.total_questions || 0
      avgCorrectRate.value  = s.avg_correct_rate || 0
      quizCount.value       = s.quiz_count || 0
      quizAvgScore.value    = s.quiz_avg_score || 0
      errorCount.value      = s.error_count || 0
      weeklyStats.value     = s.weekly_stats || []
    }

    if (masteryResult) {
      knowledgeMastery.value = masteryResult.mastery || masteryResult
      masteryHasData.value = masteryResult.has_data || {}
    }

    if (activityResult) {
      recentActivity.value = activityResult
    }
  }

  /** 全量刷新（Dashboard 进入时调用，各接口独立容错） */
  async function refreshAll() {
    // 先验证后端可达
    try {
      await refreshApi()
    } catch (e) {
      console.warn('[statStore.refreshAll] 后端连通性检查失败:', e.message)
    }

    // 各接口独立调用，单个失败不影响其他数据
    const settle = (p) => p.catch(e => {
      console.warn('[statStore.refreshAll] 接口失败:', e.message)
      return null
    })

    const [statsResult, masteryResult, activityResult] = await Promise.all([
      settle(fetchStats()),
      settle(fetchKnowledgeMastery()),
      settle(fetchRecentActivity()),
    ])

    if (statsResult) {
      const s = statsResult
      studyDays.value       = s.study_days || 0
      totalQuestions.value  = s.total_questions || 0
      avgCorrectRate.value  = s.avg_correct_rate || 0
      quizCount.value       = s.quiz_count || 0
      quizAvgScore.value    = s.quiz_avg_score || 0
      errorCount.value      = s.error_count || 0
      weeklyStats.value     = s.weekly_stats || []
    }

    if (masteryResult) {
      knowledgeMastery.value = masteryResult.mastery || masteryResult
      masteryHasData.value = masteryResult.has_data || {}
    } else {
      console.warn('[statStore.refreshAll] 掌握度数据加载失败，保持现有数据')
    }

    if (activityResult) {
      recentActivity.value = activityResult
    } else {
      console.warn('[statStore.refreshAll] 学习动态加载失败，保持现有数据')
    }

    // 报告（异步，失败不影响主要数据）
    loadWeeklyReport().catch(() => {})
    loadMonthlyReport().catch(() => {})
    loadGrowthData().catch(() => {})
  }

  return {
    studyDays, totalQuestions, avgCorrectRate, quizCount, quizAvgScore, errorCount,
    weeklyStats, knowledgeMastery, masteryHasData, recentActivity,
    weeklyReport, monthlyReport, growthData, loading,
    hasMasteryData, moduleMastery, moduleNames,
    refreshStatData, refreshAll,
  }
})
