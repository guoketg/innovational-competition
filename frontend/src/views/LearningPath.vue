<template>
  <div class="learning-path-page">
    <PageHero
      eyebrow="PERSONALIZED PATH"
      title="学习路线图"
      description="依赖图约束下的个性化编排：每个站点按你的掌握度着色，连线表示先修依赖，箭头方向即建议的学习顺序。"
      icon="Guide"
    >
      <template #meta>
        <el-tag v-if="summary.total_stations" effect="plain" size="small">共 {{ summary.total_stations }} 站 · 已完成 {{ summary.completed_stations }} 站</el-tag>
        <el-tag v-if="summary.current_station_topic" type="warning" effect="plain" size="small">当前位置：{{ summary.current_station_topic }}</el-tag>
        <el-tag v-if="learningDepth" type="info" effect="plain" size="small">{{ learningDepth }}</el-tag>
      </template>
      <template #actions>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        <el-button v-if="hasPath" size="small" :loading="regenerating" @click="regeneratePath">重新生成</el-button>
        <el-button size="small" type="primary" @click="router.push('/code-lab')">去编程实验室</el-button>
      </template>
    </PageHero>

    <el-empty
      v-if="!loading && !hasPath"
      description="还没有学习路径。先做 5 道小测评，我会按你的水平调整路线；也可以跳过，先按默认水平生成。"
    >
      <div class="empty-actions">
        <el-button type="primary" :loading="generating" @click="openQuickQuiz">先做 5 题测评（约 3 分钟）</el-button>
        <el-button :loading="generating" @click="generatePath()">跳过测评，直接生成</el-button>
      </div>
    </el-empty>

    <el-dialog
      v-model="quizVisible"
      title="5 道题，快速判断你的起点"
      width="640px"
      :close-on-click-modal="false"
    >
      <p class="quiz-hint">答完会按你的掌握情况调整路线起点、项目顺序和学时。不会的题可以留空，不影响生成。</p>
      <div v-if="quizLoading" v-loading="true" class="quiz-loading"></div>
      <template v-else>
        <article v-for="(q, qi) in quizQuestions" :key="q.question_id" class="quiz-item">
          <h4>{{ qi + 1 }}. {{ q.question }}</h4>
          <div v-if="q.options && q.options.length">
            <el-radio-group
              v-if="q.question_type === '单选' || q.question_type === '读代码' || q.question_type === '判断'"
              v-model="quizAnswers[q.question_id]"
            >
              <el-radio v-for="(opt, oi) in q.options" :key="oi" :value="opt">{{ opt }}</el-radio>
            </el-radio-group>
            <el-checkbox-group v-else-if="q.question_type === '多选'" v-model="quizMultiAnswers[q.question_id]">
              <el-checkbox v-for="(opt, oi) in q.options" :key="oi" :value="opt">{{ opt }}</el-checkbox>
            </el-checkbox-group>
          </div>
          <el-input
            v-else
            v-model="quizAnswers[q.question_id]"
            type="textarea"
            :rows="2"
            placeholder="请输入你的答案；不会可以留空"
          />
        </article>
      </template>
      <template #footer>
        <el-button @click="quizVisible = false">取消</el-button>
        <el-button :loading="generating" @click="generatePath()">跳过测评，直接生成</el-button>
        <el-button type="primary" :loading="quizSubmitting" @click="submitQuickQuiz">提交并生成路线</el-button>
      </template>
    </el-dialog>

    <template v-if="loading || hasPath">
      <div class="view-switch">
        <button
          v-for="tab in VIEWS"
          :key="tab.key"
          :class="['view-tab', { active: viewMode === tab.key }]"
          @click="switchView(tab.key)"
        >{{ tab.label }}</button>
      </div>

      <template v-if="viewMode === 'roadmap'">
      <section v-if="reviewNotice" class="notice-strip">
        <span class="notice-dot"></span>
        <div>
          <strong>{{ reviewNotice.title || '检测到需要返工的知识点' }}</strong>
          <p>{{ reviewNotice.message }}</p>
        </div>
      </section>

      <section class="summary-grid">
        <article class="summary-card">
          <small>路径总进度</small>
          <b>{{ summary.overall_progress || 0 }}%</b>
          <el-progress :percentage="summary.overall_progress || 0" :stroke-width="7" :show-text="false" />
        </article>
        <article class="summary-card">
          <small>已完成站点</small>
          <b>{{ summary.completed_stations || 0 }} / {{ summary.total_stations || 0 }}</b>
          <span>当前第 {{ summary.current_day || 1 }} 天</span>
        </article>
        <article class="summary-card">
          <small>待补强知识点</small>
          <b>{{ lowMasteryCount }}</b>
          <span>掌握度低于 40% 的站点</span>
        </article>
        <article class="summary-card">
          <small>可快进知识点</small>
          <b>{{ highMasteryCount }}</b>
          <span>掌握度已达 70% 以上</span>
        </article>
      </section>

      <section v-loading="loading" class="map-card">
        <header class="card-head">
          <div>
            <h2>学习地图</h2>
            <p>横向为拓扑深度（越靠右越依赖前面的内容），纵向为同层站点；虚线是同知识点的连续项目。</p>
          </div>
          <div class="legend">
            <span v-for="(band, key) in BAND" :key="key" class="legend-item">
              <i :style="{ background: band.color }"></i>{{ band.label }}
            </span>
            <span class="legend-item"><i class="legend-ring current"></i>当前站</span>
            <span class="legend-item"><i class="legend-ring done"></i>已完成</span>
          </div>
        </header>
        <div class="map-scroll">
          <div ref="mapEl" class="map-canvas" :style="{ height: layout.height + 'px', minWidth: layout.width + 'px' }"></div>
        </div>
      </section>

      <section class="progress-card">
        <header class="card-head">
          <div>
            <h2>阶段进度</h2>
            <p>每个阶段完成了多少站，以及现在走到哪一站。</p>
          </div>
        </header>
        <article v-for="phase in phaseGroups" :key="phase.name" class="phase-block">
          <div class="phase-head">
            <b>{{ phase.name }}</b>
            <span>已完成 {{ phase.done }} / 共 {{ phase.total }} 站</span>
            <el-progress
              class="phase-bar"
              :percentage="phase.total ? Math.round(phase.done / phase.total * 100) : 0"
              :stroke-width="7"
              :show-text="false"
            />
          </div>
          <ul class="station-list">
            <li
              v-for="station in phase.stations"
              :key="station.key"
              :class="['station-row', `is-${station.status}`]"
            >
              <span class="station-day">第 {{ station.day }} 天</span>
              <span class="station-title">
                <b>{{ station.topic }}</b>
                <small>{{ station.duration || '按需完成' }}</small>
              </span>
              <el-tag :color="BAND[station.mastery_band].color" effect="dark" size="small" class="band-tag">
                {{ BAND[station.mastery_band].label }}{{ station.mastery !== null ? ' ' + Math.round(station.mastery * 100) + '%' : '' }}
              </el-tag>
              <span class="station-sub">
                <i :class="{ on: station.sub_tasks.learn }">教程</i>
                <i :class="{ on: station.sub_tasks.code }">实验</i>
                <i :class="{ on: station.sub_tasks.quiz }">练习</i>
              </span>
              <span :class="['station-status', `is-${station.status}`]">{{ STATUS[station.status].label }}</span>
              <span class="station-actions">
                <el-button v-if="station.knowledge" size="small" text @click="goDoc(station)">看教程</el-button>
                <el-button v-if="station.lab_id" size="small" text type="primary" @click="goStation(station)">做实验</el-button>
              </span>
            </li>
          </ul>
        </article>
      </section>
      </template>

      <section v-if="viewMode === 'graph'" v-loading="graphLoading" class="graph-card">
        <header class="card-head">
          <div>
            <h2>知识图谱</h2>
            <p>AI 依据知识点名单生成描述，并推断「先修（灰色实线箭头）」与「相似（紫色虚线）」两类关系；先修边中标注「专家」的来自课程先修表，不会被 AI 覆盖。节点大小表示关联数量，颜色沿用掌握度分档。</p>
          </div>
          <div class="legend">
            <span v-for="(band, key) in BAND" :key="key" class="legend-item">
              <i :style="{ background: band.color }"></i>{{ band.label }}
            </span>
            <span class="legend-item"><i class="legend-line prereq"></i>先修</span>
            <span class="legend-item"><i class="legend-line similar"></i>相似</span>
          </div>
        </header>

        <div class="graph-bar">
          <el-button
            size="small"
            type="primary"
            :loading="graphGenerating"
            @click="generateGraph"
          >{{ graph?.has_graph ? '重新生成知识图谱' : '用 AI 构建知识图谱' }}</el-button>
          <el-tag size="small" effect="plain" :type="graph?.has_graph ? 'success' : 'info'">
            {{ graph?.has_graph ? 'AI 已生成' : '专家骨架' }}
          </el-tag>
          <el-tag v-if="graphStats.nodes" size="small" effect="plain">知识点 {{ graphStats.nodes }}</el-tag>
          <el-tag v-if="graphStats.prerequisite" size="small" effect="plain">先修 {{ graphStats.prerequisite }}</el-tag>
          <el-tag v-if="graphStats.similar" size="small" effect="plain">相似 {{ graphStats.similar }}</el-tag>
          <span class="graph-tip">点击节点查看描述与关联</span>
        </div>

        <p v-if="graphNotice" class="graph-notice">{{ graphNotice }}</p>

        <div class="graph-scroll">
          <div ref="graphEl" class="graph-canvas"></div>
        </div>
      </section>
    </template>

    <el-drawer v-model="detailVisible" :title="detailNode?.name || '知识点'" size="420px">
      <div v-if="detailNode" class="node-detail">
        <div class="detail-head">
          <el-tag :color="BAND[detailNode.mastery_band]?.color" effect="dark" size="small" class="band-tag">
            {{ BAND[detailNode.mastery_band]?.label }}{{ detailMastery }}
          </el-tag>
          <code>{{ detailNode.tag }}</code>
        </div>
        <p v-if="detailNode.definition" class="detail-def">{{ detailNode.definition }}</p>
        <div v-if="detailNode.key_points?.length" class="detail-block">
          <b>关键要点</b>
          <ul><li v-for="point in detailNode.key_points" :key="point">{{ point }}</li></ul>
        </div>
        <div v-for="group in detailRelations" :key="group.key" class="detail-block">
          <b>{{ group.title }}</b>
          <ul v-if="group.items.length" class="rel-list">
            <li v-for="item in group.items" :key="item.tag">
              <button class="rel-link" @click="openDetail(item.tag)">{{ item.name }}</button>
              <span :class="['rel-origin', item.origin]">{{ item.origin === 'expert' ? '专家' : 'AI' }}</span>
              <small v-if="item.reason">{{ item.reason }}</small>
            </li>
          </ul>
          <p v-else class="rel-empty">暂无</p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import PageHero from '../components/PageHero.vue'
import {
  deleteLearningPath,
  generateKnowledgeGraph,
  generateLearningPath,
  getKnowledgeGraph,
  getLearningRoadmap,
  startQuickQuiz,
  submitQuickQuiz as submitQuickQuizApi,
} from '../api/learning'

const router = useRouter()

const VIEWS = [
  { key: 'roadmap', label: '学习路线图' },
  { key: 'graph', label: '知识图谱' },
]

const BAND = {
  high: { label: '可快进', color: '#2f9e6b', desc: '掌握度 ≥ 70%' },
  medium: { label: '在学', color: '#4c7ff0', desc: '掌握度 40%–70%' },
  low: { label: '需补强', color: '#e08a3c', desc: '掌握度 < 40%' },
  unknown: { label: '暂无诊断', color: '#9aa4b6', desc: '还没有练习证据' },
}
const STATUS = {
  done: { label: '已完成', border: '#2f9e6b' },
  current: { label: '当前站', border: '#ff6b4a' },
  locked: { label: '前置未完成', border: '#c9d0dd' },
  todo: { label: '待学习', border: '#c9d0dd' },
}

const loading = ref(false)
const generating = ref(false)
const regenerating = ref(false)
const hasPath = ref(false)
const quizVisible = ref(false)
const quizLoading = ref(false)
const quizSubmitting = ref(false)
const quizSessionId = ref(null)
const quizQuestions = ref([])
const quizAnswers = reactive({})
const quizMultiAnswers = reactive({})
const roadmap = ref(null)
const availableTracks = ref([])
const mapEl = ref(null)
const viewMode = ref('roadmap')
const graph = ref(null)
const graphLoading = ref(false)
const graphGenerating = ref(false)
const graphEl = ref(null)
const detailVisible = ref(false)
const detailTag = ref('')
let chart = null
let graphChart = null
let resizeObserver = null

const summary = computed(() => roadmap.value?.summary || {})
const learningDepth = computed(() => roadmap.value?.learning_depth || '')
const reviewNotice = computed(() => roadmap.value?.review_notice || null)
const stations = computed(() => roadmap.value?.stations || [])
const lowMasteryCount = computed(() => stations.value.filter(s => s.mastery_band === 'low').length)
const highMasteryCount = computed(() => stations.value.filter(s => s.mastery_band === 'high').length)

const phaseGroups = computed(() => {
  const groups = (roadmap.value?.phases || []).map(phase => ({ ...phase, stations: [] }))
  stations.value.forEach(station => {
    if (groups[station.phase_index]) groups[station.phase_index].stations.push(station)
  })
  return groups
})

/** 分层布局：x = 拓扑深度，y = 同层站点的等距分布 */
const layout = computed(() => {
  const tiers = new Map()
  stations.value.forEach(station => {
    const tier = station.tier || 0
    if (!tiers.has(tier)) tiers.set(tier, [])
    tiers.get(tier).push(station)
  })
  const keys = [...tiers.keys()].sort((a, b) => a - b)
  const rows = Math.max(...keys.map(key => tiers.get(key).length), 1)
  const height = Math.max(380, rows * 96 + 96)
  const width = Math.max(760, keys.length * 210 + 180)
  const pos = {}
  keys.forEach((key, tierIndex) => {
    const group = tiers.get(key)?.slice().sort((a, b) => a.day - b.day) || []
    const step = height / (group.length + 1)
    group.forEach((station, index) => {
      pos[station.key] = { x: tierIndex * 210 + 110, y: Math.round(step * (index + 1)) }
    })
  })
  return { pos, height, width }
})

// ---------- 知识图谱（§5.8 第二版） ----------
const graphNodes = computed(() => graph.value?.nodes || [])
const graphEdges = computed(() => graph.value?.edges || [])
const graphStats = computed(() => graph.value?.stats || {})
const graphNotice = computed(() => graph.value?.notice || '')

const nodeIndex = computed(() => {
  const map = {}
  graphNodes.value.forEach(node => { map[node.tag] = node })
  return map
})

const detailNode = computed(() => (detailTag.value ? nodeIndex.value[detailTag.value] : null) || null)
const detailMastery = computed(() => {
  const value = detailNode.value?.mastery
  return value === null || value === undefined ? '' : ` ${Math.round(value * 100)}%`
})

/** 二级详情：先修（入边）/ 后继（出边）/ 相似 三组关联 */
const detailRelations = computed(() => {
  const node = detailNode.value
  if (!node) return []
  const prereq = [], next = [], similar = []
  graphEdges.value.forEach(edge => {
    const other = edge.source === node.tag ? edge.target : edge.target === node.tag ? edge.source : null
    if (!other) return
    const item = {
      tag: other,
      name: nodeIndex.value[other]?.name || other,
      reason: edge.reason,
      origin: edge.origin,
    }
    if (edge.relation === 'similar') similar.push(item)
    else if (edge.target === node.tag) prereq.push(item)
    else next.push(item)
  })
  return [
    { key: 'prereq', title: '先修（学它之前建议先掌握）', items: prereq },
    { key: 'next', title: '后继（掌握它之后可以学）', items: next },
    { key: 'similar', title: '相似（易混淆，适合对比学习）', items: similar },
  ]
})

/** 颜色工具：把十六进制色混入白色（ratio 越大越浅） */
function shade(hex, ratio) {
  const n = parseInt(hex.slice(1), 16)
  const mix = c => Math.round(c + (255 - c) * ratio)
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`
}

/** 颜色工具：把十六进制色转成带透明度的 rgba */
function alpha(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

function buildGraphOption() {
  const degree = {}
  graphEdges.value.forEach(edge => {
    degree[edge.source] = (degree[edge.source] || 0) + 1
    degree[edge.target] = (degree[edge.target] || 0) + 1
  })

  const nodes = graphNodes.value.map(node => {
    const band = BAND[node.mastery_band] || BAND.unknown
    return {
      id: node.tag,
      name: node.name,
      raw: node,
      symbolSize: 34 + Math.min(degree[node.tag] || 0, 8) * 4,
      itemStyle: {
        color: {
          type: 'radial',
          x: 0.36,
          y: 0.3,
          r: 0.78,
          colorStops: [
            { offset: 0, color: shade(band.color, 0.48) },
            { offset: 1, color: band.color },
          ],
        },
        borderColor: '#ffffff',
        borderWidth: 2,
        shadowBlur: 16,
        shadowColor: alpha(band.color, 0.38),
      },
      label: {
        show: true,
        position: 'bottom',
        distance: 8,
        fontSize: 12,
        fontWeight: 600,
        color: '#33405c',
        textBorderColor: '#ffffff',
        textBorderWidth: 3,
        formatter: params => {
          const text = String(params.name || '').split('：').pop() || params.name || ''
          return text.length > 12 ? `${text.slice(0, 12)}…` : text
        },
      },
    }
  })

  const links = graphEdges.value.map(edge => ({
    source: edge.source,
    target: edge.target,
    raw: edge,
    lineStyle: edge.relation === 'similar'
      ? {
          color: '#a97fe6',
          width: 1.8,
          type: 'dashed',
          curveness: 0.24,
          opacity: 0.9,
          shadowBlur: 6,
          shadowColor: 'rgba(169,127,230,.35)',
        }
      : { color: '#93a6c6', width: 1.7, curveness: 0.1, opacity: 0.9 },
  }))

  return {
    animationDuration: 800,
    animationEasingUpdate: 'cubicOut',
    backgroundColor: {
      type: 'radial',
      x: 0.5,
      y: 0.45,
      r: 0.8,
      colorStops: [
        { offset: 0, color: '#fdfdff' },
        { offset: 1, color: '#eef2fa' },
      ],
    },
    tooltip: {
      confine: true,
      backgroundColor: 'rgba(255,255,255,.98)',
      borderColor: '#dfe6f5',
      borderWidth: 1,
      padding: [10, 13],
      textStyle: { color: '#33405c', fontSize: 12, lineHeight: 19 },
      extraCssText: 'border-radius:12px; box-shadow:0 10px 28px rgba(24,38,72,.16);',
      formatter: (params) => {
        if (params.dataType === 'edge') {
          const edge = params.data.raw
          const label = edge.relation === 'similar' ? '相似' : '先修'
          return [
            `<b>${label}</b>：${nodeIndex.value[edge.source]?.name || edge.source} → ${nodeIndex.value[edge.target]?.name || edge.target}`,
            edge.reason || '',
            `来源：${edge.origin === 'expert' ? '专家先修表' : 'AI 推断'}`,
          ].filter(Boolean).join('<br/>')
        }
        const node = params.data.raw
        const band = BAND[node.mastery_band] || BAND.unknown
        const mastery = node.mastery === null || node.mastery === undefined ? '暂无' : `${Math.round(node.mastery * 100)}%`
        return [
          `<b>${node.name}</b>`,
          node.definition || '',
          `掌握度：${mastery}（${band.label}）`,
          '点击查看要点与关联',
        ].filter(Boolean).join('<br/>')
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: nodes,
      links,
      force: { repulsion: 520, edgeLength: [120, 200], gravity: 0.05, friction: 0.12 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 9],
      scaleLimit: { min: 0.6, max: 3 },
      emphasis: {
        focus: 'adjacency',
        scale: 1.12,
        itemStyle: { borderWidth: 3, shadowBlur: 22 },
        lineStyle: { width: 2.8, opacity: 1 },
        label: { fontWeight: 700, color: '#17213a' },
      },
      blur: {
        itemStyle: { opacity: 0.16 },
        lineStyle: { opacity: 0.06 },
        label: { opacity: 0.15 },
      },
      labelLayout: { hideOverlap: true },
    }],
  }
}

function shortTopic(topic) {
  const text = String(topic || '').split('：').pop() || ''
  return text.length > 9 ? `${text.slice(0, 9)}…` : text
}

function buildOption() {
  const nodes = stations.value.map(station => {
    const point = layout.value.pos[station.key] || { x: 110, y: 60 }
    const band = BAND[station.mastery_band] || BAND.unknown
    const status = STATUS[station.status] || STATUS.todo
    return {
      id: station.key,
      name: station.topic,
      x: point.x,
      y: point.y,
      symbol: 'roundRect',
      symbolSize: [148, 54],
      raw: station,
      itemStyle: {
        color: band.color,
        borderColor: status.border,
        borderWidth: station.status === 'current' ? 3 : 1.5,
        opacity: station.status === 'locked' ? 0.55 : 1,
        shadowBlur: station.status === 'current' ? 14 : 0,
        shadowColor: 'rgba(255,107,74,.4)',
      },
      label: {
        show: true,
        position: 'inside',
        formatter: `{d|第${station.day}站}\n{t|${shortTopic(station.topic)}}`,
        rich: {
          d: { fontSize: 10, lineHeight: 15, color: 'rgba(255,255,255,.82)' },
          t: { fontSize: 12, lineHeight: 16, fontWeight: 650, color: '#fff' },
        },
      },
    }
  })

  const edges = (roadmap.value?.edges || []).map(edge => ({
    source: edge.source,
    target: edge.target,
    lineStyle: edge.kind === 'sequence'
      ? { color: '#cfd6e4', width: 1.5, type: 'dashed', curveness: 0.06 }
      : { color: '#a6b1c7', width: 1.5, curveness: 0.08 },
  }))

  return {
    animationDuration: 420,
    tooltip: {
      confine: true,
      formatter: (params) => {
        const station = params.data?.raw
        if (!station) return ''
        const band = BAND[station.mastery_band] || BAND.unknown
        const mastery = station.mastery === null ? '暂无' : `${Math.round(station.mastery * 100)}%`
        const subs = `教程${station.sub_tasks.learn ? '✓' : '·'} 实验${station.sub_tasks.code ? '✓' : '·'} 练习${station.sub_tasks.quiz ? '✓' : '·'}`
        return [
          `<b>第 ${station.day} 天 · ${station.topic}</b>`,
          `${station.phase_name || ''}`,
          `掌握度：${mastery}（${band.label}）`,
          `进度：${subs}`,
          `状态：${STATUS[station.status]?.label || ''}`,
        ].join('<br/>')
      },
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: true,
      draggable: false,
      data: nodes,
      links: edges,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 7],
      lineStyle: { color: '#a6b1c7', width: 1.5 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 2.4 } },
    }],
  }
}

/** 按当前视图渲染对应图表（两个视图互斥挂载，切换后重建实例） */
function renderActive() {
  if (viewMode.value === 'roadmap') {
    if (!mapEl.value) return
    if (!chart) chart = echarts.init(mapEl.value)
    chart.setOption(buildOption(), true)
    return
  }
  if (!graphEl.value) return
  if (!graphChart) {
    graphChart = echarts.init(graphEl.value)
    graphChart.on('click', params => {
      if (params.dataType === 'node' && params.data?.raw) openDetail(params.data.raw.tag)
    })
  }
  graphChart.setOption(buildGraphOption(), true)
}

function disposeCharts() {
  chart?.dispose()
  chart = null
  graphChart?.dispose()
  graphChart = null
}

function bindResize() {
  resizeObserver?.disconnect()
  if (mapEl.value) resizeObserver?.observe(mapEl.value)
  if (graphEl.value) resizeObserver?.observe(graphEl.value)
}

function openDetail(tag) {
  detailTag.value = tag
  detailVisible.value = true
}

async function switchView(mode) {
  if (viewMode.value === mode) return
  disposeCharts()
  viewMode.value = mode
  if (mode === 'graph' && !graph.value) await loadGraph()
  await nextTick()
  renderActive()
  bindResize()
}

async function loadGraph() {
  graphLoading.value = true
  try {
    graph.value = (await getKnowledgeGraph()) || null
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '获取知识图谱失败')
  } finally {
    graphLoading.value = false
  }
}

async function generateGraph() {
  graphGenerating.value = true
  try {
    graph.value = (await generateKnowledgeGraph()) || null
    ElMessage.success('已生成知识图谱')
    await nextTick()
    renderActive()
    bindResize()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '生成知识图谱失败')
  } finally {
    graphGenerating.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const data = await getLearningRoadmap()
    hasPath.value = !!data?.has_path
    roadmap.value = data?.has_path ? data : null
    availableTracks.value = data?.available_tracks || []
    if (hasPath.value) {
      await nextTick()
      renderActive()
      bindResize()
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '获取学习地图失败')
  } finally {
    loading.value = false
  }
}

function clearQuizAnswers() {
  Object.keys(quizAnswers).forEach(key => delete quizAnswers[key])
  Object.keys(quizMultiAnswers).forEach(key => delete quizMultiAnswers[key])
}

async function openQuickQuiz() {
  quizVisible.value = true
  quizLoading.value = true
  quizQuestions.value = []
  quizSessionId.value = null
  clearQuizAnswers()
  try {
    const data = await startQuickQuiz()
    quizSessionId.value = data?.session_id || null
    quizQuestions.value = data?.questions || []
    if (!quizQuestions.value.length) {
      ElMessage.warning('暂时没有拿到题目，可以先跳过测评直接生成')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '获取测评题目失败，可以先跳过测评直接生成')
  } finally {
    quizLoading.value = false
  }
}

async function submitQuickQuiz() {
  if (!quizSessionId.value) {
    ElMessage.warning('题目还没准备好，可以先跳过测评直接生成')
    return
  }
  const answerList = quizQuestions.value.map((q) => {
    const value = quizMultiAnswers[q.question_id] ?? quizAnswers[q.question_id]
    return {
      question_id: q.question_id,
      user_answer: Array.isArray(value) ? value.join(',') : (value || ''),
    }
  })
  if (!answerList.some((item) => item.user_answer)) {
    ElMessage.info('这 5 题都空着，将按注册信息先估一个水平')
    await generatePath()
    return
  }
  quizSubmitting.value = true
  try {
    await submitQuickQuizApi({ session_id: quizSessionId.value, answers: answerList })
    localStorage.setItem('last_quick_quiz_session_id', String(quizSessionId.value))
    await generatePath(quizSessionId.value)
    if (hasPath.value) quizVisible.value = false
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '提交测评失败，可以先跳过测评直接生成')
  } finally {
    quizSubmitting.value = false
  }
}

async function generatePath(diagnosticSessionId = null) {
  generating.value = true
  try {
    await generateLearningPath({
      modules: availableTracks.value,
      learning_depth: '标准',
      diagnostic_session_id: diagnosticSessionId,
    })
    ElMessage.success(diagnosticSessionId ? '已按测评结果生成学习路线' : '已生成学习路线')
    quizVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '生成学习路线失败')
  } finally {
    generating.value = false
  }
}

async function regeneratePath() {
  try {
    await ElMessageBox.confirm(
      '重新生成会清空当前的任务进度，但会按你最新的学习情况重新调整路线。确定继续吗？',
      '重新生成学习路线',
      { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  regenerating.value = true
  try {
    const lastQuizSessionId = Number(localStorage.getItem('last_quick_quiz_session_id')) || null
    await deleteLearningPath()
    hasPath.value = false
    roadmap.value = null
    await load()
    await generatePath(lastQuizSessionId)
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '重置学习路线失败')
  } finally {
    regenerating.value = false
  }
}

function goStation(station) {
  if (station.module_id && station.lab_id) {
    router.push(`/code-lab/${station.module_id}/${station.lab_id}`)
    return
  }
  goDoc(station)
}

function goDoc(station) {
  router.push(station.knowledge ? { path: '/learning-docs', query: { knowledge: station.knowledge } } : '/learning-docs')
}

onMounted(async () => {
  resizeObserver = new ResizeObserver(() => {
    chart?.resize()
    graphChart?.resize()
  })
  await load()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  disposeCharts()
})
</script>

<style scoped>
.learning-path-page { display: flex; flex-direction: column; gap: 16px; }

.empty-actions { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; }
.quiz-hint { margin: 0 0 16px; color: #66708a; font-size: 13px; line-height: 1.6; }
.quiz-loading { min-height: 180px; }
.quiz-item { padding: 12px 0; border-bottom: 1px solid #eef1f7; }
.quiz-item:last-child { border-bottom: 0; }
.quiz-item h4 { margin: 0 0 10px; font-size: 14px; font-weight: 600; color: #1f2a44; line-height: 1.6; }
.quiz-item :deep(.el-radio-group),
.quiz-item :deep(.el-checkbox-group) { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }

.view-switch {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid #e2e7f1;
  border-radius: 12px;
  background: #f4f7fc;
  align-self: flex-start;
}
.view-tab {
  padding: 6px 16px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #71809b;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all .18s;
}
.view-tab:hover { color: #4c7ff0; }
.view-tab.active { background: #fff; color: #17213a; box-shadow: 0 2px 8px rgba(24, 38, 72, .1); }

.notice-strip {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid #f3d9cf;
  border-radius: 14px;
  background: linear-gradient(100deg, #fff7f3, #fffdfb);
}
.notice-dot { width: 8px; height: 8px; flex: 0 0 8px; margin-top: 6px; border-radius: 50%; background: #ff8c73; }
.notice-strip strong { color: #c05238; font-size: 13px; }
.notice-strip p { margin: 3px 0 0; color: #8a6a5f; font-size: 12px; }

.summary-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
.summary-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 15px 17px;
  border: 1px solid #e2e7f1;
  border-radius: 16px;
  background: #fff;
  box-shadow: var(--shadow-sm, 0 4px 14px rgba(24, 38, 72, .06));
}
.summary-card small { color: #8a95a8; font-size: 11px; letter-spacing: .04em; }
.summary-card b { color: #17213a; font-size: 22px; font-weight: 760; letter-spacing: -.02em; }
.summary-card span { color: #8a95a8; font-size: 11px; }

.map-card,
.graph-card,
.progress-card {
  padding: 16px 18px 18px;
  border: 1px solid #e2e7f1;
  border-radius: 18px;
  background: #fff;
  box-shadow: var(--shadow-sm, 0 4px 14px rgba(24, 38, 72, .06));
}
.card-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.card-head h2 { margin: 0; color: #17213a; font-size: 15px; font-weight: 720; }
.card-head p { margin: 4px 0 0; color: #8a95a8; font-size: 11.5px; line-height: 1.6; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; color: #5b6579; font-size: 11.5px; }
.legend-item i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; }
.legend-ring { border-radius: 50%; background: transparent !important; }
.legend-ring.current { border: 3px solid #ff6b4a; }
.legend-ring.done { border: 3px solid #2f9e6b; }

.map-scroll { overflow-x: auto; }
.map-canvas { width: 100%; }

/* ---------- 知识图谱 ---------- */
.graph-card .legend-item i { border-radius: 50%; box-shadow: 0 2px 6px rgba(24, 38, 72, .18); }
.legend-line { width: 16px !important; height: 0 !important; border-radius: 0 !important; box-shadow: none !important; }
.legend-line.prereq { border-top: 2px solid #93a6c6; }
.legend-line.similar { border-top: 2px dashed #a97fe6; }

.graph-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; }
.graph-tip { color: #9aa4b6; font-size: 11.5px; }
.graph-notice {
  margin: 0 0 10px;
  padding: 9px 12px;
  border: 1px solid #dbe6fb;
  border-radius: 11px;
  background: #f4f8ff;
  color: #5b7291;
  font-size: 12px;
  line-height: 1.6;
}
.graph-scroll {
  overflow: hidden;
  border: 1px solid #e8edf7;
  border-radius: 14px;
  background: #fbfcff;
}
.graph-canvas { width: 100%; height: 620px; }

.node-detail { display: flex; flex-direction: column; gap: 14px; }
.detail-head { display: flex; align-items: center; gap: 8px; }
.detail-head code { padding: 2px 7px; border-radius: 6px; background: #f1f4fa; color: #71809b; font-size: 11.5px; }
.detail-def { margin: 0; color: #3c4658; font-size: 13px; line-height: 1.75; }
.detail-block { display: flex; flex-direction: column; gap: 6px; }
.detail-block > b { color: #17213a; font-size: 12.5px; font-weight: 700; }
.detail-block ul { margin: 0; padding-left: 18px; color: #4a5568; font-size: 12.5px; line-height: 1.8; }
.rel-list { padding-left: 0 !important; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.rel-list li { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.rel-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: #4c7ff0;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.rel-link:hover { text-decoration: underline; }
.rel-origin { padding: 1px 6px; border-radius: 6px; font-size: 10.5px; }
.rel-origin.expert { background: #eef3fb; color: #5b7291; }
.rel-origin.llm { background: #f4eefc; color: #8a5cd0; }
.rel-list small { flex: 1 1 100%; color: #9aa4b6; font-size: 11px; }
.rel-empty { margin: 0; color: #b3bbca; font-size: 12px; }

.phase-block { padding: 12px 0; border-top: 1px solid #eef1f7; }
.phase-block:first-of-type { border-top: 0; }
.phase-head { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.phase-head b { color: #17213a; font-size: 13px; font-weight: 700; }
.phase-head span { color: #8a95a8; font-size: 11.5px; }
.phase-bar { flex: 1 1 160px; min-width: 120px; }

.station-list { margin: 10px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.station-row {
  display: grid;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid #eef1f7;
  border-radius: 12px;
  background: #fbfcfe;
  grid-template-columns: 66px minmax(180px, 1fr) auto auto auto auto;
}
.station-row.is-current { border-color: #f6c9b9; background: #fff9f6; }
.station-row.is-locked { opacity: .72; }
.station-day { color: #8a95a8; font-size: 11.5px; }
.station-title { display: flex; flex-direction: column; min-width: 0; }
.station-title b { overflow: hidden; color: #17213a; font-size: 12.5px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.station-title small { color: #9aa4b6; font-size: 10.5px; }
.band-tag { border: 0; }
.station-sub { display: inline-flex; gap: 6px; }
.station-sub i { padding: 2px 7px; border: 1px solid #e2e7f1; border-radius: 7px; color: #a3abbb; font-size: 10.5px; font-style: normal; }
.station-sub i.on { border-color: #bfe3d1; color: #2f9e6b; background: #f1faf5; }
.station-status { font-size: 11.5px; color: #8a95a8; }
.station-status.is-done { color: #2f9e6b; }
.station-status.is-current { color: #ff6b4a; font-weight: 650; }
.station-actions { display: inline-flex; gap: 2px; justify-self: end; }

@media (max-width: 900px) {
  .station-row { grid-template-columns: 1fr; gap: 6px; }
  .station-actions { justify-self: start; }
}
</style>
