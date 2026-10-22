import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { noAuth: true } },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '学习控制台' } },
      { path: 'diagnosis', name: 'Diagnosis', component: () => import('../views/Diagnosis.vue'), meta: { title: '学情自测' } },
      { path: 'diagnosis/report/:id', name: 'DiagnosisReport', component: () => import('../views/DiagnosisReport.vue'), meta: { title: '诊断报告' } },
      { path: 'qa', name: 'QA', component: () => import('../views/QA.vue'), meta: { title: '智能答疑', workspace: true } },
      { path: 'learning-docs', name: 'LearningDocs', component: () => import('../views/LearningDocs.vue'), meta: { title: '学习文档', workspace: true } },
      // 个性化学习路线图·学习地图（技术方案.md §5.8 第一版）
      { path: 'learning-path', name: 'LearningPath', component: () => import('../views/LearningPath.vue'), meta: { title: '学习路线图' } },
      { path: 'task-quiz/:sessionId', name: 'TaskQuiz', component: () => import('../views/TaskQuiz.vue'), meta: { title: '专项练习' } },
      // 编程实验室（三级结构）
      { path: 'code-lab', name: 'ModuleSelect', component: () => import('../views/ModuleSelect.vue'), meta: { title: '编程实验室' } },
      { path: 'code-lab/:moduleId', name: 'TaskList', component: () => import('../views/TaskList.vue'), meta: { title: '关卡列表', workspace: true } },
      { path: 'code-lab/:moduleId/:taskId', name: 'CodeLab', component: () => import('../views/CodeLab.vue'), meta: { title: '实验工作台', fullscreen: true } },
      { path: 'lab-history', name: 'LabHistory', component: () => import('../views/LabHistory.vue'), meta: { title: '编程实验室 · 已完成记录' } },
      { path: 'code-runner', name: 'CodeRunner', component: () => import('../views/CodeRunner.vue'), meta: { title: '代码运行器', workspace: true } },
      { path: 'error-book', name: 'ErrorBook', component: () => import('../views/ErrorBook.vue'), meta: { title: '错题本' } },
      // 学情复盘已并入学习控制台，旧链接（书签 / 浏览器历史）回到控制台，避免打开空白页
      { path: 'analytics', redirect: '/dashboard' },
      { path: 'profile', name: 'Profile', component: () => import('../views/Profile.vue'), meta: { title: '个人中心' } },
    ]
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const STALE_ASSET_RELOAD_PARAM = '__asset_reload'
const STALE_ASSET_PATTERN = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS|Loading CSS chunk|ChunkLoadError/i

function reloadFromFreshShell(target) {
  const url = new URL(target || window.location.href, window.location.origin)

  // The marker prevents a genuinely broken deployment from causing an
  // infinite refresh loop. It is removed as soon as the new route loads.
  if (url.searchParams.has(STALE_ASSET_RELOAD_PARAM)) return false

  url.searchParams.set(STALE_ASSET_RELOAD_PARAM, String(Date.now()))
  window.location.replace(`${url.pathname}${url.search}${url.hash}`)
  return true
}

// Vite emits this event when a deployment replaces a preloaded JS/CSS asset.
// Reload the HTML shell so an already-open tab picks up the new asset hashes.
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault()
  reloadFromFreshShell(window.location.href)
})

// Vue Router reports the same deployment race when a lazy route component is
// imported. Recover the requested route instead of leaving the click inert.
router.onError((error, to) => {
  const message = String(error?.message || error || '')
  if (!STALE_ASSET_PATTERN.test(message)) return
  reloadFromFreshShell(to?.fullPath || window.location.href)
})

// A successful route load proves the current asset set is healthy. Remove the
// one-shot marker without adding another browser-history entry.
router.isReady().then(() => {
  const url = new URL(window.location.href)
  if (!url.searchParams.has(STALE_ASSET_RELOAD_PARAM)) return

  url.searchParams.delete(STALE_ASSET_RELOAD_PARAM)
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
})

router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()

  // 不需要认证的页面直接放行
  if (to.meta.noAuth) {
    next()
    return
  }

  // 无本地 token → 强制去登录
  if (!userStore.token) {
    next('/login')
    return
  }

  // 有 token 但未验证过 → 调后端校验接口确认有效性
  if (!userStore._verified) {
    try {
      await userStore.verifyToken()
      userStore._verified = true
    } catch (e) {
      // token 无效或过期 → 清理并跳转登录
      userStore.logout()
      next('/login')
      return
    }
  }

  // 已登录用户访问 /login → 重定向到主页
  if (to.path === '/login') {
    next('/dashboard')
    return
  }

  next()
})

export default router
