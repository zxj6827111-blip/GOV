"use client";

import { useState } from "react";
import EnhancedIssueCard from "./EnhancedIssueCard";
import { IssueItem } from "./IssueTabs";

interface Evidence {
  id: string;
  text: string;
  page: number;
  coordinates?: {
    x1: number;
    y1: number; 
    x2: number;
    y2: number;
  };
  screenshot_url?: string;
  confidence?: number;
}

interface EnhancedIssueItem {
  id: string;
  source: "ai" | "rule";
  rule_id?: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  title: string;
  message: string;
  evidence?: Evidence[];
  location: {
    section?: string;
    table?: string;
    row?: string;
    col?: string;
    page?: number;
  };
  metrics: Record<string, any>;
  suggestion?: string;
  tags: string[];
  created_at: number;
  attachments?: {
    screenshots?: string[];
    documents?: string[];
  };
}

interface ResultDisplayProps {
  jobId: string;
  issues: IssueItem[];
  mode?: "list" | "grid";
  enableExport?: boolean;
}

export default function ResultDisplay({ 
  jobId, 
  issues, 
  mode = "list",
  enableExport = true 
}: ResultDisplayProps) {
  const [selectedSeverity, setSelectedSeverity] = useState<string>("all");
  const [selectedSource, setSelectedSource] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"severity" | "page" | "time">("severity");

  // 决算化映射与预算项屏蔽（前端兜底）
  function mapDecisionWordingOnce(s?: string): string {
    if (!s) return s as any;
    return s
      .replace(/预算收支总表/g, "收入支出决算总表")
      .replace(/预算收入表/g, "收入决算表")
      .replace(/预算支出表/g, "支出决算表")
      .replace(/预算执行情况/g, "决算执行情况")
      .replace(/预算表/g, "决算表")
      .replace(/预算/g, "决算");
  }
  function sanitizeIssue(issue: IssueItem): IssueItem | null {
    const hasBudget =
      /预算/.test(issue.title || "") ||
      /预算/.test(issue.message || "") ||
      (Array.isArray((issue as any).tags) && (issue as any).tags.some((t: string) => /预算/.test(t)));
    // 强绑定预算的条目直接屏蔽（暂不展示，等待预算系统阶段再开放）
    if (hasBudget) return null;
    // 其余做“决算化映射”
    const mapped: any = { ...issue };
    if (typeof mapped.title === "string") mapped.title = mapDecisionWordingOnce(mapped.title);
    if (typeof mapped.message === "string") mapped.message = mapDecisionWordingOnce(mapped.message);
    if (Array.isArray(mapped.tags)) {
      mapped.tags = mapped.tags.map((t: string) => mapDecisionWordingOnce(t));
    }
    return mapped as IssueItem;
  }
  const sanitized = issues.map(sanitizeIssue).filter(Boolean) as IssueItem[];

  // 过滤和排序逻辑
  const filteredIssues = sanitized.filter(issue => {
    // 严重程度过滤
    if (selectedSeverity !== "all" && issue.severity !== selectedSeverity) {
      return false;
    }
    
    // 来源过滤
    if (selectedSource !== "all" && issue.source !== selectedSource) {
      return false;
    }
    
    // 搜索过滤
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      return (
        issue.title.toLowerCase().includes(query) ||
        issue.message.toLowerCase().includes(query) ||
        (issue.rule_id && issue.rule_id.toLowerCase().includes(query))
      );
    }
    
    return true;
  });

  const sortedIssues = [...filteredIssues].sort((a, b) => {
    if (sortBy === "severity") {
      const severityOrder = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };
      return (severityOrder[b.severity as keyof typeof severityOrder] || 0) - 
             (severityOrder[a.severity as keyof typeof severityOrder] || 0);
    } else if (sortBy === "page") {
      return (a.location.page || 0) - (b.location.page || 0);
    } else if (sortBy === "time") {
      return b.created_at - a.created_at;
    }
    return 0;
  });

  // 统计信息
  const stats = sanitized.reduce((acc, issue) => {
    acc.total += 1;
    acc[issue.severity] = (acc[issue.severity] || 0) + 1;
    if (issue.source === "ai") acc.ai += 1;
    else acc.rule += 1;
    return acc;
  }, { total: 0, critical: 0, high: 0, medium: 0, low: 0, info: 0, ai: 0, rule: 0 } as Record<string, number>);

  // 将IssueItem转换为EnhancedIssueItem（模拟证据数据）
  const enhancedIssues: EnhancedIssueItem[] = sortedIssues.map(issue => ({
    ...issue,
    evidence: issue.location.page ? [{
      id: `evidence_${issue.id}`,
      text: (issue.message || "").substring(0, 100) + (((issue.message || "").length > 100) ? "..." : ""),
      page: issue.location.page,
      confidence: 0.85
    }] : []
  }));

  return (
    <div className="w-full max-w-7xl mx-auto p-6">
      {/* 头部统计 */}
      <div className="mb-6 bg-white rounded-lg shadow-sm border p-4">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">检测结果概览</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900">{stats.total}</div>
            <div className="text-sm text-gray-500">总计</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">{stats.critical + stats.high}</div>
            <div className="text-sm text-gray-500">严重/高危</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-yellow-600">{stats.medium}</div>
            <div className="text-sm text-gray-500">中等</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.low + stats.info}</div>
            <div className="text-sm text-gray-500">低危/信息</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">{stats.ai}</div>
            <div className="text-sm text-gray-500">AI检测</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-purple-600">{stats.rule}</div>
            <div className="text-sm text-gray-500">规则检测</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-indigo-600">
              {issues.filter(i => i.evidence && i.evidence.length > 0).length}
            </div>
            <div className="text-sm text-gray-500">有证据</div>
          </div>
        </div>
      </div>

      {/* 对齐报告入口 */}
      <div className="mb-4">
        {jobId ? (
          <button
            onClick={() => window.open(`/report/${jobId}`, "_blank")}
            className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
            title="打开该 Job 的模板对齐报告（前端可视化）"
          >
            查看对齐报告
          </button>
        ) : (
          <span className="text-sm text-gray-400">暂无 jobId，无法查看对齐报告</span>
        )}
      </div>

      {/* 过滤和搜索工具栏 */}
      <div className="mb-6 bg-white rounded-lg shadow-sm border p-4">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          {/* 搜索框 */}
          <div className="flex-1 max-w-md">
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg className="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="搜索问题..."
              />
            </div>
          </div>

          {/* 过滤器 */}
          <div className="flex flex-wrap gap-3">
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="block text-sm border border-gray-300 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            >
              <option value="all">所有严重程度</option>
              <option value="critical">严重</option>
              <option value="high">高危</option>
              <option value="medium">中等</option>
              <option value="low">低危</option>
              <option value="info">信息</option>
            </select>

            <select
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              className="block text-sm border border-gray-300 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            >
              <option value="all">所有来源</option>
              <option value="ai">AI检测</option>
              <option value="rule">规则检测</option>
            </select>

            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as "severity" | "page" | "time")}
              className="block text-sm border border-gray-300 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            >
              <option value="severity">按严重程度排序</option>
              <option value="page">按页码排序</option>
              <option value="time">按时间排序</option>
            </select>
          </div>
        </div>

        {/* 结果计数 */}
        <div className="mt-3 text-sm text-gray-600">
          显示 {enhancedIssues.length} / {issues.length} 个问题
        </div>
      </div>

      {/* 问题列表 */}
      <div className={`space-y-4 ${mode === "grid" ? "grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6" : ""}`}>
        {enhancedIssues.length > 0 ? (
          enhancedIssues.map((issue, idx) => (
            <EnhancedIssueCard
              key={`${issue.id}-${idx}`}
              issue={issue}
              jobId={jobId}
              enableExport={enableExport}
              showSource={true}
              compact={mode === "grid"}
            />
          ))
        ) : (
          <div className="text-center py-12 bg-white rounded-lg border">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">没有找到匹配的问题</h3>
            <p className="mt-1 text-sm text-gray-500">
              {sanitized.length === 0 ? "当前没有检测到任何问题" : "请调整筛选条件重试"}
            </p>
          </div>
        )}
      </div>

      {/* 批量操作工具栏 */}
      {enhancedIssues.length > 0 && enableExport && (
        <div className="mt-6 bg-white rounded-lg shadow-sm border p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-600">
              批量操作
            </div>
            <div className="flex space-x-3">
              <button
                onClick={async () => {
                  try {
                    const response = await fetch(`/api/jobs/${jobId}/evidence.zip`);
                    if (response.ok) {
                      const blob = await response.blob();
                      const url = window.URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `all_evidence_${jobId}.zip`;
                      document.body.appendChild(a);
                      a.click();
                      window.URL.revokeObjectURL(url);
                      document.body.removeChild(a);
                    }
                  } catch (error) {
                    console.error('批量下载失败:', error);
                  }
                }}
                className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                <svg className="-ml-1 mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                下载全部证据
              </button>
              
              <button
                onClick={async () => {
                  try {
                    const response = await fetch(`/api/jobs/${jobId}/export?format=csv`);
                    if (response.ok) {
                      const data = await response.json();
                      if (data.csv_data) {
                        const blob = new Blob([data.csv_data], { type: 'text/csv;charset=utf-8;' });
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `complete_report_${jobId}.csv`;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                        document.body.removeChild(a);
                      }
                    }
                  } catch (error) {
                    console.error('导出失败:', error);
                  }
                }}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                <svg className="-ml-1 mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                导出完整报告
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}