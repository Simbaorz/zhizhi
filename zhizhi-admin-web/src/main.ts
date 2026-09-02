import { createPinia } from "pinia";
import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

import AppRoot from "@/app/AppRoot.vue";
import { registerUnauthorizedHandler } from "@/api/http";
import { router } from "@/router";
import { useAuthStore } from "@/stores/auth";
import "@/style.css";

const app = createApp(AppRoot);
const pinia = createPinia();
app.use(pinia);
app.use(router);
app.use(ElementPlus);
registerUnauthorizedHandler(async () => {
  useAuthStore(pinia).expireSession();
  if (router.currentRoute.value.meta.auth !== false) {
    await router.replace("/login");
  }
});
app.mount("#app");
