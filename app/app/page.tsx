"use client";

import { useState, useEffect, useRef } from "react";
import ResultCard from "@/components/ResultCard";

type UploadResp = {
  job_id: string;
  filename?: string;
  size?: number;
  saved_path?: string;
  checksum?: string;
};

type JobStatus =
  | { job_id: string; status: "queued" | "processing"; progress?: number; ts?: number }
  | { job_id: string; status: "done"; progress: 100; result: ResultPayload; ts?: number }
  | { job_id: string; status: "error"; error: string; ts?: number }
  | { job_id: string; status: "unknown" };

type Issue = {
  rule: string;
  severity: "critical" | "error" | "warn" | "info" | string;
  message: string;
  location?: { page?: number; [k: string]: any };
};

type ResultPayload = {
  summary: string;
  issues: Issue[];
  meta?: Record<string, any>;
};

export default function HomePage() {
  // UI 状态
  const [log, setLog] = useState<string[]>([]);
  const [job, setJob] = useState<UploadResp | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [url, setUrl] = useState("");
  const pollTimer = useRef<any>(null);

  function appendLog(s: string) {
    setLog((prev) => [...prev, s].slice(-200));
  }

  // 轮询
  useEffect(() => {
    if (!job?.job_id) return;
    if (pollTimer.current) clearInterval(pollTimer.current);

    pollTimer.current = setInterval(async () => {
      try {
        const r = await fetch(`/api/jobs_adv/${job.job_id}/status`, { cache: "no-store" });
        const js = (await r.json()) as JobStatus;
        setStatus(js);
        appendLog(`状态: HTTP ${r.status} → ${JSON.stringify(js)}`);
        if (js.status === "done" || js.status === "error") {
          clearInterval(pollTimer.current);
        }
      } catch (e: any) {
        appendLog(`状态错误: ${e?.message || String(e)}`);
      }
    }, 1000);

    return () => pollTimer.current && clearInterval(pollTimer.current);
  }, [job?.job_id]);

  // 文件上传
  async function onPickFile(ev: React.ChangeEvent<HTMLInputElement>) {
    const f = ev.target.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.set("file", f);
    try {
      appendLog("开始上传...");
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const js = (await r.json()) as UploadResp;
      appendLog(`解析返回: HTTP ${r.status} → ${JSON.stringify(js)}`);
      if (!r.ok) throw new Error(JSON.stringify(js));
      setJob(js);
      setStatus(null);
    } catch (e: any) {
      appendLog(`上传失败: ${e?.message || String(e)}`);
    } finally {
      ev.target.value = "";
    }
  }

  // 链接上传（服务端拉取）
  async function onUploadByUrl() {
    if (!url.trim()) return;
    try {
      appendLog(`开始链接上传: ${url}`);
      const r = await fetch("/api/upload-by-url", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const js = (await r.json()) as UploadResp;
      appendLog(`链接上传返回: HTTP ${r.status} → ${JSON.stringify(js)}`);
      if (!r.ok) throw new Error(JSON.stringify(js));
      setJob(js);
      setStatus(null);
    } catch (e: any) {
      appendLog(`链接上传失败: ${e?.message || String(e)}`);
    }
  }

  // 触发解析
  async function onAnalyze() {
    if (!job?.job_id) return;
    try {
      setLoading(true);
      appendLog(`开始解析（job ${job.job_id.slice(0, 8)}...）`);
      const r = await fetch(`/api/analyze/${job.job_id}`, { method: "POST" });
      const js = await r.json();
      appendLog(`解析返回: HTTP ${r.status} → ${JSON.stringify(js)}`);
      if (!r.ok) throw new Error(JSON.stringify(js));
      // 状态会被轮询拉到
    } catch (e: any) {
      appendLog(`解析错误: ${e?.message || String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  // 分组展示
type Issue = {
  rule: string;
  severity: "error" | "warn" | "info" | string;
  message: string;
  location?: Record<string, any>;
};

type IssuesBuckets = {
  error: Issue[];
  warn: Issue[];
  info: Issue[];
  all: Issue[];
};

const normalizeIssues = (raw: any): IssuesBuckets => {
  // 后端老格式：直接就是 Issue[]
  if (Array.isArray(raw)) {
    const arr = raw as Issue[];
    const sev = (s: any) => (String(s || "").toLowerCase());
    return {
      error: arr.filter((x) => ["critical", "error"].includes(sev(x.severity))),
      warn:  arr.filter((x) => sev(x.severity) === "warn"),
      info:  arr.filter((x) => sev(x.severity) === "info"),
      all:   arr,
    };
  }
  // 新格式：{ error:[], warn:[], info:[], all:[] }
  return {
    error: raw?.error ?? [],
    warn:  raw?.warn  ?? [],
    info:  raw?.info  ?? [],
    all:   raw?.all   ?? [ ...(raw?.error ?? []), ...(raw?.warn ?? []), ...(raw?.info ?? []) ],
  };
};

// 统一拿到 buckets
const buckets: IssuesBuckets = normalizeIssues((status as any)?.result?.issues);

// 想要三栏就分别用 error/warn/info：
const severe: Issue[] = buckets.error;
const warn:   Issue[] = buckets.warn;
const info:   Issue[] = buckets.info;

// 想要单卡合并展示就用：
const allIssues: Issue[] = buckets.all;


  return (
    <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
      <header className="flex items-baseline justify-between">
        <h1 className="text-3xl font-bold">GovBudgetChecker</h1>
        <span className="text-slate-500">规则文件：v3.3</span>
      </header>

      {/* 上传区 */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-semibold">上传预算/决算 PDF</h2>
        <p className="mt-2 text-sm text-slate-600">
          先上传，然后点击“开始解析”。解析结果会自动展示为结果卡片。
        </p>

        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <label className="relative inline-flex">
            <input
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={onPickFile}
            />
            <span className="cursor-pointer rounded-md bg-slate-900 px-4 py-2 text-white">
              选择 PDF 并上传
            </span>
          </label>

          <input
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="粘贴 PDF 链接（http/https）"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button
            onClick={onUploadByUrl}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
          >
            通过链接上传
          </button>

          <button
            onClick={onAnalyze}
            disabled={!job?.job_id || loading}
            className="rounded-md bg-indigo-600 px-4 py-2 text-white disabled:opacity-50"
            title={job?.job_id ? `job ${job.job_id}` : "请先上传文件"}
          >
            {loading ? "解析中…" : "开始解析"}
          </button>
        </div>

        {/* 顶部状态条 */}
        <div className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-slate-700">
          <div>解析返回：{status ? JSON.stringify({ job_id: status.job_id, status: status.status }) : "（等待上传）"}</div>
          <div>状态：{status ? JSON.stringify(status) : "（尚未轮询）"}</div>
        </div>
      </section>

      {/* 结果卡片 */}
      <section className="space-y-4">
        <h3 className="text-lg font-semibold">结果卡片</h3>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <ResultCard title="严重问题" issues={severe} tone="danger" />
          <ResultCard title="一般问题" issues={warn} tone="warning" />
          <ResultCard title="提示信息" issues={info} tone="info" />
        </div>

        {/* 如果完全无问题 */}
        {allIssues.length === 0 && status?.status === "done" && (
          <ResultCard title="没有发现问题" issues={[]} tone="ok" />
        )}
      </section>

      {/* 调试日志 */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h3 className="text-lg font-semibold">调试日志</h3>
        <p className="mt-1 text-sm text-slate-500">
          上传后点击“开始解析”，结果会显示在这里。
        </p>
        <div className="mt-4 h-56 overflow-auto rounded-md border bg-slate-50 p-3 text-xs leading-6">
          {log.length === 0 ? (
            <p className="text-slate-500">（空）</p>
          ) : (
            log.map((l, i) => <div key={i}>{l}</div>)
          )}
        </div>
      </section>
    </main>
  );
}
