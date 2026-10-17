<template>
  <div class="learning-docs-page">
    <div class="path-toolbar">
      <div class="path-toolbar-copy">
        <h1>学习文档</h1>
        <span>{{ total ? `数据结构与算法 · 共 ${total} 篇教程` : '正在加载教程目录…' }}</span>
      </div>
      <div class="path-actions">
        <el-button size="small" text @click="openAIDialog">🤖 AI 生成教程</el-button>
      </div>
    </div>

    <el-empty v-if="!loading && !modules.length" description="暂无学习文档" />

    <div v-else v-loading="loading" class="course-layout">
      <aside class="course-tree-panel">
        <div class="tree-header">
          <div><span>教程目录</span><b>{{ total }} 篇</b></div>
        </div>

        <div class="course-tree" role="tree" aria-label="学习文档目录">
          <section v-for="(group, groupIndex) in modules" :key="group.module" class="tree-phase">
            <button class="phase-node" @click="toggleGroup(groupIndex)">
              <span class="phase-index">{{ String(groupIndex + 1).padStart(2, '0') }}</span>
              <span class="phase-copy">
                <b>{{ group.module }}</b>
                <small>{{ group.items.length }} 篇教程</small>
              </span>
              <el-icon :class="{ rotated: isGroupExpanded(groupIndex) }"><ArrowRight /></el-icon>
            </button>
            <div v-show="isGroupExpanded(groupIndex)" class="phase-children">
              <div v-for="item in group.items" :key="item.knowledge_tag" class="task-tree-group">
                <button
                  :class="['task-node', { active: currentDoc?.knowledge_tag === item.knowledge_tag, verified: item.source_type !== 'seed' }]"
                  @click="selectDoc(item, groupIndex)"
                >
                  <span class="tree-line-dot">{{ docIndex(item) + 1 }}</span>
                  <span class="task-node-copy">
                    <b>{{ item.title }}</b>
                    <small>{{ sourceLabel(item.source_type) }}</small>
                  </span>
                </button>
                <nav v-if="currentDoc?.knowledge_tag === item.knowledge_tag" class="task-article-tree" aria-label="本页目录">
                  <button
                    v-for="item2 in articleOutline"
                    :key="item2.id"
                    :class="[{ active: activeOutlineId === item2.id }, `level-${item2.level}`]"
                    @click="scrollToOutline(item2)"
                  >
                    <span>{{ item2.level === 3 ? '·' : '§' }}</span>{{ item2.title }}
                  </button>
                  <span v-if="learnDialogLoading" class="tree-outline-loading">正在读取本页目录…</span>
                </nav>
              </div>
            </div>
          </section>
        </div>
      </aside>

      <main class="reader-content-column inline-reader-content">
        <div class="reader-page-nav reader-page-nav-docs">
          <button class="reader-page-link previous" :disabled="!previousDoc" @click="moveDoc(-1)">
            <small>← 上一篇</small><b>{{ previousDoc?.title || '已经是第一篇' }}</b>
          </button>
          <span class="reader-doc-position">{{ currentDocIndex + 1 }} / {{ total }}</span>
          <button class="reader-page-link next" :disabled="!nextDoc" @click="moveDoc(1)">
            <small>下一篇 →</small><b>{{ nextDoc?.title || '已经是最后一篇' }}</b>
          </button>
        </div>

        <!-- 来源标识 -->
        <div v-if="tutorialMeta.source_type && !learnDialogLoading" class="tutorial-source-badge" :class="'source-' + tutorialMeta.source_type">
          <el-tag v-if="tutorialMeta.source_type === 'seed'" type="success" size="small" effect="plain">📚 系统预置</el-tag>
          <el-tag v-else-if="tutorialMeta.source_type === 'user_modified'" type="warning" size="small" effect="plain">✏️ 我的修改</el-tag>
          <el-tag v-else-if="tutorialMeta.source_type === 'ai_generated'" type="primary" size="small" effect="plain">🤖 AI 生成</el-tag>
          <span class="source-breadcrumb">{{ currentGroupName }} · {{ learnDialogTitle }}</span>
          <el-button v-if="tutorialMeta.source_type === 'user_modified'" type="danger" size="small" text @click="restoreSeedTutorial">恢复原始版本</el-button>
          <el-button v-if="tutorialMeta.source_type === 'ai_generated'" type="danger" size="small" text @click="deleteCustomTutorial">删除此教程</el-button>
        </div>

        <!-- #31：AI 生成教程标注「基于你 X 时的状态生成」并提供「按最新状态重新生成」入口 -->
        <div v-if="tutorialMeta.source_type === 'ai_generated' && tutorialProfileNote && !learnDialogLoading" class="tutorial-profile-note">
          <span class="profile-note-text">🧭 {{ tutorialProfileNote }}</span>
          <el-button type="primary" size="small" text :loading="regenLoading" @click="regenerateTutorial">🔄 按最新状态重新生成</el-button>
        </div>

        <!-- #31 分层演化：学习状态已漂移时，提示并引导低成本演化（正文稳定复用，只重算个性化导读） -->
        <div v-if="tutorialMeta.source_type === 'ai_generated' && tutorialMeta.profile_drift && !learnDialogLoading" class="tutorial-drift-note">
          <span class="drift-note-text">✨ 你的学习状态已有更新，本篇个性化导读可以随之演化</span>
          <el-button type="success" size="small" text :loading="evolveLoading" @click="evolveTutorial">随学习状态演化</el-button>
        </div>

        <div v-if="learnDialogLoading" class="reader-loading"><el-icon class="is-loading" :size="30"><Loading /></el-icon><p>正在加载教程…</p></div>

        <!-- 资料缺失提示：系统预置资料未覆盖该知识点时，引导一键 AI 生成（生成后落库，下次直接复用） -->
        <el-alert
          v-if="materialMissing && !learnDialogLoading && !isEditing"
          type="warning"
          :closable="false"
          show-icon
          class="material-missing-alert"
        >
          <template #title>该知识点暂无系统预置资料，当前为占位说明。可一键生成专属教程，生成后自动保存。</template>
          <el-button size="small" type="primary" text @click="openAIGenerateForDoc">🤖 AI 生成本篇教程</el-button>
        </el-alert>

        <!-- 编辑/预览切换 -->
        <div v-if="learnDialogContent && !learnDialogLoading" class="tutorial-edit-bar">
          <el-button size="small" :type="isEditing ? '' : 'primary'" text @click="toggleEditMode">
            {{ isEditing ? '👁 预览' : '✏️ 编辑' }}
          </el-button>
        </div>

        <div v-if="!learnDialogLoading && isEditing" class="learn-material-editor">
          <el-input
            v-model="editContent"
            type="textarea"
            :rows="20"
            placeholder="使用 Markdown 格式编辑教程内容…"
            class="tutorial-textarea"
          />
          <div class="editor-actions">
            <el-button @click="cancelEdit">取消</el-button>
            <el-button type="primary" :loading="saveLoading" @click="saveEditedTutorial">保存修改</el-button>
          </div>
        </div>

        <div
          v-else-if="!learnDialogLoading"
          ref="materialRef"
          class="learn-material-content"
          tabindex="0"
          @scroll="handleArticleScroll"
          v-html="learnDialogContent"
        ></div>
      </main>
    </div>

    <el-dialog v-model="showAIDialog" title="🤖 AI 生成教程" width="550px" :close-on-click-modal="false">
      <el-form :model="aiGenForm" label-position="top">
        <el-form-item label="知识点标识（英文/拼音，用于系统索引）">
          <el-input v-model="aiGenForm.knowledge_tag" placeholder="如: custom-dsa-advanced" />
        </el-form-item>
        <el-form-item label="教程主题">
          <el-input v-model="aiGenForm.topic" placeholder="如: 红黑树原理与实现" />
        </el-form-item>
        <el-form-item label="学习目标（可选）">
          <el-input v-model="aiGenForm.goal" type="textarea" :rows="2" placeholder="想通过这篇教程达成什么学习目标？" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAIDialog = false">取消</el-button>
        <el-button type="primary" :loading="aiGenLoading" :disabled="!aiGenForm.knowledge_tag || !aiGenForm.topic" @click="doAIGenerate">开始生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getLearningDocuments,
  getLearningResource,
  recordStudyVisit,
  saveTutorial,
  deleteTutorial,
  generateAITutorial,
  evolveTutorial as evolveTutorialApi,
} from '../api/learning'
import { bindCodeBlockActions, renderMarkdown } from '../composables/useCodeBlockRenderer'

const route = useRoute()
const modules = ref([])
const total = ref(0)
const loading = ref(false)
const expandedGroups = ref([])
const currentDoc = ref(null)
const learnDialogTitle = ref('')
const learnDialogContent = ref('')
const learnDialogLoading = ref(false)
const tutorialMeta = ref({ source_type: '', tutorial_id: null, parent_id: null, generated_at: null, profile_snapshot: null, profile_drift: false })
const showAIDialog = ref(false)
const aiGenForm = reactive({ knowledge_tag: '', topic: '', goal: '' })
const aiGenLoading = ref(false)
const regenLoading = ref(false)
const evolveLoading = ref(false)
const materialMissing = ref(false)  // 当前文档是否为系统资料未命中的占位兜底
const isEditing = ref(false)
const editContent = ref('')   // 编辑框里的草稿
const savedContent = ref('')  // 当前文档最后一次落库的正文，用于「取消」与重开编辑器时还原
const saveLoading = ref(false)
const materialRef = ref(null)
const articleOutline = ref([])
const activeOutlineId = ref('')
let outlineScrollFrame = 0
let docLoadToken = 0

const SOURCE_LABELS = {
  seed: '系统预置',
  user_modified: '我的修改',
  ai_generated: 'AI 生成',
}

/** 扁平化后的全部文档，用于上一/下一篇导航与序号 */
const flatDocs = computed(() => modules.value.flatMap(group => group.items))
const currentDocIndex = computed(() =>
  flatDocs.value.findIndex(doc => doc.knowledge_tag === currentDoc.value?.knowledge_tag))
const previousDoc = computed(() =>
  currentDocIndex.value > 0 ? flatDocs.value[currentDocIndex.value - 1] : null)
const nextDoc = computed(() =>
  currentDocIndex.value >= 0 && currentDocIndex.value < flatDocs.value.length - 1
    ? flatDocs.value[currentDocIndex.value + 1] : null)
const currentGroupName = computed(() => {
  const tag = currentDoc.value?.knowledge_tag
  return modules.value.find(group => group.items.some(doc => doc.knowledge_tag === tag))?.module || ''
})

/** #31：AI 生成教程的画像标注，如「基于你 2026-10-14 12:00 时的状态生成 · 掌握度：中档」 */
const tutorialProfileNote = computed(() => {
  if (tutorialMeta.value.source_type !== 'ai_generated') return ''
  const snap = tutorialMeta.value.profile_snapshot
  const at = formatGeneratedAt(tutorialMeta.value.generated_at)
  const parts = []
  if (at) parts.push(`基于你 ${at} 时的状态生成`)
  if (snap?.mastery_level) parts.push(`掌握度：${snap.mastery_level}`)
  return parts.join(' · ')
})

/** 兼容快照：后端以 JSON 字符串落库，前端可能拿到字符串或已解析对象 */
function parseSnapshot(raw) {
  if (!raw) return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(raw) } catch { return null }
}

/** 将 ISO / SQLite 时间串格式化为「YYYY-MM-DD HH:mm」 */
function formatGeneratedAt(value) {
  if (!value) return ''
  const date = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function sourceLabel(type) { return SOURCE_LABELS[type] || SOURCE_LABELS.seed }
function docIndex(item) { return flatDocs.value.findIndex(doc => doc.knowledge_tag === item.knowledge_tag) }

function isGroupExpanded(index) { return expandedGroups.value.includes(index) }
function toggleGroup(index) {
  expandedGroups.value = isGroupExpanded(index)
    ? expandedGroups.value.filter(item => item !== index)
    : [...expandedGroups.value, index]
}

onMounted(async () => {
  recordStudyVisit()
  await loadDocuments()
})

async function loadDocuments() {
  loading.value = true
  try {
    await refreshTree()
    const requested = route.query.knowledge
    const target = requested ? flatDocs.value.find(doc => doc.knowledge_tag === requested) : null
    if (target) {
      const groupIndex = modules.value.findIndex(group => group.items.some(doc => doc.knowledge_tag === requested))
      await selectDoc(target, groupIndex >= 0 ? groupIndex : undefined)
    } else if (flatDocs.value.length) {
      await selectDoc(flatDocs.value[0], 0)
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '获取教程目录失败')
    modules.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

/** 只刷新目录树，不改变当前选中的文档 */
async function refreshTree() {
  const data = await getLearningDocuments()
  modules.value = data?.modules || []
  total.value = data?.total || 0
  expandedGroups.value = modules.value.map((_, index) => index)
}

async function selectDoc(doc, groupIndex) {
  if (groupIndex !== undefined && !isGroupExpanded(groupIndex)) expandedGroups.value.push(groupIndex)
  if (currentDoc.value?.knowledge_tag === doc.knowledge_tag && learnDialogContent.value) {
    materialRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  await loadDocument(doc)
}

function moveDoc(offset) {
  const target = offset < 0 ? previousDoc.value : nextDoc.value
  if (target) loadDocument(target)
}

async function loadDocument(doc) {
  if (!doc) return

  // 切换前拦截未保存的编辑
  if (isEditing.value && editContent.value !== '') {
    try {
      await ElMessageBox.confirm('你有未保存的修改，切换教程将丢失这些内容。确定要放弃吗？', '未保存的修改', {
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
        type: 'warning',
      })
    } catch {
      return // 用户取消 — 停留在当前内容
    }
    isEditing.value = false
  }

  const loadToken = ++docLoadToken
  currentDoc.value = doc
  articleOutline.value = []
  activeOutlineId.value = ''
  materialMissing.value = false
  learnDialogLoading.value = true
  try {
    const resource = await getLearningResource(doc.knowledge_tag)
    if (loadToken !== docLoadToken) return
    if (!resource?.content) throw new Error('该教程尚未准备好')
    // 系统资料未命中：后端返回的是占位兜底文案（found=false），提示并引导 AI 生成
    materialMissing.value = resource.found === false && resource.source_type !== 'ai_generated'
    learnDialogTitle.value = resource.matched_tag || doc.title
    tutorialMeta.value = {
      source_type: resource.source_type || 'seed',
      tutorial_id: resource.tutorial_id || null,
      parent_id: resource.parent_id || null,
      generated_at: resource.created_at || null,
      profile_snapshot: parseSnapshot(resource.profile_snapshot),
      profile_drift: !!resource.profile_drift,
    }
    savedContent.value = resource.content || ''
    editContent.value = savedContent.value
    learnDialogContent.value = renderMarkdown(resource.content)
    // 正文在 v-if/v-else 之后才渲染，先显示再绑定代码块复制按钮
    learnDialogLoading.value = false
    await nextTick()
    if (materialRef.value) {
      materialRef.value.scrollTop = 0
      bindCodeBlockActions(materialRef.value)
      rebuildArticleOutline()
    }
  } catch (error) {
    if (loadToken !== docLoadToken) return
    ElMessage.error(error.message || '获取教程失败')
  } finally {
    if (loadToken === docLoadToken) learnDialogLoading.value = false
  }
}

function rebuildArticleOutline() {
  const container = materialRef.value
  if (!container) return
  const tag = currentDoc.value?.knowledge_tag || 'doc'
  articleOutline.value = [...container.querySelectorAll('h2, h3')].map((heading, index) => {
    const id = `doc-${tag}-section-${index + 1}`
    heading.id = id
    return { id, title: heading.textContent?.trim() || `章节 ${index + 1}`, level: Number(heading.tagName.slice(1)) }
  })
  activeOutlineId.value = articleOutline.value[0]?.id || ''
}

function scrollToOutline(item) {
  const container = materialRef.value
  const target = container?.querySelector(`[id="${item.id}"]`)
  if (!container || !target) return
  const top = target.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 22
  container.scrollTo({ top, behavior: 'smooth' })
  activeOutlineId.value = item.id
}

function handleArticleScroll() {
  if (outlineScrollFrame) return
  outlineScrollFrame = window.requestAnimationFrame(() => {
    outlineScrollFrame = 0
    const container = materialRef.value
    if (!container || !articleOutline.value.length) return
    const threshold = container.getBoundingClientRect().top + 90
    let active = articleOutline.value[0]
    for (const item of articleOutline.value) {
      const heading = container.querySelector(`[id="${item.id}"]`)
      if (heading && heading.getBoundingClientRect().top <= threshold) active = item
      else break
    }
    activeOutlineId.value = active.id
  })
}

/** 打开编辑框时以「已保存的正文」为准，避免上次取消掉的草稿留在缓冲区里 */
function toggleEditMode() {
  if (!isEditing.value) editContent.value = savedContent.value
  isEditing.value = !isEditing.value
}

/** 取消编辑：丢弃草稿并退出编辑态 */
function cancelEdit() {
  editContent.value = savedContent.value
  isEditing.value = false
}

async function afterContentRerender() {
  await nextTick()
  if (materialRef.value) {
    materialRef.value.scrollTop = 0
    bindCodeBlockActions(materialRef.value)
    rebuildArticleOutline()
  }
}

async function saveEditedTutorial() {
  if (!editContent.value.trim()) return ElMessage.warning('内容不能为空')
  saveLoading.value = true
  try {
    await saveTutorial(currentDoc.value.knowledge_tag, {
      title: learnDialogTitle.value,
      content: editContent.value,
      source_type: tutorialMeta.value.source_type || 'ai_generated',
    })
    ElMessage.success('已保存')
    savedContent.value = editContent.value
    isEditing.value = false
    learnDialogContent.value = renderMarkdown(editContent.value)
    await afterContentRerender()
    if (tutorialMeta.value.source_type === 'seed') tutorialMeta.value.source_type = 'user_modified'
    // 目录项的来源标签（系统预置 / 我的修改）由后端算出，刷新一下免得与页眉对不上
    try { await refreshTree() } catch (_) { /* 目录刷新失败不影响已保存的结果 */ }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saveLoading.value = false
  }
}

function openAIDialog() {
  aiGenForm.knowledge_tag = ''
  aiGenForm.topic = ''
  aiGenForm.goal = ''
  showAIDialog.value = true
}

/** 资料缺失时的一键生成：预填当前文档的知识点标识与主题，生成后落库复用 */
function openAIGenerateForDoc() {
  aiGenForm.knowledge_tag = currentDoc.value?.knowledge_tag || ''
  aiGenForm.topic = currentDoc.value?.title || learnDialogTitle.value
  aiGenForm.goal = ''
  showAIDialog.value = true
}

async function doAIGenerate() {
  aiGenLoading.value = true
  try {
    const result = await generateAITutorial({
      knowledge_tag: aiGenForm.knowledge_tag,
      topic: aiGenForm.topic,
      goal: aiGenForm.goal,
    })
    showAIDialog.value = false
    // C5：库中已有同标签的 AI 生成教程时后端直接复用（不调大模型），提示要如实区分
    ElMessage.success(result.existing ? '已生成（库中已有，本次未调用大模型）' : 'AI 教程已生成！')
    tutorialMeta.value = {
      source_type: 'ai_generated',
      tutorial_id: result.tutorial_id,
      parent_id: null,
      generated_at: result.generated_at || null,
      profile_snapshot: parseSnapshot(result.profile_snapshot),
      profile_drift: false,
    }
    learnDialogTitle.value = result.title
    currentDoc.value = { knowledge_tag: aiGenForm.knowledge_tag, title: result.title, source_type: 'ai_generated' }
    savedContent.value = result.content || ''
    editContent.value = savedContent.value
    learnDialogContent.value = renderMarkdown(result.content)
    learnDialogLoading.value = false
    materialMissing.value = false
    await afterContentRerender()
    // 目录里该篇的来源标签要同步为「AI 生成」
    try { await refreshTree() } catch (_) { /* 目录刷新失败不影响已生成的正文 */ }
  } catch (e) {
    ElMessage.error('AI 生成失败: ' + (e.response?.data?.message || e.message))
  } finally {
    aiGenLoading.value = false
  }
}

/** #31：按最新画像强制重新生成当前 AI 教程（后端 force=true 绕过 C5 复用） */
async function regenerateTutorial() {
  const tag = currentDoc.value?.knowledge_tag
  if (!tag) return
  try {
    await ElMessageBox.confirm(
      '将按你当前最新的学习状态重新生成该教程，并覆盖旧的 AI 生成版本。确定？',
      '按最新状态重新生成',
      { confirmButtonText: '重新生成', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消，保持现状
  }
  regenLoading.value = true
  try {
    const result = await generateAITutorial({
      knowledge_tag: tag,
      topic: learnDialogTitle.value || currentDoc.value?.title || tag,
      goal: '',
      force: true,
    })
    ElMessage.success('已按最新状态重新生成')
    tutorialMeta.value = {
      source_type: 'ai_generated',
      tutorial_id: result.tutorial_id,
      parent_id: null,
      generated_at: result.generated_at || null,
      profile_snapshot: parseSnapshot(result.profile_snapshot),
      profile_drift: false,
    }
    learnDialogTitle.value = result.title
    savedContent.value = result.content || ''
    editContent.value = savedContent.value
    learnDialogContent.value = renderMarkdown(result.content)
    materialMissing.value = false
    await afterContentRerender()
    try { await refreshTree() } catch (_) { /* 目录刷新失败不影响已生成的正文 */ }
  } catch (e) {
    ElMessage.error('重新生成失败: ' + (e.response?.data?.message || e.message))
  } finally {
    regenLoading.value = false
  }
}

/** #31 教程随学习动态演化：只重算个性化导读（正文稳定复用，不调用大模型） */
async function evolveTutorial() {
  const tag = currentDoc.value?.knowledge_tag
  if (!tag) return
  evolveLoading.value = true
  try {
    const result = await evolveTutorialApi({ knowledge_tag: tag })
    ElMessage.success(result.message || '已随最新学习状态更新个性化导读')
    tutorialMeta.value = {
      ...tutorialMeta.value,
      tutorial_id: result.tutorial_id,
      generated_at: result.generated_at || tutorialMeta.value.generated_at,
      profile_snapshot: parseSnapshot(result.profile_snapshot),
      profile_drift: false,
    }
    savedContent.value = result.content || ''
    editContent.value = savedContent.value
    learnDialogContent.value = renderMarkdown(result.content)
    await afterContentRerender()
  } catch (e) {
    ElMessage.error('演化失败: ' + (e.response?.data?.message || e.message))
  } finally {
    evolveLoading.value = false
  }
}

/** 删除用户版本后重新加载当前文档；若该文档已不在目录中则回到首篇 */
async function reloadAfterDelete() {
  const tag = currentDoc.value?.knowledge_tag
  tutorialMeta.value = { source_type: 'seed', tutorial_id: null, parent_id: null }
  try {
    await refreshTree()
  } catch (_) { /* 目录刷新失败不阻塞正文重载 */ }
  const target = flatDocs.value.find(doc => doc.knowledge_tag === tag) || flatDocs.value[0]
  if (target) await loadDocument(target)
}

async function restoreSeedTutorial() {
  try {
    await ElMessageBox.confirm('将放弃你的修改，恢复为系统预置版本。确定？', '恢复原始版本', { type: 'warning' })
  } catch {
    return // 用户取消，保持现状
  }
  try {
    await deleteTutorial(currentDoc.value.knowledge_tag)
    ElMessage.success('已恢复为系统预置版本')
    await reloadAfterDelete()
  } catch (e) {
    ElMessage.error('恢复失败')
  }
}

async function deleteCustomTutorial() {
  try {
    await ElMessageBox.confirm('将删除此 AI 生成的教程。确定？', '删除教程', { type: 'warning' })
  } catch {
    return // 用户取消，保持现状
  }
  try {
    await deleteTutorial(currentDoc.value.knowledge_tag)
    ElMessage.success('已删除')
    await reloadAfterDelete()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
.learning-docs-page{display:flex;width:100%;height:100%;min-height:0;flex-direction:column;overflow:hidden;margin:0;max-width:none}
.path-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:54px;margin:0;padding:8px 16px;border-bottom:1px solid #e2e7f1;background:#f8faff}.path-toolbar-copy{min-width:0}.path-toolbar h1{margin:0;color:#17213a;font-size:18px;letter-spacing:-.02em}.path-toolbar-copy span{display:block;margin-top:3px;color:#8a95a8;font-size:11px}.path-actions{display:flex;gap:8px;flex-shrink:0}.path-actions :deep(.el-button){min-height:34px;padding-inline:13px!important}
.course-layout{height:auto;min-height:0;max-height:none;flex:1;display:grid;grid-template-columns:300px minmax(0,1fr);gap:0;align-items:stretch;overflow:hidden}.course-tree-panel,.inline-reader-content{min-height:0;border:0;border-radius:0;background:#fff;box-shadow:none}.course-tree-panel{display:flex;overflow:hidden;flex-direction:column;border-right:1px solid #e2e7f1;background:#f4f2ed}.tree-header{flex:0 0 auto;padding:17px 18px;border-bottom:1px solid #dedbd4;background:#fff}.tree-header>div{display:flex;justify-content:space-between;margin-bottom:2px}.tree-header span{color:#536b40;font-weight:800}.tree-header b{color:#7c889e;font-size:10px}.course-tree{min-height:0;flex:1;overflow:auto;overscroll-behavior:contain;padding:8px}.tree-phase{margin-bottom:6px}.phase-node,.task-node{width:100%;display:flex;align-items:center;border:0;background:transparent;text-align:left;cursor:pointer}.phase-node{gap:9px;padding:11px 9px;border-radius:7px}.phase-node:hover{background:#e9ece5}.phase-index{color:#6f945b;font:800 11px/1 monospace}.phase-copy{flex:1;min-width:0}.phase-copy b,.phase-copy small,.task-node-copy b,.task-node-copy small{display:block}.phase-copy b{color:#34432e;font-size:12px}.phase-copy small{margin-top:3px;color:#8b9386;font-size:10px}.phase-node svg{font-size:11px;transition:transform .2s}.phase-node svg.rotated{transform:rotate(90deg)}.phase-children{position:relative;margin-left:20px;padding-left:12px;border-left:1px solid #d6dbd1}.task-tree-group{margin:2px 0}.task-node{position:relative;gap:9px;padding:9px 8px;border-radius:6px}.task-node:hover,.task-node.active{background:#e5eddf}.task-node.active{box-shadow:inset 3px 0 #79a961}.tree-line-dot{display:grid;width:22px;height:22px;flex:0 0 22px;place-items:center;border-radius:7px;color:#71806a;background:#e2e6dd;font-size:10px;font-weight:800}.task-node.verified .tree-line-dot{color:#fff;background:#5f8557}.task-node-copy{flex:1;min-width:0}.task-node-copy b{overflow:hidden;color:#36435d;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.task-node-copy small{margin-top:3px;color:#8c9487;font-size:9px}.task-article-tree{margin:2px 0 7px 14px;padding:4px 0 5px 9px;border-left:1px dashed #b9c5b1}.task-article-tree button{display:flex;align-items:flex-start;gap:5px;width:100%;padding:5px 6px;border:0;border-radius:4px;color:#6e786b;background:transparent;font-size:9px;line-height:1.45;text-align:left;cursor:pointer}.task-article-tree button:hover,.task-article-tree button.active{color:#45603b;background:#e3eadf}.task-article-tree button.level-3{padding-left:16px}.task-article-tree button span{color:#83a46f;font-weight:800}.tree-outline-loading{display:block;padding:7px;color:#8a9487;font-size:9px}
.reader-content-column{min-width:0;min-height:0;display:flex;overflow:hidden;flex-direction:column;background:#fff}.inline-reader-content{border-right:1px solid #e2e7f1}.reader-page-nav{height:64px;display:grid;align-items:center;gap:12px;flex:0 0 64px;padding:0 18px;border-bottom:1px solid #e1e5ec;background:#fcfcfd}.reader-page-nav-docs{grid-template-columns:minmax(0,1fr) auto minmax(0,1fr)}.reader-doc-position{padding:5px 11px;border-radius:13px;color:#5d6a80;background:#f1f4f8;font-size:10px;font-weight:700;white-space:nowrap}.reader-page-link{min-width:0;padding:6px 8px;border:0;border-radius:6px;background:transparent;text-align:left;cursor:pointer}.reader-page-link.next{text-align:right}.reader-page-link:hover:not(:disabled){background:#f0f3f8}.reader-page-link:disabled{cursor:default;opacity:.35}.reader-page-link small,.reader-page-link b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.reader-page-link small{color:#78995f;font-size:9px}.reader-page-link b{margin-top:3px;color:#4d586d;font-size:10px}.reader-loading{display:grid;min-height:0;place-content:center;flex:1;color:#7b879a;text-align:center}.learn-material-content{min-height:0;flex:1 1 0;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;scroll-behavior:smooth;padding:34px clamp(28px,5vw,68px) 80px;color:#303b53;background:#fff;font-size:15px;line-height:1.85;outline:none}.learn-material-content:focus-visible{box-shadow:inset 0 0 0 2px rgba(83,100,216,.22)}.learn-material-content :deep(h1){margin:0 0 20px;padding-bottom:12px;border-bottom:2px solid #8daf72;color:#111b32;font-size:30px}.learn-material-content :deep(h2){scroll-margin-top:20px;margin:32px 0 13px;padding-left:12px;border-left:4px solid #8daf72;color:#1f2c48;font-size:21px}.learn-material-content :deep(h3){scroll-margin-top:20px;margin:23px 0 10px;color:#5f8557;font-size:17px}.learn-material-content :deep(p){margin:10px 0}.learn-material-content :deep(code:not(pre code)){padding:2px 6px;border-radius:5px;color:#d54f76;background:#f4f0f4}.learn-material-content :deep(table){width:100%;margin:16px 0;border-collapse:collapse;font-size:13px}.learn-material-content :deep(th){padding:10px;border:1px solid #dfe4ed;color:#fff;background:#3d4147;text-align:left}.learn-material-content :deep(td){padding:9px 10px;border:1px solid #e1e5ed}.learn-material-content :deep(blockquote){margin:16px 0;padding:11px 16px;border-left:4px solid #8daf72;background:#f3f7f0;color:#53657a}.learn-material-content :deep(ul),.learn-material-content :deep(ol){padding-left:24px}.learn-material-content :deep(img){max-width:100%;height:auto;margin:14px 0;border:1px solid #e8ecf1;border-radius:8px}
.tutorial-source-badge{display:flex;align-items:center;gap:8px;padding:6px 18px;border-bottom:1px solid #e8ecf1;background:#fafbfd}.tutorial-source-badge .el-button{margin-left:4px;font-size:11px}.source-breadcrumb{overflow:hidden;color:#8a95a8;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.tutorial-profile-note{display:flex;align-items:center;justify-content:space-between;gap:10px;flex:0 0 auto;padding:6px 18px;border-bottom:1px solid #eef1f5;background:#f4f8ff}.tutorial-profile-note .profile-note-text{overflow:hidden;color:#5a6b8c;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.tutorial-profile-note .el-button{padding:0;font-size:11px}.tutorial-drift-note{display:flex;align-items:center;justify-content:space-between;gap:10px;flex:0 0 auto;padding:6px 18px;border-bottom:1px solid #eaf5ec;background:#f2fbf4}.tutorial-drift-note .drift-note-text{overflow:hidden;color:#3f7d52;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.tutorial-drift-note .el-button{padding:0;font-size:11px}.material-missing-alert{flex:0 0 auto;margin:10px 18px 0;border-radius:8px}.material-missing-alert :deep(.el-alert__title){font-size:12px}.material-missing-alert .el-button{margin-top:2px;padding:0}.tutorial-edit-bar{display:flex;align-items:center;gap:8px;padding:4px 18px;border-bottom:1px solid #eef1f5;background:#fcfdfe}.learn-material-editor{min-height:0;flex:1 1 0;display:flex;flex-direction:column;padding:24px clamp(28px,5vw,68px) 24px;overflow-y:auto}.learn-material-editor .tutorial-textarea{flex:1;min-height:400px}.learn-material-editor .tutorial-textarea :deep(textarea){font-family:'JetBrains Mono','Fira Code',monospace;font-size:13px;line-height:1.7;color:#2d3748;background:#fafbfc;border-color:#e2e8f0}.editor-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid #eef1f5}
@media(max-width:1100px){.course-layout{grid-template-columns:270px minmax(0,1fr)}}@media(max-width:900px){.path-toolbar{align-items:flex-start}.path-toolbar-copy span{display:none}.learning-docs-page{height:auto;overflow:visible}.course-layout{height:auto;max-height:none;display:block;overflow:visible}.course-tree-panel{height:360px}.inline-reader-content{height:calc(100dvh - 110px);min-height:600px;margin-top:12px}.learn-material-content{padding:26px 20px 70px}.tutorial-source-badge{flex-wrap:wrap;padding:6px 12px}.tutorial-profile-note,.tutorial-drift-note{flex-wrap:wrap}}
</style>
