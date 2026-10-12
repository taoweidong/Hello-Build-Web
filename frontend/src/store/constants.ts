// 业务存储键常量：独立模块，避免 http/工具层为取常量而拉起整条 store→router 依赖链
/** 业务侧登录用户信息（localStorage） */
export const businessUserKey = "build-user-info";

/** 调度全景：用户上次选择的布局（localStorage，刷新后保持） */
export const panoramaLayoutKey = "panorama-layout";
