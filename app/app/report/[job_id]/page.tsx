"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

export default function ReportPage({ params }: { params: { job_id: string } }) {
  const { job_id } = params;
  const [md, setMd] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let aborted = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`/api/reports/${encodeURIComponent(job_id)}`, { cache: "no-store" });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || `加载失败(${res.status})`);
        }
        const text = await res.text();
        if (!aborted) setMd(text || "# 暂无报告内容");
      } catch (e: any) {
        if (!aborted) setError(e?.message || String(e));
      } finally {
        if (!aborted) setLoading(false);
      }
    }
    load();
    return () => { aborted = true; };
  }, [job_id]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(md || "");
      alert("已复制到剪贴板");
    } catch {
      // ignore
    }
  };

  const handleDownload = () => {
    const blob = new Blob([md || ""], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `alignment_report_${job_id}.md`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  return (
    <div className="w-full max-w-5xl mx-auto p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">模板对齐报告</h1>
        <div className="flex gap-2">
          <button
            onClick={handleCopy}
            className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          >
            复制Markdown
          </button>
          <button
            onClick={handleDownload}
            className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700"
          >
            下载Markdown
          </button>
        </div>
      </div>

      {loading && (
        <div className="text-sm text-gray-500">加载中...</div>
      )}
      {error && (
        <div className="text-sm text-red-600">加载失败：{error}</div>
      )}
      {!loading && !error && (
        <div className="prose max-w-none">
          <ReactMarkdown>{md}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}