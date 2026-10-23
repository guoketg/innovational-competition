# CLAUDE.md

## 项目概述
智码助学 — 面向高校计算机学科（数据结构与算法等）实训的个性化、伴随式 AI 教学软件。

## 与用户沟通的要求（必须遵守）
- **说人话**：需要用户拍板/选择/确认时，必须让没有技术背景的人一眼看懂。
- 先用一句话说明「这个问题在问什么」；每个选项直接写「选它会发生什么」（后果），不要用抽象名词。
- 禁止自造术语（如「测评强制维度」「冷启动兜底」「编排算子」「旁挂」）；非用不可时紧跟一句大白话解释。
- 自检：如果一句话会让用户再问「这是什么意思」，就重写。
- 正例：✅「用户是否必须做测评才能生成学习路径？
  A. 必须做：不做测评就不给生成路径（判断更准，但可能劝退新用户）
  B. 可以跳过：按注册信息先估水平（流程更顺，但可能不准，之后自动校正）」

## 🚫 禁用专家工具（AdvisorTool，必须遵守）
- 禁止调用 AdvisorTool（界面上的「专家/顾问」评审工具）：它会让每次回复多等一轮，输出明显变慢。
- 遇到报错、方案变更、用户不满等情况，直接自己分析并继续处理，不要请专家评审。
- 只有用户明确要求「请专家看一下」时才允许调用。

## 技术栈
- 前端：Vue3 + Vite + Element Plus + ECharts（Docker 80 / 本地 dev 5174）
- 后端：Python FastAPI + SQLite（Docker 容器内 8000→本机 8001；本地开发 8000）
- AI：DeepSeek API；容器化：Docker Compose

## ⚡ 代码修改后自动部署（必须执行）
每次修改代码后必须执行 `docker compose up -d --build`，因为前端是 `npm run build` → nginx 静态构建、后端是源码复制，不重建不生效；用户看的是 http://localhost:80 的 Docker 版本，不是 dev server。

**Docker 未启动时自己启动，不要跳过部署**：先 `docker info` 自检，报 dockerDesktopLinuxEngine 连接失败则：
```powershell
$exe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (-not (Test-Path $exe)) { $exe = Join-Path (Split-Path (Split-Path (Get-Command docker).Source)) "Docker Desktop.exe" }
Start-Process $exe
for ($i = 0; $i -lt 36; $i++) { docker info *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep -Seconds 5 }
```
就绪后立即 build；3 分钟仍未就绪，明确告知用户「Docker Desktop 启动失败，需手动启动」并给出原始报错，不要静默完成。

## 🧪 代码修改后自动测试（必须执行）
部署后必须自动用 Playwright MCP 做端到端测试，无需用户要求：
1. 部署完成等待 ~15s
2. 打开 `http://localhost:80`，用 demo / demo123 登录
3. 逐一验证本次修改涉及的功能点
4. 检查控制台 JS 错误
5. 报告结果（通过/失败/控制台错误）

## Python 运行环境约束（必须遵守）
- **禁止使用系统 PATH 里的全局 python** 跑本项目脚本、测试、数据处理。
- 一律用项目 venv 或 Docker：`& "F:\code\MyPython\computer-cross-education\tiaozhanbei\venv\Scripts\python.exe" script.py`
- 服务类（后端/FastAPI）优先 `docker compose up -d --build`。

## 启动方式（必须优先使用 Docker）
- **Docker（推荐）**：`docker compose up -d --build` → 前端 http://localhost:80，后端 http://localhost:8001，文档 http://localhost:8001/docs
- **本地开发（仅 Docker 不可用时）**：`source venv/Scripts/activate`，`pip install -r backend/requirements.txt`，`cd backend && python main.py`；前端 `cd frontend && npm install && npm run dev -- --port 5174`

## RAG 知识库引擎

### 嵌入模型（云端 API，无需本地 GPU）
| 后端 | 模型 | 维度 | 场景 |
|------|------|:---:|------|
| SiliconFlow | `BAAI/bge-large-zh-v1.5` | 1024 | 生产（Docker 默认，`EMBEDDING_RUNTIME_MODE=siliconflow`） |
| 阿里云 DashScope | `text-embedding-v3` | 1024 | 备用（用户自配 Key） |

- 用户在「个人中心 → AI大模型配置」配置嵌入 API Key。
- 向量库：集合 `rag_docs_cached-bge-large-zh-v1.5`（SiliconFlow）/ `rag_docs_cached-dashscope-text-embedding-v3`（历史）；存储 `backend/data/chroma_db/`；共 4887 块（PDF 2402 + Markdown 1885 + Q&A 600）。
- 本地 venv 位于项目根 `venv/`，核心依赖 `chromadb`、`dashscope`、`openai`。
- 构建：`python backend/rag_builder.py --provider siliconflow --api-key <Key>`（DashScope 用 `--api-key <Key>`）。构建后 QA 自动检索；未配置 Key 时正常回答但无增强并提示配置。
- 接口：`GET /api/rag/status`、`POST /api/rag/search?q=xxx`；回答下方展示 📚 参考来源（PDF 页码 / Markdown 章节 / 题库知识点）。
- 数据源：Q&A 题库 ~600 条，`backend/data/dataset/`。教材 PDF 与 Markdown 已不随仓库提供，需要时放回 `pdf/`、`learning_materials/` 再跑 `rag_builder.py`。

### ⚠️ API Key 使用规则（极重要，违反将泄露 Key 并产生账单）
- **绝对禁止把任何真实 API Key 写进代码或配置文件**（.py/.js/.vue/.json/.yml/.env）；禁止用硬编码默认 Key 兜底。
- 未配置 = 功能不可用，只给明确指引（如「请在个人中心配置 xxx API Key」）。
- Key 只能由用户在前端界面填写：LLM 走「个人中心 → DeepSeek 快速配置」，嵌入走「个人中心 → 知识库嵌入 API Key 快速配置」。
- 本地测试：用 Playwright 在浏览器输入，或用不提交的环境变量。

### 参考项目
SuperMew（agentic RAG）：`F:/code/MyPython/SuperMew-main/` — 三层分块+自动合并、混合检索+RRF、LangGraph pipeline、Step-back+HyDE 查询扩展、Jina Reranker。

## 数据库
- 仅用 SQLite：`backend/data/learning_platform.db`（路径见 `backend/config.py` 的 `DATABASE_PATH`）。
- Docker 持久化：volume `student_backend_data` → `/app/data`，`docker compose down` 不丢数据；远程 PostgreSQL 支持已于 2026-10-20 全部移除。
- 连接层：`backend/db.py` 提供 `get_db()`（原生 sqlite3，开外键）与 `json_load()`。
- 运维示例：`docker exec ai-learning-backend python -c "import sqlite3; conn=sqlite3.connect('/app/data/learning_platform.db'); ..."`；本地开发直接改 `backend/data/learning_platform.db`（用项目 venv）。
- **两份库不同**：Docker volume 内一份、本地 `backend/data/learning_platform.db` 一份，别混着看。

## 讲解请求的可视化约束
- 讲解/解释类请求默认**不加载**可视化模块（dynamic-ui / Inline Visuals / PureShowWidget），直接用文字 + 代码引用作答。
- 确需可视化时先问「可视化更容易理解，你需要补充吗？」，用户同意后再渲染。

## 关键决策记录

### 2026-10-22：学习文档改用 Mermaid 绘图（替代失效外链图片）
- 404 的 `/runoob-images/*.png` 删除后教程无图，改用 Mermaid（浏览器现场绘制），先覆盖 10 篇可见 `dsa-*` 文档。
- `frontend/src/composables/useCodeBlockRenderer.js` 识别 `mermaid` 输出裸 `<div class="mermaid">`；`frontend/src/views/LearningDocs.vue` 调 `renderMermaidIn()` 并加容器样式。
- 新增文档配图：教程 Markdown 正文里写 `mermaid` 语言的围栏代码块即可（flowchart / sequenceDiagram），前端无需改；tag 必须是 `knowledge_tags.json` 里的可见 tag。
- 已验证 10 篇均正常渲染、无控制台报错。

### 2026-10-22：清理学习文档失效图片引用
- `tutorial_seed.json` 42 篇/120 处引用从未提供的 `/runoob-images/*.png`（原图源也已 404），直接删除、不做占位图。
- 同步 `backend/data/tutorial_seed.json` 与 `dsa_tutorial_seed.json`，并单独 SQL 更新两份 SQLite 的 `tutorial_documents.content`（种子改动不会覆盖已有行）。

### 2026-10-21：意图识别评测补齐（100 条 + 四方对比）
- 新增 `backend/data/eval/intent_judges_cases.jsonl`（learning 70 / tool_use 15 / disguised 15）与 `backend/scripts/evaluate_intent_judges.py`，报告 `backend/data/eval/intent_judges_report.json`。
- Key 走环境变量（`EVAL_API_KEY`/`EVAL_BASE_URL`/`EVAL_MODEL`、`OPENROUTER_API_KEY`），缺 Key 的臂自动跳过。
- 实测 n=100：rule 0.97/0.80/0ms；NLP 0.81/0.82/1.2ms；DeepSeek 0.95/0.96/770ms；Jev 1.00/0.94/1252ms。
- 判据在**同批用例**上调出（in-sample），PPT/论文必须注明；Jev 端到端 1.25s **不快于** DeepSeek 0.77s，不得宣称「Jev 更快」；rule/nlp 为本地时延，与云端不可同轴比较。
- `scikit-learn` 已加入 `backend/requirements.txt`（仅评测用）。

### 2026-10-20：全面切回 SQLite，移除 PostgreSQL
- `backend/db.py` 重写为纯 SQLite；`database.py` 删 PG 分支与 `_seed_pg_data()`；`docker-compose.yml`/`.env.example` 删 `DATABASE_URL`；requirements 删 `psycopg2-binary`。
- 保留 `conversation_export_service.py` 的 `postgres://` 打码逻辑（隐私脱敏）与 `docs/` 历史文档。
- 远程 PG 历史数据不再被读取，如需找回只能临时恢复旧代码导出。

### 2026-10-18：内容通道护栏（防泄题）下线
- 断开 4 个调用点：`qa_router.py`、`qa_service.py`、`lab_workspace_service.py`（流式/非流式两条链路）；行为通道（工具代改护栏）不变。
- `answer_guard_service.py`、其单测与 `backend/scripts/` 评测脚本保留，可回滚/离线评测；`evaluate_release()` 现在只作为行为通道免提示加速。
- 理由：与 DPO「用户发起 → 给；AI 主动 → 不给」的请求轴冲突；项目评测口径本就把「用户要答案却只给提示」判为过度拦截；5562 条偏好样本中 48 条合理的「用户要答案 + 给答案」会被误拦。
- 答辩口径：改为「拦截 AI **未经请求**主动泄题」，不再说「系统拦截代码」；历史基线（过度拦截率 0.1429）保留但不再产生新日志。

## 重要注意事项
- `backend/docker-entrypoint.sh` 必须是 **LF** 行尾符，否则容器报 `Illegal option -`。
- Demo 账号：`demo` / `demo123`。
- 后端端口映射 `127.0.0.1:8001:8000`；镜像体积大，改代码必须 rebuild。
