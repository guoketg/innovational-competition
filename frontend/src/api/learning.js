import request from './request'

// 学习路径生成需要较长时间（LLM生成大JSON），使用独立超时配置
export const generateLearningPath = (data) =>
  request.post('/learning/path/generate', data, { timeout: 300000 })  // 5分钟超时
/** 记录学习访问（轻量，不计入loading） */
export const recordStudyVisit = () => request.post('/learning/visit').catch(() => {})
export const getLearningPath = () => request.get('/learning/path')
/** 个性化学习路线图·学习地图（站点 + 先修依赖边 + 掌握度分档 + 进度） */
export const getLearningRoadmap = () => request.get('/learning/path/roadmap')
/** 知识图谱（§5.8 第二版）：未生成时返回专家先修骨架 */
export const getKnowledgeGraph = () => request.get('/learning/path/graph')
/** 调用 LLM 构建知识图谱（知识点描述 + 先修/相似双关系），耗时较长 */
export const generateKnowledgeGraph = () =>
  request.post('/learning/path/graph/generate', {}, { timeout: 300000 })  // 5分钟超时
export const deleteLearningPath = () => request.delete('/learning/path')
/** 新用户 5 道快速测评：题目带课程知识点标签，用于决定路线起点与顺序 */
export const startQuickQuiz = () => request.post('/learning/path/quick-quiz')
export const submitQuickQuiz = (data) => request.post('/learning/path/quick-quiz/submit', data)
export const generateDiagnosticTest = (data) => request.post('/learning/path/diagnostic-test', data)
export const updatePathProgress = (data) => request.put('/learning/path/progress', data)
export const getDailyTasks = (date) => request.get('/learning/tasks', { params: { date } })
export const completeTask = (data, date) => request.put('/learning/tasks/complete', data, { params: { date } })
export const getErrorBook = (page = 1) => request.get('/learning/error-book', { params: { page } })
export const reviewError = (id) => request.put(`/learning/error-book/${id}/review`)
export const reviewSessionErrors = (sessionId) => request.put(`/learning/error-book/session/${sessionId}/review-all`)
export const getErrorSessions = () => request.get('/learning/error-book/sessions')
export const getErrorsBySession = (sessionId, page = 1) => request.get(`/learning/error-book/session/${sessionId}`, { params: { page } })
export const getOrphanErrors = (page = 1) => request.get('/learning/error-book/orphan', { params: { page } })
export const deleteSessionErrors = (sessionId) => request.delete(`/learning/error-book/session/${sessionId}`)
export const deleteOrphanErrors = () => request.delete('/learning/error-book/orphan')
export const batchDeleteErrors = (ids) => request.post('/learning/error-book/batch-delete', { ids })
/** 错题重测：把错题组装成一份可提交的重测卷 */
export const generateReviewQuiz = (data) => request.post('/learning/error-book/retest', data)

export const generateTaskQuiz = (data) => request.post('/learning/task-quiz', data)
export const getLearningResource = (knowledge) => request.get('/learning/resource', { params: { knowledge } })
/** 学习文档目录（按 module 分组的全部教程） */
export const getLearningDocuments = () => request.get('/learning/documents')

// 教程文档管理
export const saveTutorial = (knowledgeTag, data) =>
  request.put(`/learning/tutorial/${encodeURIComponent(knowledgeTag)}`, data)

export const deleteTutorial = (knowledgeTag) =>
  request.delete(`/learning/tutorial/${encodeURIComponent(knowledgeTag)}`)

export const generateAITutorial = (data) =>
  request.post('/learning/tutorial/generate', data)

/** #31 教程随学习动态演化：只重算个性化层，正文稳定复用，不调用大模型 */
export const evolveTutorial = (data) =>
  request.post('/learning/tutorial/evolve', data)
