"use client";

import { useState, useEffect, useRef } from "react";
import IssueTabs, { DualModeResult, IssueItem } from "./components/IssueTabs";
import IssueList from "./components/IssueList";
import IssueCard from "./components/IssueCard";

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
  rule_id?: string;
  severity: "critical" | "error" | "warn" | "info" | string;
  message: string;
  location?: { page?: number; [k: string]: any };
  source?: "ai" | "local_rules" | "AI_VALIDATOR" | string; // 扩展来源类型
  metadata?: { [k: string]: any }; // 新增：元数据字段
};

type ResultPayload = {
  summary: string;
  issues: Issue[] | { error: Issue[]; warn: Issue[]; info: Issue[]; all: Issue[] };
  meta?: Record<string, any>;
  // 新增：双模式结果支持
  dual_mode?: DualModeResult;
  mode?: "local" | "ai" | "dual";
};

export default function HomePage() {
  // UI 状态
  const [log, setLog] = useState<string[]>([]);
  const [job, setJob] = useState<UploadResp | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [url, setUrl] = useState("");
  const [uploadComplete, setUploadComplete] = useState(false);
  const [selectedIssue, setSelectedIssue] = useState<IssueItem | null>(null);
  const [viewMode, setViewMode] = useState<"tabs" | "list" | "card">("tabs");
  const [showDebugLog, setShowDebugLog] = useState(false);
  const [aiAssistEnabled, setAiAssistEnabled] = useState<boolean | null>(null);
  const [aiExtractorAlive, setAiExtractorAlive] = useState<boolean | null>(null);
  const [aiExtractorPingMs, setAiExtractorPingMs] = useState<number | null>(null);
  const [configLatencyMs, setConfigLatencyMs] = useState<number | null>(null);
  const [lastAnalyzeLatencyMs, setLastAnalyzeLatencyMs] = useState<number | null>(null);
  // 检测选项状态
  const [useLocalRules, setUseLocalRules] = useState(true);
  const [useAiAssist, setUseAiAssist] = useState(true);
  const pollTimer = useRef<any>(null);
  
  // 任务卡住检测状态
  const [progressHistory, setProgressHistory] = useState<number[]>([]);
  const [showStuckWarning, setShowStuckWarning] = useState(false);

  function appendLog(s: string) {
    setLog((prev) => [...prev, s].slice(-200));
  }

  // 获取AI辅助状态
  useEffect(() => {
    const fetchConfig = async () => {
      const start = Date.now();
      try {
        const response = await fetch('/api/config', { cache: 'no-store' });
        const config = await response.json();
        const ms = (config && typeof config.backend_response_ms === 'number') ? config.backend_response_ms : (Date.now() - start);
        setConfigLatencyMs(ms);
        setAiExtractorAlive(config.ai_extractor_alive ?? null);
        setAiExtractorPingMs(typeof config.ai_extractor_ping_ms === 'number' ? config.ai_extractor_ping_ms : null);
        // 仅当后端开启且AI服务连通性为true时才认为AI可用
        const enabled = !!config.ai_assist_enabled && config.ai_extractor_alive === true;
        setAiAssistEnabled(enabled);
      } catch (error) {
        console.error('Failed to fetch config:', error);
        setAiAssistEnabled(false);
        setAiExtractorAlive(null);
        setAiExtractorPingMs(null);
        setConfigLatencyMs(Date.now() - start);
      }
    };
    fetchConfig();
  }, []);

  // 轮询
  useEffect(() => {
    if (!job?.job_id) return;
    if (pollTimer.current) clearInterval(pollTimer.current);

    pollTimer.current = setInterval(async () => {
      try {
        const r = await fetch(`/api/jobs/${job.job_id}/status`, { cache: "no-store" });
        const raw: any = await r.json();

        // 兼容新旧两种后端返回结构，归一化顶层 status/progress 字段，便于前端统一处理
        const js: any = { ...raw };
        if (js && js.meta) {
          if (js.status === undefined && js.meta.status) {
            // 将后端 meta.status 映射为顶层状态
            const s = js.meta.status;
            js.status =
              s === "failed"
                ? "error"
                : s === "queued"
                ? "queued"
                : s === "processing"
                ? "processing"
                : s === "done" || s === "completed"
                ? "done"
                : "unknown";
          }
          if (js.progress === undefined && typeof js.meta.progress === "number") {
            js.progress = js.meta.progress;
          }
          // 若上面未提供 progress，但状态已为完成，则兜底设置为 100
          if ((js.progress === undefined || js.progress === null) && js.status === "done") {
            js.progress = 100;
          }
        }
        // 如果没有任何状态字段，但存在结果（ai_findings/rule_findings/merged），认为任务已完成
        if (js.status === undefined && (js.ai_findings !== undefined || js.rule_findings !== undefined || js.merged !== undefined)) {
          js.status = "done";
          if (js.progress === undefined) js.progress = 100;
        }

        setStatus(js as any);
        appendLog(`状态: HTTP ${r.status} → ${JSON.stringify(js)}`);
        
        // 任务卡住检测逻辑
        if (js.status === "processing" && 'progress' in js && js.progress !== undefined) {
          setProgressHistory(prev => {
            const newHistory = [...prev, js.progress!].slice(-3); // 保留最近3次进度
            
            // 检查是否连续3次进度未变化
            if (newHistory.length === 3 && 
                newHistory[0] === newHistory[1] && 
                newHistory[1] === newHistory[2] &&
                newHistory[0] < 100) {
              setShowStuckWarning(true);
            } else {
              setShowStuckWarning(false);
            }
            
            return newHistory;
          });
        } else {
          // 重置检测状态
          setProgressHistory([]);
          setShowStuckWarning(false);
        }
        
        if (js.status === "done" || js.status === "error") {
          clearInterval(pollTimer.current);
          setProgressHistory([]);
          setShowStuckWarning(false);
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
      setUploadComplete(true);
    } catch (e: any) {
      appendLog(`上传失败: ${e?.message || String(e)}`);
      setUploadComplete(false);
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
      setUploadComplete(true);
    } catch (e: any) {
      appendLog(`链接上传失败: ${e?.message || String(e)}`);
      setUploadComplete(false);
    }
  }

  // 触发解析
  async function onAnalyze() {
    if (!job?.job_id) return;
    
    // 检查是否至少选择了一种检测方式
    if (!useLocalRules && !useAiAssist) {
      appendLog("错误: 请至少选择一种检测方式");
      return;
    }
    
    try {
      setLoading(true);
      const t0 = Date.now();
      appendLog(`开始解析（job ${job.job_id.slice(0, 8)}...）`);
      
      // 构建请求参数
      const body = {
        use_local_rules: useLocalRules,
        use_ai_assist: useAiAssist,
        mode: useLocalRules && useAiAssist ? "dual" : useLocalRules ? "local" : "ai"
      };
      
      const r = await fetch(`/api/analyze/${job.job_id}`, { 
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body)
      });
      const js = await r.json();
      setLastAnalyzeLatencyMs(Date.now() - t0);
      appendLog(`解析返回: HTTP ${r.status} → ${JSON.stringify(js)}`);
      if (!r.ok) throw new Error(JSON.stringify(js));
      // 状态会被轮询拉到
    } catch (e: any) {
      appendLog(`解析错误: ${e?.message || String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  // ===== 单卡片：准备 issues 数据（逻辑区） =====
interface IssuesBuckets {
  error: Issue[];
  warn: Issue[];
  info: Issue[];
  all: Issue[];
}

function normalizeIssues(raw: any): IssuesBuckets {
  const empty: IssuesBuckets = { error: [], warn: [], info: [], all: [] };
  if (!raw) return empty;

  // 1) 后端返回 { error:[], warn:[], info:[], all:[] }
  if (typeof raw === "object" && Array.isArray(raw.all)) {
    const all = raw.all as Issue[];
    return {
      error: Array.isArray(raw.error) ? (raw.error as Issue[]) : all.filter((x) => (x.severity ?? "info") === "error"),
      warn: Array.isArray(raw.warn) ? (raw.warn as Issue[]) : all.filter((x) => (x.severity ?? "info") === "warn"),
      info: Array.isArray(raw.info) ? (raw.info as Issue[]) : all.filter((x) => (x.severity ?? "info") === "info"),
      all,
    };
  }

  // 2) 兼容旧版只给数组
  if (Array.isArray(raw)) {
    const all = raw as Issue[];
    return {
      error: all.filter((x) => (x.severity ?? "info") === "error"),
      warn: all.filter((x) => (x.severity ?? "info") === "warn"),
      info: all.filter((x) => (x.severity ?? "info") === "info"),
      all,
    };
  }

  // 3) 兼容只有 error/warn/info 三桶
  const obj = raw as { error?: Issue[]; warn?: Issue[]; info?: Issue[] };
  const error = Array.isArray(obj.error) ? obj.error : [];
  const warn = Array.isArray(obj.warn) ? obj.warn : [];
  const info = Array.isArray(obj.info) ? obj.info : [];
  return { error, warn, info, all: [...error, ...warn, ...info] };
}

// 统一拿到 buckets（status 为后端轮询结果对象）
const buckets: IssuesBuckets = normalizeIssues((status as any)?.result?.issues);

// 单卡片展示使用：allIssues
const allIssues: Issue[] = buckets.all;

// 检查是否为双模式结果
// 检查三种可能的数据格式：
// 1. 新格式：status.result.dual_mode (来自新API)
// 2. 旧格式：status.results (来自jobs_adv2 API)
// 3. 直接双模式格式：status.ai_findings/rule_findings (来自/api/jobs/{id}/status)
const isDualMode = (
  ((status as any)?.result?.mode === "dual" && (status as any)?.result?.dual_mode) ||
  ((status as any)?.results?.ai_findings !== undefined || (status as any)?.results?.rule_findings !== undefined) ||
  ((status as any)?.results?.aiFindings !== undefined || (status as any)?.results?.ruleFindings !== undefined) ||
  ((status as any)?.ai_findings !== undefined || (status as any)?.rule_findings !== undefined) ||
  ((status as any)?.aiFindings !== undefined || (status as any)?.ruleFindings !== undefined)
);

let dualModeResult: DualModeResult | null = null;
if (isDualMode) {
  // 优先使用新格式
  if ((status as any)?.result?.dual_mode) {
    dualModeResult = (status as any).result.dual_mode;
  } 
  // 回退到旧格式，从status.results构建DualModeResult
  else if ((status as any)?.results) {
    const results = (status as any).results;
    dualModeResult = {
      ai_findings: results.ai_findings || results.aiFindings || [],
      rule_findings: results.rule_findings || results.ruleFindings || [],
      merged: results.merged || {
        totals: { ai: 0, rule: 0, merged: 0, conflicts: 0, agreements: 0, ai_only: 0, rule_only: 0 },
        conflicts: [],
        agreements: [],
        merged_ids: [],
        ai_only: [],
        rule_only: []
      },
      meta: results.meta || {}
    };
  }
  // 处理直接双模式格式（来自/api/jobs/{id}/status）
  else if ((status as any)?.ai_findings !== undefined || (status as any)?.rule_findings !== undefined ||
           (status as any)?.aiFindings !== undefined || (status as any)?.ruleFindings !== undefined) {
    dualModeResult = {
      ai_findings: (status as any).ai_findings || (status as any).aiFindings || [],
      rule_findings: (status as any).rule_findings || (status as any).ruleFindings || [],
      merged: (status as any).merged || {
        totals: { ai: 0, rule: 0, merged: 0, conflicts: 0, agreements: 0, ai_only: 0, rule_only: 0 },
        conflicts: [],
        agreements: [],
        merged_ids: [],
        ai_only: [],
        rule_only: []
      },
      meta: (status as any).meta || {}
    };
  }
}

// 转换传统Issue为IssueItem格式
const convertToIssueItem = (issue: Issue, index: number): IssueItem => ({
  id: `issue_${index}`,
  source: ((issue as any).source === "ai" || (issue as any).source === "AI_VALIDATOR") ? "ai" : "rule",
  rule_id: (issue as any).rule_id || issue.rule || "",
  severity: (issue.severity === "error" ? "high" : 
            issue.severity === "warn" ? "medium" : 
            issue.severity === "critical" ? "critical" : "info") as any,
  title: issue.message.split('。')[0] + (issue.message.includes('。') ? '。' : ''),
  message: issue.message,
  evidence: [],
  location: {
    section: undefined,
    table: undefined,
    row: undefined,
    col: undefined,
    page: issue.location?.page
  },
  metrics: {},
  suggestion: undefined,
  tags: ((issue as any).rule_id || issue.rule) ? [(issue as any).rule_id || issue.rule] : [],
  created_at: Date.now() / 1000
});

// 为问题添加来源标识
const enrichedIssues = allIssues.map((issue) => {
  // 根据多种条件判断来源
  let source = 'local_rules'; // 默认为本地规则
  
  // 检查是否为AI检测问题的多种标识
  if (
    // 1. rule字段包含AI标识
    issue.rule?.startsWith('AI-') || 
    issue.rule?.includes('ai') || 
    issue.rule?.includes('AI') ||
    (issue as any).rule_id?.startsWith('AI_') ||
    (issue as any).rule_id?.includes('AI') ||
    
    // 2. metadata中标记为AI发现
    (issue as any).metadata?.ai_discovered === true ||
    (issue as any).metadata?.discovery_method === 'ai_extraction' ||
    
    // 3. 描述中包含AI相关信息
    issue.message?.includes('AI检测') ||
    issue.message?.includes('AI发现') ||
    
    // 4. 特定的AI规则ID
    (issue as any).rule_id === 'AI_DISCOVERED' ||
    
    // 5. 来源字段直接标识（如果后端提供）
    (issue as any).source === 'ai' ||
    (issue as any).source === 'AI_VALIDATOR'
  ) {
    source = 'ai';
  }
  
  return {
    ...issue,
    source
  };
});

// 获取问题来源标识的显示文本和样式
const getSourceBadge = (source: string) => {
  if (source === 'ai') {
    return {
      text: 'AI检测',
      className: 'bg-blue-100 text-blue-700 border border-blue-200'
    };
  } else {
    return {
      text: '本地规则',
      className: 'bg-green-100 text-green-700 border border-green-200'
    };
  }
};

// 小徽标颜色
const badgeColor = (sev: string) =>
  sev === "error"
    ? "bg-red-100 text-red-700"
    : sev === "warn"
    ? "bg-amber-100 text-amber-700"
    : "bg-sky-100 text-sky-700";

  return (
    <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
      <header className="flex items-baseline justify-between">
        <h1 className="text-3xl font-bold">政府决算公开检查</h1>
        <span className="text-slate-500"></span>
      </header>

      {/* 上传区 */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-semibold">上传决算PDF</h2>

        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <label className="relative inline-flex">
            <input
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={onPickFile}
            />
            <span className="cursor-pointer rounded-md bg-slate-900 px-4 py-2 text-white">
              {uploadComplete ? "上传完成" : "选择 PDF 并上传"}
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
            {loading ? "检查中…" : "开始检查"}
          </button>
        </div>

        {/* 检测选项 */}
        <div className="mt-4 space-y-3">
          <h3 className="text-sm font-medium text-slate-700">检测选项</h3>
          <div className="flex flex-col space-y-2">
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={useLocalRules}
                onChange={(e) => setUseLocalRules(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span className="text-sm text-slate-700">本地规则检测</span>
              <span className="text-xs text-slate-500">（基于预定义规则进行检测）</span>
            </label>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={useAiAssist}
                onChange={(e) => setUseAiAssist(e.target.checked)}
                disabled={aiAssistEnabled !== true}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
              />
              <span className="text-sm text-slate-700">AI辅助检测</span>
              <span className="text-xs text-slate-500">
                {aiAssistEnabled === true ? "（使用豆包AI进行智能分析）" : (aiExtractorAlive === false ? "（AI服务不可达）" : "（AI服务未启用）")}
              </span>
            </label>
            <div className="text-xs text-slate-500 flex flex-wrap gap-3">
              {typeof configLatencyMs === 'number' && (
                <span>配置耗时：{configLatencyMs} ms</span>
              )}
              {typeof aiExtractorPingMs === 'number' && (
                <span>AI服务Ping：{aiExtractorPingMs} ms{aiExtractorAlive === false ? '（不可达）' : ''}</span>
              )}
              {typeof lastAnalyzeLatencyMs === 'number' && (
                <span>本次触发耗时：{lastAnalyzeLatencyMs} ms</span>
              )}
            </div>
          </div>
          {!useLocalRules && !useAiAssist && (
            <p className="text-sm text-red-600">⚠️ 请至少选择一种检测方式</p>
          )}
        </div>

        {/* AI检测模式提示框 */}
        <div className="mt-4 rounded-lg bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 p-4">
          <div className="flex items-center space-x-2">
            <div className="flex-shrink-0">
              <svg className="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-medium text-blue-900">当前检测模式</h4>
              <p className="text-sm text-blue-700 mt-1">
                {(() => {
                  const modes = [] as string[];
                  if (useLocalRules) modes.push("本地规则");
                  if (useAiAssist && aiAssistEnabled === true) modes.push("AI辅助");
                  
                  if (modes.length === 0) {
                    return (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800 mr-2">
                        未选择检测方式
                      </span>
                    );
                  }
                  
                  const modeText = modes.join(" + ");
                  const bgColor = modes.length === 2 ? "bg-green-100 text-green-800" : "bg-yellow-100 text-yellow-800";
                  
                  return (
                    <>
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${bgColor} mr-2`}>
                        {modeText}
                      </span>
                      {modes.length === 2 
                        ? "本次检查将使用豆包AI辅助 + 本地规则引擎进行双重检测，提供更全面的问题识别"
                        : modes.includes("AI辅助")
                        ? "本次检查将仅使用豆包AI进行智能检测"
                        : "本次检查将仅使用本地规则引擎进行检测"
                      }
                    </>
                  );
                })()}
              </p>
            </div>
          </div>

          {/* 卡住降级操作区 */}
          {showStuckWarning && (
            <div className="mt-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
              检测进度长时间无变化，可能已卡住。您可以：
              <div className="mt-2 flex gap-2">
                <button
                  onClick={() => {
                    setUseAiAssist(false);
                    appendLog('已切换为仅本地规则，建议重新点击“开始检查”');
                  }}
                  className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50"
                >
                  仅本地规则重新解析
                </button>
                <button
                  onClick={() => {
                    setShowDebugLog(true);
                  }}
                  className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50"
                >
                  查看调试日志
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 任务卡住警告横幅 */}
        {showStuckWarning && (
          <div className="mt-4 rounded-lg bg-yellow-50 border border-yellow-200 p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800">
                  任务疑似卡住
                </h3>
                <div className="mt-2 text-sm text-yellow-700">
                  <p>检测到进度连续3次未变化，任务可能遇到问题。以下是当前已获取的结果：</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 进度条 */}
        {(loading || (status && status.status !== "done" && status.status !== "error")) && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-sm text-slate-600 mb-2">
              <span>检查进度</span>
              <span>
                {(status && 'progress' in status) ? `${status.progress}%` : 
                 loading ? "准备中..." : 
                 status?.status === "queued" ? "排队中..." : 
                 status?.status === "processing" ? "处理中..." : "0%"}
              </span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-2">
              <div 
                className="bg-indigo-600 h-2 rounded-full transition-all duration-300 ease-out"
                style={{ 
                  width: `${(status && 'progress' in status) ? status.progress : (loading ? 10 : 0)}%` 
                }}
              ></div>
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {status?.status === "queued" && "任务已提交，等待处理..."}
              {status?.status === "processing" && (
                (status as any)?.stage ? (status as any).stage : "正在分析PDF文档..."
              )}
              {loading && "正在启动检查任务..."}
            </div>
          </div>
        )}

        {/* 顶部状态条 - 隐藏 */}
        <div className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-slate-700" style={{display: 'none'}}>
          <div>解析返回：{status ? JSON.stringify({ job_id: status.job_id, status: status.status }) : "（等待上传）"}</div>
          <div>状态：{status ? JSON.stringify(status) : "（尚未轮询）"}</div>
        </div>
      </section>

      {/* ===== 问题展示区域 ===== */}
      <section className="mt-12">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-semibold">
            问题清单
            <span className="ml-2 text-base text-slate-500">
              ({isDualMode ? 
                `${dualModeResult?.merged.totals.merged || 0} 条` : 
                `${enrichedIssues.length} 条`})
            </span>
          </h2>
          
          {/* 视图切换按钮 */}
          <div className="flex items-center space-x-2">
            <span className="text-sm text-slate-600">视图:</span>
            <div className="flex rounded-lg border border-slate-200 p-1">
              <button
                onClick={() => setViewMode("tabs")}
                className={`px-3 py-1 text-sm rounded-md transition-colors ${
                  viewMode === "tabs" 
                    ? "bg-indigo-100 text-indigo-700" 
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                标签页
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`px-3 py-1 text-sm rounded-md transition-colors ${
                  viewMode === "list" 
                    ? "bg-indigo-100 text-indigo-700" 
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                列表
              </button>
              <button
                onClick={() => setViewMode("card")}
                className={`px-3 py-1 text-sm rounded-md transition-colors ${
                  viewMode === "card" 
                    ? "bg-indigo-100 text-indigo-700" 
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                卡片
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          {/* 双模式结果展示 */}
          {isDualMode && dualModeResult ? (
            <>
              {viewMode === "tabs" && (
                <IssueTabs 
                  result={dualModeResult} 
                  onIssueClick={setSelectedIssue}
                />
              )}
              {viewMode === "list" && (
                <IssueList 
                  issues={[...dualModeResult.ai_findings, ...dualModeResult.rule_findings]}
                  onIssueClick={setSelectedIssue}
                  showSource={true}
                  title="所有问题"
                />
              )}
              {viewMode === "card" && selectedIssue && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold">问题详情</h3>
                    <button
                      onClick={() => setSelectedIssue(null)}
                      className="text-slate-500 hover:text-slate-700"
                    >
                      ✕ 关闭
                    </button>
                  </div>
                  <IssueCard 
                    issue={selectedIssue}
                    showSource={true}
                  />
                </div>
              )}
              {viewMode === "card" && !selectedIssue && (
                <div className="text-center py-8 text-slate-500">
                  <p>请从标签页或列表视图中选择一个问题查看详情</p>
                </div>
              )}
            </>
          ) : (
            /* 传统模式结果展示 */
            <>
              {viewMode === "tabs" && (
                <div className="text-center py-8 text-slate-500">
                  <p>标签页视图仅在双模式下可用</p>
                  <p className="text-sm mt-2">请同时启用"本地规则检测"和"AI辅助检测"</p>
                </div>
              )}
              {(viewMode === "list" || viewMode === "tabs") && (
                <>
                  {enrichedIssues.length === 0 ? (
                    <div className="text-center py-8 text-slate-500">
                      <div className="w-16 h-16 mx-auto mb-4 text-slate-300">
                        <svg fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                      </div>
                      <p className="text-lg font-medium">没有发现问题</p>
                      <p className="text-sm">文档检查通过，未发现合规性问题</p>
                    </div>
                  ) : (
                    <IssueList 
                      issues={enrichedIssues.map(convertToIssueItem)}
                      onIssueClick={setSelectedIssue}
                      showSource={true}
                      title="检测结果"
                    />
                  )}
                </>
              )}
              {viewMode === "card" && selectedIssue && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold">问题详情</h3>
                    <button
                      onClick={() => setSelectedIssue(null)}
                      className="text-slate-500 hover:text-slate-700"
                    >
                      ✕ 关闭
                    </button>
                  </div>
                  <IssueCard 
                    issue={selectedIssue}
                    showSource={true}
                  />
                </div>
              )}
              {viewMode === "card" && !selectedIssue && (
                <div className="text-center py-8 text-slate-500">
                  <p>请从列表视图中选择一个问题查看详情</p>
                </div>
              )}
            </>
          )}

          {/* 兜底显示：当任务卡住且有部分结果时显示 */}
          {showStuckWarning && status && status.status === "processing" && (
            <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <h3 className="text-sm font-medium text-amber-800 mb-2">
                当前已获取的部分结果
              </h3>
              <div className="text-sm text-amber-700">
                {/* 显示当前状态中的部分结果 */}
                {(status as any)?.ai_findings && (status as any).ai_findings.length > 0 && (
                  <div className="mb-2">
                    <span className="font-medium">AI检测结果:</span> 已发现 {(status as any).ai_findings.length} 个问题
                  </div>
                )}
                {(status as any)?.rule_findings && (status as any).rule_findings.length > 0 && (
                  <div className="mb-2">
                    <span className="font-medium">规则检测结果:</span> 已发现 {(status as any).rule_findings.length} 个问题
                  </div>
                )}
                {(status as any)?.meta?.ai_error && (
                  <div className="mb-2 text-red-600">
                    <span className="font-medium">AI检测错误:</span> {(status as any).meta.ai_error}
                  </div>
                )}
                {(status as any)?.meta?.rule_error && (
                  <div className="mb-2 text-red-600">
                    <span className="font-medium">规则检测错误:</span> {(status as any).meta.rule_error}
                  </div>
                )}
                <p className="text-xs mt-2">
                  注意：这是任务未完成时的部分结果，可能不完整。建议等待任务完成或重新提交任务。
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* 调试日志 */}
      <div className="flex justify-center mb-4">
        <button
          onClick={() => setShowDebugLog(!showDebugLog)}
          className="rounded-md bg-slate-600 px-4 py-2 text-white hover:bg-slate-700"
        >
          {showDebugLog ? "隐藏调试日志" : "查看调试日志"}
        </button>
      </div>
      
      {showDebugLog && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="text-lg font-semibold">调试日志</h3>
          <p className="mt-1 text-sm text-slate-500">
            上传后点击"开始检查"，结果会显示在这里。
          </p>
          <div className="mt-4 h-56 overflow-auto rounded-md border bg-slate-50 p-3 text-xs leading-6">
            {log.length === 0 ? (
              <p className="text-slate-500">（空）</p>
            ) : (
              log.map((l, i) => <div key={i}>{l}</div>)
            )}
          </div>
        </section>
      )}
    </main>
  );
}
