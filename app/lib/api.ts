// app/lib/api.ts
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE!;
const DEFAULT_TIMEOUT = Number(process.env.NEXT_PUBLIC_API_TIMEOUT || 20000);

function joinUrl(base: string, path: string) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

export async function apiFetch(
  path: string,
  opts: RequestInit & { timeoutMs?: number } = {}
) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), opts.timeoutMs ?? DEFAULT_TIMEOUT);

  const url = joinUrl(API_BASE, path);
  const res = await fetch(url, {
    ...opts,
    signal: controller.signal,
  }).catch((e) => {
    clearTimeout(id);
    throw e;
  });

  clearTimeout(id);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} - ${text}`);
  }
  return res;
}
