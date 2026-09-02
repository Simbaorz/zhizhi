# 致知

[English](README.md)

致知是构建在 [Gewu Agent Runtime](https://github.com/Simbaorz/gewu) 之上的企业知识问答 Agent 体系。它由支持治理的后端、独立管理控制台和轻量 Web API 试用端组成，使企业可以在保留现有身份体系与业务界面的前提下，接入安全、可配置的 Agent 能力。

## 工程组成

- `zhizhi-backend/`：租户隔离、任意层级组织、资源治理、Agent Web API、Admin API、持久化与后台任务。
- `zhizhi-admin-web/`：组织、模型、数据源、Git 知识源、Scene、Skill、可用资源和绑定资源的管理控制台。
- `zhizhi-web/`：轻量 Web API 试用端与接入参考。

三个工程统一保存在本仓库中并共同版本化，同时保持独立构建和独立部署。

## 架构

```text
企业宿主系统
  ├─ 身份认证与业务授权
  ├─ 已有业务界面
  └─ 可信的租户 / 组织 / 用户上下文
                    │
                    ▼
              致知 Web API
                    │
               能力与策略解析
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
     模型          数据源       Scene / Skill
      └─────────────┼─────────────┘
                    ▼
             Gewu Agent Runtime
```

租户是隔离边界，组织节点构成任意深度的树。可用资源决定每个范围可以使用或继续授权什么，绑定资源决定 Runtime 真正选择什么。请求从当前组织节点向父级和租户回溯，最近的有效模型绑定优先。

Gewu 继续作为独立项目维护，不会复制到本仓库。正式的软件包版本发布前，后端通过固定的 Git revision 使用 Gewu。

## 开发

环境要求：

- Python 3.12+
- `uv`
- Node.js 22+
- 启用 Corepack 的 pnpm

在仓库根目录安装并验证两个前端工程：

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm run test
corepack pnpm run typecheck
corepack pnpm run build
```

同时启动两个前端开发服务器，端口分别为 5173 和 5174：

```bash
corepack pnpm run dev
```

安装并验证后端：

```bash
cd zhizhi-backend
uv sync --all-packages --all-extras --all-groups --frozen
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
```

本地配置与启动方式见各工程自己的 README。

## 许可证

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE)。
