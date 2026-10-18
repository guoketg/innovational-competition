# CLAUDE.md

## 项目概述
智码助学 — 面向高校计算机学科（数据结构与算法等）实训的个性化、伴随式 AI 教学软件。

## 与用户沟通的要求（必须遵守）

- **说人话。** 任何需要用户拍板、选择、确认的内容，必须让没有技术背景的人一眼看懂。
- 具体要求：
  1. 先用一句话说明「这个问题到底在问什么」。
  2. 每个选项直接写「选它会发生什么」，即用户能看到的后果，不要用抽象名词代替具体动作。
  3. 禁止自造术语（如「测评强制维度」「冷启动兜底」「编排算子」「旁挂」）。确实必须使用时，紧跟一句大白话解释。
  4. 不要一次抛出一堆术语让用户自己拼意思。
- 反例（看不懂）：
  ❌「测评强制维度：强制 vs 可选」
- 正例（能看懂）：
  ✅「用户是否必须做测评才能生成个性化学习路径？
  A. 必须做：不做测评就不给生成路径（判断更准，但可能把新用户劝退）
  B. 可以跳过：跳过时按注册信息先估一个水平（流程更顺，但可能不准，之后会自动校正）」
- 自检：如果一句话会让用户再问一次「这是什么意思」，就说明没写合格，必须重写。

## 技术栈
- 前端：Vue3 + Vite + Element Plus + ECharts（Docker 端口 80 / 本地开发端口 5174）
- 后端：Python FastAPI + PostgreSQL（远程服务器）；Docker 容器内 8000，映射到本机 8001；本地开发 8000
- AI：DeepSeek API
- 容器化：Docker Compose

## ⚡ 代码修改后自动部署（必须执行）

**每次修改代码后，必须自动执行以下命令让用户看到效果：**
```bash
docker compose up -d --build
```
- 原因：Docker 前端是 `npm run build` → nginx 静态构建，后端是 Python 源码复制。源码修改必须重建镜像才能生效。
- 用户访问 `http://localhost:80` 看到的是 Docker 版本的代码，不是本地 dev server。

## 🧪 代码修改后自动测试（必须执行）

**每次代码修改并部署后，必须自动使用 Playwright MCP 进行端到端测试，无需用户反复要求。**
- 使用 Playwright MCP 浏览器工具（`mcp__playwright__*`）进行测试
- 测试范围应覆盖本次修改涉及的所有功能点
- 测试流程：
  1. `docker compose up -d --build` 部署完成后等待 ~15s 让容器初始化
  2. 导航到 `http://localhost:80`，使用 demo 账号登录（demo / demo123）
  3. 针对本次修改的功能逐一验证
  4. 检查浏览器控制台是否有 JavaScript 错误
  5. 报告测试结果（通过/失败/控制台错误）

## Python 运行环境约束（必须遵守）
- **禁止使用全局 Python 环境**（系统 PATH 里的 `python`）运行本项目的任何脚本、测试或数据处理命令。
- 一律使用**项目级虚拟环境**或 Docker：
  - 项目 venv（当前唯一已安装依赖的本地环境）：`F:\code\MyPython\computer-cross-education\tiaozhanbei\venv\Scripts\python.exe`
  - 形式示例：`& "F:\code\MyPython\computer-cross-education\tiaozhanbei\venv\Scripts\python.exe" script.py`
  - 服务类（后端/FastAPI）：优先 `docker compose up -d --build`
- 暂时先统一用项目的虚拟环境；后续引入 Docker 跑脚本时再切换。

## 启动方式（必须优先使用 Docker）

### 方式一：Docker 一键启动（推荐，始终优先使用）
```bash
docker compose up -d --build
```
- 前端: http://localhost:80
- 后端: http://localhost:8001 （注意 Docker 映射到 8001）
- API 文档: http://localhost:8001/docs

### 方式二：本地开发（仅在 Docker 不可用时使用）

**激活虚拟环境（必须）：**
```bash
# Windows Git Bash:
source venv/Scripts/activate

# 安装依赖：
pip install -r backend/requirements.txt

# 启动后端：
cd backend && python main.py
```
前端：
```bash
cd frontend && npm install && npm run dev -- --port 5174
```

## RAG 知识库引擎

### 嵌入模型（云端 API）

| 后端 | 模型 | 维度 | 使用场景 |
|------|------|:---:|------|
| SiliconFlow | `BAAI/bge-large-zh-v1.5` | 1024 | 生产环境（推荐） |
| 阿里云 DashScope | `text-embedding-v3` | 1024 | 备用（需用户配置 API Key） |

- 所有嵌入均通过云端 API 调用，无需本地 GPU
- Docker 默认使用 SiliconFlow（`EMBEDDING_RUNTIME_MODE=siliconflow`）
- 用户可在「个人中心 → AI大模型配置」中配置嵌入 API Key

### 当前向量库状态
- 集合：`rag_docs_cached-bge-large-zh-v1.5`（SiliconFlow）/ `rag_docs_cached-dashscope-text-embedding-v3`（DashScope 历史）
- 存储：`backend/data/chroma_db/`
- 总计 4887 个文档块：PDF 2402 + Markdown 1885 + Q&A 600

### 虚拟环境
- 路径：项目根目录 `venv/`（本地开发唯一已装好依赖的环境）
- 核心 RAG 依赖：`chromadb`, `dashscope`, `openai`
- 所有 Python 操作必须在激活虚拟环境后执行

### RAG 一键构建
```bash
# 激活 venv
source venv/Scripts/activate

# DashScope 云端模式（需用户自行申请 API Key）
python backend/rag_builder.py --api-key <你的DashScope_API_Key>

# SiliconFlow 云端模式（推荐）
python backend/rag_builder.py --provider siliconflow --api-key <你的SiliconFlow_API_Key>
```
构建后：
- QA 页面提问自动触发 RAG 检索（前提：用户已在个人中心配置嵌入 API Key）
- 未配置时 QA 正常回答，但无知识库增强，并提示用户配置 text-embedding-v3 API Key
- 回答下方展示 📚 参考来源（PDF 页码 / Markdown 章节 / 题库知识点）
- API: `GET /api/rag/status`, `POST /api/rag/search?q=xxx`

### ⚠️ API Key 使用规则（极其重要 — 违反将导致 Key 泄露和账单损失）

**🚫 禁止事项：**
- **绝对禁止将任何真实 API Key 直接写入代码文件**（包括 .py / .js / .vue / .json / .yml / .env）
- 绝不使用硬编码的默认 Key 来兜底——未配置 = 不可用，清晰提示即可
- 测试用的 Key 只能通过浏览器 UI 输入（Playwright），不能写入任何源代码

**✅ 正确做法：**
- 所有 API Key 必须由用户通过前端界面自行输入配置
- 未配置 → 功能不可用 → 显示明确指引（如「请在个人中心配置 xxx API Key」）
- LLM 对话 Key：`个人中心 → DeepSeek 快速配置` 中填写
- 嵌入 Key：`个人中心 → 知识库嵌入 API Key 快速配置` 中填写 DashScope text-embedding-v3
- 本地测试：通过 Playwright 在浏览器中输入 Key，或使用环境变量（不提交）

### RAG 数据源
| 数据源 | 数量 | 路径 |
|--------|:---:|------|
| Q&A 题库 | ~600 条 | `backend/data/dataset/` |

> 教材 PDF 与 Markdown 学习资料已不再随仓库提供；如需扩充知识库，可自行放回 `pdf/`、`learning_materials/` 后运行 `backend/rag_builder.py`。

### 参考项目
- SuperMew（agentic RAG）：`F:/code/MyPython/SuperMew-main/`
  - 三层分块 + 自动合并、混合检索 + RRF 融合、LangGraph agentic RAG pipeline
  - 查询扩展（Step-back + HyDE）、Jina Reranker 精排

## 数据库

### 生产环境：PostgreSQL（远程服务器）
- **Docker 容器内自动使用远程 PostgreSQL**，通过 `DATABASE_URL` 环境变量配置
- 连接地址：通过项目根目录 `.env` 的 `DATABASE_URL` 注入，文档和源码中不得保存真实凭据。
- 本地 SQLite 仅在不设置 `DATABASE_URL` 时作为回退（`backend/db.py` 自动检测）
- **本地 SQLite 已被弃用**，所有数据操作应针对 PostgreSQL

### 数据库运维
- 查询/修改数据：通过 Docker 容器执行 Python 脚本连接 PostgreSQL
  ```bash
  docker exec ai-learning-backend python -c "
  import psycopg2, os
  conn = psycopg2.connect(os.environ['DATABASE_URL'])
  # 执行 SQL ...
  conn.close()
  "
  ```
- `docker compose down` 不会影响远程 PostgreSQL 数据
- 本地 volume `backend_data` 仅用于临时缓存文件

## 讲解请求的可视化约束
- 用户提出**讲解/解释类请求**时，默认**不要**加载可视化模块（dynamic-ui / Inline Visuals / PureShowWidget），直接以文字 + 代码引用作答。
- 如 agent 认为可视化确实更有助于理解，可**先询问**用户："可视化更容易理解，你需要补充吗？"，经用户同意后再渲染，禁止默认直接启动可视化。

## 关键决策记录

### 2026-10-18：内容通道护栏（防泄题护栏）下线

**决定**：断开防泄题护栏在运行时的全部调用，AI 输出的代码不再做「与参考答案文字重合」拦截。行为通道（工具代改护栏）保持不变。

- **动的 4 个调用点**：`backend/routers/qa_router.py`（流式问答）、`backend/services/qa_service.py`（非流式问答）、`backend/services/lab_workspace_service.py`（关卡导师的流式与非流式两条链路，含轮末兜底复检与「重生成再检」）。
- **未删文件**：`backend/services/answer_guard_service.py` 与其单测 `backend/tests/test_answer_guard_service.py` 完整保留，供随时回滚与离线评测复用；`backend/scripts/` 下的内容通道评测脚本同样保留（历史基线数据不丢）。
- **保留的一处复用**：关卡导师里的 `evaluate_release()`（释放阀）现在只作为**行为通道的免提示加速通道**喂给 `decide_channel(valve_released=...)`，不再影响任何内容输出。

**下线理由（用户决策）**：

1. **与 DPO 的「请求轴」原则冲突**。DPO 训练模型「用户发起 → 给；AI 主动 → 不给」，而内容护栏不看用户意图、只比文字重合——用户明确索要答案时仍被拦。用户原话：「代码要不要是用户发起，我们的系统是没资格拦截代码的。」
2. **项目自己的评测口径本就否定这种做法**。`backend/scripts/evaluate_direct_code_rate.py` 的标注规则写明：`give_hint 且诉求为答案/改码 → 该拦(over_block 过度拦截)`，即「用户要答案、AI 只给提示」被判为错误。
3. **有实证**：扫描 `backend/data/dpo/` 全部 5562 条（chosen/rejected 两臂）后，**48 条「用户明确要答案/要改码 + chosen 给答案」的偏好样本会被护栏判为违规**；作为对照，用户只要提示（hint_only）时被拦的只有 2 条。

**连带影响（需同步口径）**：PPT 创新点 2（检测与在线判定）、创新点 3（基于多维证据的时机干预）失去运行时实现，答辩口径应改为「拦截 AI **未经请求**主动泄题」而非「系统拦截代码」，或另作调整；内容通道基线指标（如过度拦截率 0.1429）保留为历史数据，不再由运行时产生新日志。

## 重要注意事项
- `backend/docker-entrypoint.sh` 必须是 **LF** 行尾符（不是 CRLF），否则容器启动报 `Illegal option -`
- Demo 账号：`demo` / `demo123`
- Docker Compose 将后端端口映射为 `127.0.0.1:8001:8000`
- Docker 构建镜像体积大（含 Python 依赖），修改代码后必须 rebuild
- **修改数据库配置（如模型名称）必须操作远程 PostgreSQL，不能改本地 SQLite**
