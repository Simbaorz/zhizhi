# 致知 Backend

[English](README.md) · [返回项目总览](../README.zh-CN.md)

致知 Backend 负责把一个已经完成身份认证的企业问题，转化为一次受治理的 Agent 运行。

它位于企业宿主系统和 [Gewu Agent Runtime](https://github.com/Simbaorz/gewu) 之间。宿主系统继续掌握用户、业务权限和产品体验；后端校验传入的租户与组织上下文，解析该范围允许使用的能力，组合只读 Workspace 与 ToolSet，然后交给 Gewu 执行并持久化会话。

## 一次 Agent 回合内部发生了什么

```text
可信的调用方上下文
        │
        ▼
租户与组织路径校验
        │
        ├─ 最近的模型绑定
        ├─ 最近的数据源绑定
        ├─ 可见的 Scene 与 Skill
        └─ 租户 + 组织 Workspace 挂载
        │
        ▼
只读的致知 ToolSet
        │
        ▼
Gewu Agent Runtime
        │
        ├─ 流式输出模型与工具事件
        ├─ 持久化消息和会话状态
        ├─ 挂起并恢复 ask_user
        ├─ 压缩长上下文
        └─ 接收中断
```

后端不会从一个公开浏览器请求中自行推断身份。Agent API 应部署在可信企业网关或业务应用之后，由调用方先完成认证，再构造调用上下文。

## Workspace 结构

本目录是一个 Python `uv workspace`：

| 模块 | 职责 |
| --- | --- |
| [`apps/zhizhi-web-api`](apps/zhizhi-web-api/README.md) | 供企业应用接入的轻量流式 Agent API |
| [`apps/zhizhi-admin-api`](apps/zhizhi-admin-api/README.md) | 管理员认证、RBAC、租户、组织、资源、Scene、Skill 与带审计的变更 |
| [`apps/zhizhi-worker`](apps/zhizhi-worker/README.md) | 执行 Scene Git 同步与附件清理的 Celery Worker 和调度器 |
| `packages/zhizhi-application` | 与传输层无关的应用服务、资源策略、持久化适配、Runtime 组合与 Workspace 管理 |

所有进程共享同一应用包，并且必须使用一致的数据库、Redis 拓扑、Workspace 存储根目录、媒体存储与存储加密密钥。

## 身份与组织模型

租户是强隔离边界。组织节点形成一棵任意深度的树：

```text
tenant
└── organization unit
    ├── organization unit
    │   └── organization unit
    └── organization unit
```

组织节点包含父节点、外部标识、显示名称、类型、元数据和状态。区域、分公司、部门、团队、项目等只是数据，不是固定的数据库层级。

调用方和用户组与组织树保持分离。一个调用方可以关联多个组织节点和用户组，而不必把企业身份模型硬编码进组织结构。

Web API 接收以下上下文：

```json
{
  "conversation_id": "conversation-123",
  "tenant_id": "tenant-123",
  "active_organization_unit_id": "team-456",
  "principal_id": "user-789",
  "principal_type": "user"
}
```

租户级运行可以不传当前组织节点；如果传入，后端会先验证完整的根到叶路径，再解析任何 Agent 能力。

## 可用资源、绑定资源与继承

资源治理将“允许使用”和“真正选择”分开：

| 概念 | 含义 |
| --- | --- |
| 可用资源（entitlement） | 某个租户或组织范围允许使用该资源，并可按策略继续授权 |
| 绑定资源（binding） | 在该范围选择哪个已授权资源参与执行 |

模型和数据源从当前组织叶节点开始，依次向父级和租户回溯，第一个有效绑定优先。如果最近的活动绑定存在但无法构造能力，请求会直接失败，不会静默跳过并使用更宽范围的资源。

Runtime 知识采用另一种组合方式：租户 Workspace 与当前完整组织路径上的 Workspace 都会以只读方式挂载。当前版本中，受管理的 Scene 和 Skill 为租户级资源，只在解析后的调用范围可见时暴露。

## Runtime 能力

首个开源版本有意限制 ToolSet：

- `list`、`read`、`glob`、`grep`：发现和阅读只读 Workspace；
- `skill`：加载受治理的 Skill；
- `ask_user`：挂起运行并请求结构化澄清；
- 解析到已授权数据源绑定时，按需加入 `query_data_source`。

系统不提供 Shell 工具，也不允许 Runtime 不受限制地修改 Workspace。

### 让模型查询事实，但不拿到数据库凭证

`query_data_source` 不会让 Agent 直接连接数据库。致知把它绑定到管理员配置的 HTTP 数据网关。当前参考适配器会：

- 只接受单条 `SELECT` 或 `WITH`；
- 拒绝数据变更与 DDL 关键字；
- 强制行数限制和 Tool 返回体积上限；
- 将网关凭证保留在服务端；
- 规范化返回结构，并遮蔽名称疑似敏感的字段值。

这个网关协议属于上层应用适配，不是 Gewu 的要求。企业可以替换为自己的受治理查询服务，同时保持 Runtime 契约的边界。

## Agent Web API

集成接口有意保持精简：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/agent/chat/stream` | 启动 Agent 回合并接收 Server-Sent Events |
| `POST` | `/api/agent/chat/ask-answer` | 恢复等待中的 `ask_user` |
| `POST` | `/api/agent/chat/attachments` | 在回合开始前上传图片 |
| `GET` | `/api/agent/chat/attachments/{attachment_id}` | 读取已授权附件 |
| `GET` | `/api/agent/capabilities` | 解析当前范围的能力 |
| `GET` | `/api/agent/skills` | 获取可见 Skill |
| `GET` | `/api/agent/scenes` | 获取可见 Scene |
| `GET` | `/api/agent/conversations/{conversation_id}/messages` | 读取持久化消息 |
| `GET` | `/api/agent/conversations/{conversation_id}/pending-ask` | 恢复待澄清状态 |
| `POST` | `/api/agent/conversations/{conversation_id}/interrupt` | 中断当前运行 |
| `GET` | `/healthz` | 进程存活检查 |
| `GET` | `/readyz` | Runtime 就绪检查 |

请求使用 `request_id` 实现幂等。同一 ID 被用于不同工作时会返回冲突，而不是启动重复回合。

## Admin API

管理进程与 Agent 执行完全分离，提供：

- 管理员登录、加密密码传输、会话、登录限流、RBAC 和按权限生成导航；
- 租户、递归组织树、管理员账号、租户成员与角色；
- 模型定义、加密凭证、连通性测试、可用资源和绑定资源；
- HTTP 数据源定义、加密网关凭证、可用资源和绑定资源；
- Git 仓库与租户授权；
- Scene 和 Skill 文件、压缩包、Manifest 与 Scene Git 同步；
- 变更审计以及受限的上传下载。

该进程不会启动 Agent Runtime。

## 配置模型

每个进程从环境变量加载引导配置，再从 YAML 或 Apollo 加载服务配置。
致知仓库根目录就是部署时的 `PROJECT_HOME`，因此共享服务配置位于根 `conf/`，不属于 Python Workspace。

常用引导变量包括：

- `PROJECT_NAME`、`PROJECT_HOME`、`MODE`、`TIMEZONE`；
- `CONFIG_SOURCE`：`local` 或 `apollo`；
- `CONFIG_FILE`：显式指定 YAML；
- 使用 `CONFIG_SOURCE=apollo` 时所需的 Apollo 连接变量。

根目录的 [`.env.example`](../.env.example) 记录这一层后端引导变量。

仓库提供以下示例：

- [`conf/web.example.yml`](../conf/web.example.yml)
- [`conf/admin.example.yml`](../conf/admin.example.yml)
- [`conf/worker.example.yml`](../conf/worker.example.yml)

真实配置与凭证不会提交到 Git。

Web API、Admin API 与 Worker 必须使用兼容的：

- 数据库连接与表结构；
- Redis 应用数据库与 Celery 数据库；
- `workspace.storage_root`；
- 媒体文件系统或对象存储配置；
- `storage_encryption.key`。

生产环境中，JWT 签名密钥与存储加密密钥必须不同，管理员 Session Cookie 应启用 Secure，并通过 TLS 暴露服务。

## 本地开发

环境要求：

- Python 3.12+
- `uv`
- Redis
- 使用 Scene Git 同步时需要 Git
- 用于生成管理员密码传输密钥的 OpenSSL

以下命令均从致知仓库根目录执行。安装后端 Workspace：

```bash
uv --directory zhizhi-backend sync --all-packages --all-extras --all-groups --frozen
```

创建不会提交到 Git 的本地配置：

```bash
cp .env.example .env
cp conf/web.example.yml conf/web.yml
cp conf/admin.example.yml conf/admin.yml
cp conf/worker.example.yml conf/worker.yml
openssl genpkey -algorithm RSA -out conf/admin-password-key.pem -pkeyopt rsa_keygen_bits:2048
chmod 600 conf/admin-password-key.pem
```

示例配置默认将临时文件、媒体和受管理 Workspace 放在根目录下被忽略的 `volume/` 中，并让
Admin API 使用刚生成的私钥。启动前：

1. 在三份配置中设置相同且非空的 `storage_encryption.key`；
2. 设置 Admin `jwt.sk`；
3. 确认所有进程使用同一数据库与 Redis 部署。

启动完整本地服务：

```bash
./scripts/start-local.sh
```

脚本会启动：

- `http://127.0.0.1:8000` 的 Web API；
- `http://127.0.0.1:8001` 的 Admin API；
- 带 Beat 的 Celery Worker；
- `http://127.0.0.1:5173` 的 Admin Web；
- `http://127.0.0.1:5174` 的致知 Web。

在另一个终端创建一次性的超级管理员：

```bash
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/admin.yml" \
  uv --directory zhizhi-backend run zhizhi-admin-api init-super-admin
```

如果没有显式提供命令行参数，该命令会交互式询问账号和密码。

### 分别启动进程

```bash
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/web.yml" \
  uv --directory zhizhi-backend run zhizhi-web-api --host 127.0.0.1 --port 8000
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/admin.yml" \
  uv --directory zhizhi-backend run zhizhi-admin-api --host 127.0.0.1 --port 8001
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/worker.yml" \
  uv --directory zhizhi-backend run zhizhi-worker worker --beat --loglevel=INFO
```

## 数据结构与生产行为

在 `dev` 和 `test` 模式下，启动过程会通过 SQLAlchemy Metadata 创建缺失的致知与 Gewu 表。这只是本地开发便利机制，不是迁移系统。

在 `prod` 模式下，进程不会执行任何表结构 DDL，必须在服务启动前准备完整 Schema。项目当前不承诺兼容旧表结构。

## 验证

```bash
cd zhizhi-backend
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
uv build --all-packages
```

## 许可证

[MIT](LICENSE)
