# 致知 Backend

[English](README.md)

致知 Backend 是构建在 [Gewu Agent Runtime](https://github.com/Simbaorz/gewu) 之上的企业应用层。它把 Gewu 的执行、上下文、记忆、会话、工具、Scene、Skill 与虚拟文件系统能力，组合为一套可部署的企业知识问答服务，并提供租户隔离、组织级资源治理、管理 API 和轻量集成 API。

致知位于企业现有系统之后：企业系统继续负责终端用户认证、产品界面和业务权限；致知接收可信的租户、当前组织节点与用户身份，解析本次运行应使用的模型、数据源和知识能力，然后执行 Agent 回合。

## 工程组成

- `apps/zhizhi-web-api`：供企业系统接入的流式 Agent API。
- `apps/zhizhi-admin-api`：管理员认证、RBAC、组织、模型、数据源、Git、Scene 与 Skill 管理。
- `apps/zhizhi-worker`：Scene Git 同步与定时后台任务。
- `packages/zhizhi-application`：应用服务、持久化适配、资源解析、审计与 Workspace 组合。

## 组织与资源模型

租户是隔离边界。每个租户拥有一棵任意深度的组织树：

```text
tenant
└── organization unit
    └── organization unit
        └── ...
```

组织节点通过 `parent_id` 连接。事业部、分公司、区域、部门、团队、项目等名称只是数据，而不是写死的表结构。请求选择一个当前组织节点，致知会校验从根节点到该节点的完整路径。

模型与数据源采用“可用资源 + 绑定资源”两层语义：

- 可用资源：允许某个租户或组织节点使用，并可继续向下授权。
- 绑定资源：该范围真正选中用于执行的资源。

运行时从当前最深组织节点开始向上回溯，直到租户，最近的有效绑定优先。任何绑定都不能绕过可用资源授权。租户级 Scene 与 Skill 会和当前组织路径一起挂载到只读 Agent Workspace。

## Web API

Web API 保持轻量，便于企业直接嵌入现有系统，而不必采用另一套用户体系或完整聊天产品：

- `POST /api/agent/chat/stream`
- `POST /api/agent/chat/ask-answer`
- `POST /api/agent/chat/attachments`
- `GET /api/agent/chat/attachments/{attachment_id}`
- `GET /api/agent/capabilities`
- `GET /api/agent/skills`
- `GET /api/agent/scenes`
- `GET /api/agent/conversations/{conversation_id}/messages`
- `GET /api/agent/conversations/{conversation_id}/pending-ask`
- `POST /api/agent/conversations/{conversation_id}/interrupt`

可信调用上下文：

```json
{
  "conversation_id": "conversation-123",
  "tenant_id": "tenant-123",
  "active_organization_unit_id": "team-456",
  "principal_id": "user-789",
  "principal_type": "user"
}
```

致知不提供终端用户登录、个人资料或会话列表产品；调用方必须先完成认证并构造上述上下文。

## 本地开发

需要 Python 3.12+ 和 `uv`。Gewu 将按照本工作区锁定的 revision 自动解析。

```bash
uv sync --all-packages --all-extras --all-groups --frozen
cp conf/web.example.yml conf/web.yml
cp conf/admin.example.yml conf/admin.yml
cp conf/worker.example.yml conf/worker.yml
./scripts/start-local.sh
```

脚本默认启动 `127.0.0.1:8000` 的 Web API、`127.0.0.1:8001` 的 Admin API，以及带调度器的 Celery Worker。真实配置和凭证不得提交到 Git。

`dev` 与 `test` 模式可通过 SQLAlchemy 元数据创建缺失表；生产模式不会执行 DDL，必须先完成数据库建表。所有进程必须共享数据库、Redis、Workspace 存储根目录和存储加密密钥。

## 验证

```bash
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
uv build --all-packages
```

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。
