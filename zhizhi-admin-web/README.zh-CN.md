# 致知 Admin Web

[English](README.md) · [返回项目总览](../README.zh-CN.md)

企业 Agent 的可信度并不只来自一个更好的聊天框。必须有人决定：哪个组织可以使用哪个模型，哪些知识具有权威性，实时事实来自哪里，以及谁有权修改这些决定。

致知 Admin Web 就是承载这些决定的控制台。

它专门面向致知 Admin API，把后端的租户、组织、资源、知识与管理员权限策略转化为可见的管理流程，同时不把这些能力混入终端用户的 Agent 使用体验。

## 管理员的工作路径

平台管理员可以建立全局资源目录，再把资源授权给租户；租户管理员则在该租户已获得的范围和权限内继续管理。

管理员可以在控制台中：

1. 创建租户和任意深度的组织树；
2. 创建或绑定管理员账号，并分配角色；
3. 配置模型供应商、凭证、能力和连通性；
4. 向租户或组织节点分配模型与数据源的可用资源；
5. 在选定范围绑定真正用于执行的模型或数据源；
6. 注册 Git 仓库并授权给租户；
7. 创建、编辑、上传、打包和同步 Scene 与 Skill；
8. 只看到当前 RBAC 会话允许访问的导航与操作。

控制台明确区分**可用资源**与**绑定资源**。可用资源决定某个范围能够使用或继续授权什么，绑定资源决定执行时真正选择什么。这是管理体验的核心，而不是藏在 API 中的实现细节。

## 当前管理能力

| 模块 | 当前能力 |
| --- | --- |
| 全局管理 | 超级管理员使用的平台级资源与租户管理 |
| 组织管理 | 租户与不限制深度的递归组织节点 |
| 账号与角色 | 管理员账号、租户成员、角色、权限和密码重置 |
| 模型管理 | 供应商配置、加密凭证、校验、测试、可用资源和绑定资源 |
| 数据源管理 | HTTP 网关配置、加密凭证、可用资源和绑定资源 |
| Git 知识 | 仓库注册、凭证更新、连通性测试和租户授权 |
| Scene | 文件编辑、目录操作、包上传下载、Git 关联、手工同步和同步历史 |
| Skill | 基于 `SKILL.md` 的资源创建、文件编辑、包导入导出和 Manifest 同步 |

本工程不管理企业员工、终端用户登录、业务权限或产品侧会话，这些仍由宿主系统负责。

## 会话与 API 边界

致知 Admin Web 使用 Admin API 的管理员 Session 和按权限生成的导航。浏览器会先取得 Admin API 的 RSA 公钥，再加密密码后传输。默认请求使用同源 `/api` 路径。

本地开发时，Vite 将 `/api` 代理到：

```text
http://127.0.0.1:8001
```

可以通过 `ZHIZHI_ADMIN_API_PROXY_TARGET` 修改目标。

首个超级管理员需要在致知仓库根目录创建：

```bash
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/admin.yml" \
  uv --directory zhizhi-backend run zhizhi-admin-api init-super-admin
```

配置与启动方式见[后端指南](../zhizhi-backend/README.zh-CN.md)。

## 技术栈

- Vue 3 Composition API
- TypeScript
- Vue Router
- Pinia
- Element Plus
- CodeMirror 与 Markdown 编辑能力
- 通过 Vite 插件使用的 Tailwind CSS
- Vite 与 Vitest

界面使用致知蓝紫色视觉体系，品牌资源位于 `src/assets`。

## 本地开发

环境要求：

- Node.js 22+
- Corepack

按照本工程自己的锁文件安装依赖：

```bash
corepack pnpm install --frozen-lockfile
```

启动开发服务器：

```bash
corepack pnpm run dev
```

访问 `http://127.0.0.1:5173`。

连接其他 Admin API：

```bash
ZHIZHI_ADMIN_API_PROXY_TARGET=http://127.0.0.1:9001 corepack pnpm run dev
```

## 验证与构建

```bash
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

生产构建输出到 `dist/`。正式部署时，建议通过与 Admin API 相同的可信域名或反向代理提供静态文件。

## 许可证

[MIT](LICENSE)
