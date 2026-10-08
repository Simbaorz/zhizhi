# 致知 Web 试用端

配套可选的测试 Portal：登录后选择已授权的租户或组织范围，创建、打开、重命名、归档或恢复个人会话。
支持流式回答、显式选择 Scene/Skill、图片上传、补充问答和任务打断/状态恢复。

浏览器不再手填租户编码、组织 ID 或调用方身份。Portal 根据测试账号授权和会话记录构造可信上下文；
完整消息、附件与运行状态仍由 Agent Backend 保存。内部 meta 消息按类型隐藏，工具请求与结果合并展示，
澄清问答保留历史，刷新页面不会主动停止服务端任务。

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm run dev
```

地址 http://127.0.0.1:5174，/api 默认代理到测试 Portal http://127.0.0.1:8003。
可用 ZHIZHI_PORTAL_API_PROXY_TARGET 覆盖；同源部署无需设置 API base。
在 Portal Admin http://127.0.0.1:5175 用现有 Super Admin 登录后创建试用账号，分配租户根级或任意深度组织。
资源治理仍在现有 Admin 中完成。

Portal 仅用于测试环境。正式企业宿主继续拥有自己的用户认证和业务权限，并独立调用现有 Agent API，
传入 conversation_id、tenant_code、可选 active_organization_unit_id、principal_id 和 principal_type。
部署时 Web 与 Portal 的 /api 应保持同源，Agent API 仅供 Portal 与可信宿主网关访问。

```bash
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```
