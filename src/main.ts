import { createApp } from "vue";
import {
  ElAlert,
  ElAvatar,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElConfigProvider,
  ElContainer,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElMain,
  ElSkeleton,
  ElTag,
  ElTooltip,
} from "element-plus";
import "element-plus/dist/index.css";

import App from "@/App.vue";
import "@/style.css";

const app = createApp(App);

[
  ElAlert,
  ElAvatar,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElConfigProvider,
  ElContainer,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElMain,
  ElSkeleton,
  ElTag,
  ElTooltip,
].forEach((component) => app.use(component));

app.mount("#app");
