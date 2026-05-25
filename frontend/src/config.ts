/** API 根地址：开发环境直连 8000，生产环境走同域 Nginx */
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(
  /\/$/,
  ""
) ?? "";

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
