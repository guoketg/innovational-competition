import request from './request'

// 学习路径生成需要较长时间（LLM生成大JSON），使用独立超时配置
export const generateLearningPath = (data) =>
  request.post('/learning/path/generate', data, { timeout: 300000 })  // 5分钟超时
/** 记录学习访问（轻量，不计入loading） */
export const recordStudyVisit = () => request.post('/learning/visit').catch(() => {})
export const getLearningPath = () => request.get('/learning/path')
/** 个性化学习路线图·学习地图（站点 + 先修依赖边 + 掌握度分档 + 进度） */
export const getLearningRoadmap = () => request.get('/learning/path/roadmap')
/** 知识图谱（§5.8 第二版）：未生成时返回专家先修骨架
 * scope = 'mine' 只返回与自己学习状态相关的节点（会随学习进度生长）；'full' 返回完整课程图谱
 */
export const getKnowledgeGraph = (scope = 'mine') =>
  request.get('/learning/path/graph', { params: { scope } })
/** 调用 LLM 构建知识图谱（知识点描述 + 先修/相似双关系），耗时较长 */
export const generateKnowledgeGraph = () =>
  request.post('/learning/path/graph/generate', {}, { timeout: 300000 })  // 5分钟超时
/** 用当前知识图谱重排学习路径（保留已完成的进度） */
export const applyKnowledgeGraphToPath = () =>
  request.post('/learning/path/graph/apply', {}, { timeout: 120000 })
/** 知识图谱测评：结构 / 边质量 / 路径影响 / 证据覆盖 四维评分与明细 */
export const getKnowledgeGraphEvaluation = () =>
  request.get('/learning/path/graph/evaluation', { timeout: 120000 })
/** 人工审核一条 AI 推断的知识关系：action = accept / reject */
export const reviewKnowledgeGraphEdge = (data) =>
  request.post('/learning/path/graph/edges/review', data)
/** 查某个知识点的 N 跳邻居：ref 支持 tag 或知识点名称 */
export const getGraphNeighbors = (params) =>
  request.get('/learning/path/graph/neighbors', { params })
/** 查两个知识点之间的最短路径 */
export const getGraphPath = (params) =>
  request.get('/learning/path/graph/path', { params })
/** 知识图谱版本快照列表（生成 / 审核 / 回滚都会留一份） */
export const getGraphVersions = (params = {}) =>
  request.get('/learning/path/graph/versions', { params })
/** 把知识图谱回滚到某个版本快照 */
export const restoreGraphVersion = (versionId, data = {}) =>
  request.post(`/learning/path/graph/versions/${versionId}/restore`, data)
/** 可选课程清单（换课程不用改代码） */
export const getGraphCourses = () =>
  request.get('/learning/path/graph/courses')
export const deleteLearningPath = () => request.delete('/learning/path')
/** 快速测评：默认 5 道；传 knowledge_tag 可对单个知识点补测 */
export const startQuickQuiz = (params = {}) =>
  request.post('/learning/path/quick-quiz', null, { params })
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
