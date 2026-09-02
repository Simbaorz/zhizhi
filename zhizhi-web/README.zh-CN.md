# 致知 Web

[English](README.md)

致知 Web 是致知 Agent Web API 的轻量试用界面和接入参考，演示可信会话上下文、流式输出、Scene 与 Skill 调用、图片附件、`ask_user` 续答、当前会话恢复和中断输出。

它不是完整的企业聊天产品：不包含登录、用户管理、会话列表或资源管理。企业可以复用其中的 API 交互方式，同时继续使用已有的身份体系和业务界面。

## 开发

在 Monorepo 根目录运行：

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm --filter zhizhi-web test
corepack pnpm --filter zhizhi-web run typecheck
corepack pnpm --filter zhizhi-web run dev
```

开发服务器运行在 `http://127.0.0.1:5174`，并将 `/api` 代理到 `http://127.0.0.1:8000`。

```bash
ZHIZHI_API_PROXY_TARGET=http://127.0.0.1:8080 corepack pnpm --filter zhizhi-web run dev
```

跨域部署时，可在构建阶段设置 `VITE_ZHIZHI_API_BASE_URL`；同源部署无需设置。

试用会话上下文保存在 `sessionStorage`，包含 `conversation_id`、`tenant_id`、可选的 `active_organization_unit_id`、`principal_id` 和 `principal_type`。宿主系统必须先完成用户认证，再提供这些值。

## 生产构建

```bash
corepack pnpm --filter zhizhi-web run build
```

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。
