# Zhizhi Admin Web

[English](README.md)

Zhizhi Admin Web 是 Zhizhi 企业知识问答 Agent 的管理控制台，提供管理员登录与 RBAC、租户与任意层级组织树、模型和数据源的可用资源与绑定资源、Git 知识源、Scene、Skill 及审计管理流程。

该控制台只管理 Agent 基础设施，不替代企业已有的终端用户门户、员工目录或业务会话界面。

## 组织级资源治理

租户是隔离边界，组织节点通过递归树表达企业自己的结构。资源管理页面区分：

- 可用资源：当前范围可以使用或继续向下授权的资源。
- 绑定资源：当前范围真正选中用于执行的资源。

界面采用统一的蓝紫色视觉体系，并使用 `src/assets` 下的 Zhizhi 品牌资源。

## 开发

```bash
corepack pnpm install
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run dev
```

开发服务器运行在 `http://127.0.0.1:5173`，并将 `/api` 代理到 `http://127.0.0.1:8001`。可通过 `ZHIZHI_ADMIN_API_PROXY_TARGET` 修改 Admin API 地址。

## 生产构建

```bash
corepack pnpm run build
```

静态产物输出到 `dist/`。

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。
