// vitest 全局 setup：注册 Element Plus，使布局组件在单测中按真实组件渲染
// 依据：main.ts 经 app.use(ElementPlus) 全局注册；测试环境缺这一步，
// el-button / el-radio-button 等会退化为未解析的自定义元素，
// 导致 findAll("button")、.el-radio-button 等选择器全部落空。
import { config } from "@vue/test-utils";
import ElementPlus from "element-plus";

config.global.plugins.push(ElementPlus);
