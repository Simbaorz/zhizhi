import { createPinia } from "pinia";
import { createApp } from "vue";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";

import AppRoot from "@/app/AppRoot.vue";
import { registerUnauthorizedHandler } from "@/api/http";
import { router } from "@/router";
import { useAuthStore } from "@/stores/auth";
import "@/style.css";
import "@/styles/globalManagement.css";
import "@/styles/brand.css";

const app = createApp(AppRoot);
const pinia = createPinia();
app.use(pinia);
app.use(router);
app.use(ElementPlus, { locale: zhCn });
registerUnauthorizedHandler(async () => {
  useAuthStore(pinia).expireSession();
  if (router.currentRoute.value.meta.auth !== false) {
    await router.replace("/login");
  }
});
app.mount("#app");
