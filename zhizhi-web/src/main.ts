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
  ElAside,
  ElSelect,
  ElOption,
  ElSegmented,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElSkeleton,
  ElTag,
  ElTooltip,
} from "element-plus";
import "element-plus/dist/index.css";

import App from "@/App.vue";
import "@/style.css";
import "@/portal.css";
import "@/brand.css";

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
  ElAside,
  ElSelect,
  ElOption,
  ElSegmented,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElSkeleton,
  ElTag,
  ElTooltip,
].forEach((component) => app.use(component));

app.mount("#app");
