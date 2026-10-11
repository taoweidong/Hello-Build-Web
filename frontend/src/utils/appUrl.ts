/** 应用内 hash 路由完整 URL 构造（origin + 部署子路径 + #/xxx）。

此前 report 两页硬编码 `${origin}/#/...`（丢 pathname，子路径部署断链），
http.ts 401 跳转硬编码 `/#/login` 同病；统一收敛到本工具（与 borrowFlowUrl 同款拼法）。
*/
export function appHashUrl(hashPath: string): string {
  const { origin, pathname } = window.location;
  const path = hashPath.startsWith("/") ? hashPath : `/${hashPath}`;
  return `${origin}${pathname}#${path}`;
}
