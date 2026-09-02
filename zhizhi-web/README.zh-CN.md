# 致知 Web

[English](README.md) · [返回项目总览](../README.zh-CN.md)

企业接入 Agent 的最短路径，往往不是再建设一个完整产品，而是先得到一份现有产品能够理解的清晰 API 契约。

致知 Web 是这份契约的轻量、可运行说明。开发者可以填写可信会话上下文，启动流式 Agent 回合，调用 Scene 或 Skill，上传图片，回答澄清问题，恢复当前会话，并中断运行。

它有意保持为试用工作台，而不是完整的企业聊天应用。

## 接入过程

典型企业应用已经知道用户是谁、会话属于哪里，并且拥有完整的产品体验。它将这些上下文交给致知，同时继续负责 Agent 周围的业务流程。

```text
企业现有界面
        │
        ├─ 会话与消息输入
        ├─ 已认证的用户和组织上下文
        └─ 产品自己的业务流程
        │
        ▼
致知 Agent Web API
        │
        ├─ 能力发现
        ├─ SSE 会话流
        ├─ Scene 与 Skill 调用
        ├─ 图片附件生命周期
        ├─ ask_user 续答
        ├─ 消息与待处理状态恢复
        └─ 中断
```

致知 Web 展示的是这条边界右侧的交互方式。正式业务应该复用交互模式，不一定需要采用这个界面。

## 当前演示的能力

- 在 `sessionStorage` 中编辑和暂存调用方上下文；
- 加载该上下文对应的有效能力；
- 获取可见的 Scene 与 Skill；
- 发起幂等 Agent 请求并解析 Server-Sent Events；
- 展示助手消息、工具调用、工具结果与澄清问题；
- 在回合开始前上传图片，并解析已授权附件地址；
- 恢复等待中的 `ask_user`；
- 恢复当前会话已持久化的消息和待处理状态；
- 请求中断当前运行。

工程有意不提供登录页、员工目录、租户管理、资源配置和会话列表。

## 可信调用上下文

试用端会在 Agent 请求中发送：

| 字段 | 含义 |
| --- | --- |
| `conversation_id` | 由宿主系统定义的当前会话标识 |
| `tenant_id` | 致知的租户隔离边界 |
| `active_organization_unit_id` | 可选的当前组织节点；为空表示租户级 |
| `principal_id` | 宿主系统定义的调用方标识 |
| `principal_type` | 调用方类型，默认是 `user` |

这个演示保存在浏览器中的值可以被用户自行修改，它们不是身份证明。

正式环境不能把 Agent API 直接公开，并无条件信任这些字段。企业宿主应用或网关必须先认证用户、执行业务授权，再构造或校验上下文后转发给致知。

## 客户端使用的 API

| 方法 | 路径 |
| --- | --- |
| `GET` | `/api/agent/capabilities` |
| `GET` | `/api/agent/skills` |
| `GET` | `/api/agent/scenes` |
| `POST` | `/api/agent/chat/stream` |
| `POST` | `/api/agent/chat/ask-answer` |
| `POST` | `/api/agent/chat/attachments` |
| `GET` | `/api/agent/chat/attachments/{attachment_id}` |
| `GET` | `/api/agent/conversations/{conversation_id}/messages` |
| `GET` | `/api/agent/conversations/{conversation_id}/pending-ask` |
| `POST` | `/api/agent/conversations/{conversation_id}/interrupt` |

完整服务契约与配置模型见[后端指南](../zhizhi-backend/README.zh-CN.md)。

## 技术栈

- Vue 3 Composition API
- TypeScript
- Vite
- Element Plus
- Markdown 渲染与 DOMPurify 清理
- 原生 `fetch` 与 Server-Sent Event 帧解析
- Node 内置测试运行器

工程有意保持轻量，让 API 交互容易追踪和复用。

## 本地开发

环境要求：

- Node.js 22+
- Corepack
- 已在本机或可访问地址运行的致知 Web API

按照本工程自己的锁文件安装依赖：

```bash
corepack pnpm install --frozen-lockfile
```

启动开发服务器：

```bash
corepack pnpm run dev
```

访问 `http://127.0.0.1:5174`。Vite 默认将 `/api` 代理到 `http://127.0.0.1:8000`。

使用其他本地 API：

```bash
ZHIZHI_API_PROXY_TARGET=http://127.0.0.1:8080 corepack pnpm run dev
```

## 生产构建

同源部署不需要配置 API 地址；跨域静态部署需要在构建阶段提供 API Origin：

```bash
VITE_ZHIZHI_API_BASE_URL=https://agent.example.com corepack pnpm run build
```

构建结果输出到 `dist/`。

## 验证

```bash
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

## 许可证

[MIT](LICENSE)
