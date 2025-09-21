// app/lib/apiBase.ts
export const apiBase =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export const apiTimeout = Number(process.env.NEXT_PUBLIC_API_TIMEOUT ?? 20000);
