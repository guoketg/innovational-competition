import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, register as registerApi, getProfile, updateProfile, verifyToken as verifyTokenApi } from '../api/auth'

// 历史遗留修复：pinia-plugin-persistedstate 曾与本文件的手动存储共用 'user' 这个 key，
// 每次刷新都会把「{token, user} 整包快照」当作用户对象再包一层，导致 user.user.user… 自嵌套。
// 该 store 的 persist 已移除（token/user 均已手动持久化），这里读取时顺手解包并写回干净值。
function _loadStoredUser() {
  try {
    let parsed = JSON.parse(localStorage.getItem('user') || 'null')
    while (parsed && typeof parsed.token === 'string' && parsed.user && typeof parsed.user === 'object') {
      parsed = parsed.user
    }
    if (parsed) localStorage.setItem('user', JSON.stringify(parsed))
    return parsed
  } catch {
    return null
  }
}

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(_loadStoredUser())
  const _verified = ref(false) // token 是否已被后端校验通过

  const isLoggedIn = computed(() => !!token.value && _verified.value)
  const learningStage = computed(() => user.value?.learning_stage || '入门')

  /** 调后端接口校验 token 是否有效 */
  async function verifyToken() {
    if (!token.value) throw new Error('无 token')
    await verifyTokenApi() // 后端 /auth/verify 无效 token 会 401
    _verified.value = true
  }

  async function login(username, password) {
    const data = await loginApi({ username, password })
    token.value = data.access_token
    user.value = data.user
    _verified.value = true // 刚登录的 token 肯定有效
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    return data
  }

  async function register(form) {
    // 注册成功不自动登录，仅调用 API
    const data = await registerApi(form)
    return data
  }

  async function fetchProfile() {
    const data = await getProfile()
    user.value = data
    localStorage.setItem('user', JSON.stringify(data))
  }

  async function updateUser(form) {
    await updateProfile(form)
    await fetchProfile()
  }

  function logout() {
    token.value = ''
    user.value = null
    _verified.value = false
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, _verified, isLoggedIn, learningStage, login, register, verifyToken, fetchProfile, updateUser, logout }
})
