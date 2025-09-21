// 所有请求都用相对路径，走 Next 的 app/api 代理。
export async function uploadPdf(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ job_id: string; filename: string }>;
}

export async function startAnalyze(jobId: string) {
  const res = await fetch(`/api/analyze2/${jobId}`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function pollStatus(jobId: string) {
  const res = await fetch(`/api/jobs_adv2/${jobId}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<any>;
}
