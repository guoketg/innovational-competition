# 智码助学 — 个性化 AI 教学软件

> 面向高校计算机学科（数据结构与算法等）实训的 AI 教学软件。

```
智码助学/
├── frontend/           # 🖥️ Vue 3 + Element Plus (nginx, 端口 80)
├── backend/            # ⚙️ Python FastAPI (端口 8001)
├── docs/               # 📄 项目文档
└── README.md
```

## 功能特性

- **AI 对话答疑**：学生 ↔ AI 流式对话（SSE 实时输出），苏格拉底式分层引导 + 答案释放时机约束
- **CodeLab 编程实验室**：在线编码、终端执行、C++ 判题
- **RAG 知识库**：教学资料检索增强问答
- **学情诊断**：自测定位知识盲区，学情复盘与掌握度分析
- **学习文档 / 错题本 / 学习资源**：系统化学习支持

## 快速开始

### Docker 部署（推荐）

```bash
# 首次启动先复制配置模板，并至少设置稳定的 JWT_SECRET_KEY
copy .env.example .env

docker compose up -d
```

启动后：

| 服务 | 端口 |
| --- | --- |
| 前端 | 80 |
| 后端 | 8001 |

Demo 账号：`demo` / `demo123`

### 本地开发

```bash
# 1. 后端 (端口 8001)
cd backend
uvicorn main:app --port 8001 --reload

# 2. 前端 (端口 5174)
cd frontend
npm install
npm run dev -- --port 5174
```

## 架构说明

- 前端通过 nginx 将 `/api/` 反向代理到后端（`host.docker.internal:8001`），SSE 路径已关闭代理缓冲（`proxy_buffering off`）以支持流式输出。
- 后端为单体 FastAPI 应用，路由包括：auth、diagnosis（学情诊断）、qa（AI 答疑）、learning、analytics、resource、knowledge、llm_config、image、rag、capability、workspace（CodeLab）。
