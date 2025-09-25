"use client";

import { useState, useMemo } from "react";
import { IssueItem } from "./IssueTabs";

interface IssueListProps {
  issues: IssueItem[];
  onIssueClick?: (issue: IssueItem) => void;
  showSource?: boolean;
  title?: string;
}

export default function IssueList({ 
  issues, 
  onIssueClick, 
  showSource = false, 
  title 
}: IssueListProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"severity" | "created_at" | "page">("severity");

  const severityOrder = {
    critical: 5,
    high: 4,
    medium: 3,
    low: 2,
    info: 1,
  };

  const filteredAndSortedIssues = useMemo(() => {
    let filtered = issues.filter((issue) => {
      const matchesSearch = 
        issue.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        issue.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
        issue.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()));
      
      const matchesSeverity = severityFilter === "all" || issue.severity === severityFilter;
      const matchesSource = sourceFilter === "all" || issue.source === sourceFilter;
      
      return matchesSearch && matchesSeverity && matchesSource;
    });

    // 排序
    filtered.sort((a, b) => {
      switch (sortBy) {
        case "severity":
          return severityOrder[b.severity] - severityOrder[a.severity];
        case "created_at":
          return b.created_at - a.created_at;
        case "page":
          const pageA = a.location.page || 0;
          const pageB = b.location.page || 0;
          return pageA - pageB;
        default:
          return 0;
      }
    });

    return filtered;
  }, [issues, searchTerm, severityFilter, sourceFilter, sortBy]);

  const getSeverityBadge = (severity: string) => {
    const colors = {
      critical: "bg-red-100 text-red-800",
      high: "bg-red-100 text-red-800",
      medium: "bg-yellow-100 text-yellow-800",
      low: "bg-blue-100 text-blue-800",
      info: "bg-gray-100 text-gray-800",
    };
    return colors[severity as keyof typeof colors] || colors.info;
  };

  const getSourceBadge = (source: string) => {
    return source === "ai"
      ? "bg-green-100 text-green-800"
      : "bg-purple-100 text-purple-800";
  };

  const getSeverityText = (severity: string) => {
    const texts = {
      critical: "严重",
      high: "高",
      medium: "中",
      low: "低",
      info: "信息",
    };
    return texts[severity as keyof typeof texts] || severity;
  };

  if (issues.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <div className="w-16 h-16 mx-auto mb-4 text-gray-300">
          <svg fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        </div>
        <p className="text-lg font-medium">没有发现问题</p>
        <p className="text-sm">文档检查通过，未发现合规性问题</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 标题和统计 */}
      {title && (
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">{title}</h3>
          <span className="text-sm text-gray-500">
            共 {filteredAndSortedIssues.length} 个问题
          </span>
        </div>
      )}

      {/* 过滤和搜索控件 */}
      <div className="flex flex-col sm:flex-row gap-4 p-4 bg-gray-50 rounded-lg">
        {/* 搜索框 */}
        <div className="flex-1">
          <input
            type="text"
            placeholder="搜索问题标题、描述或标签..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>

        {/* 严重程度过滤 */}
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="all">所有严重程度</option>
          <option value="critical">严重</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
          <option value="info">信息</option>
        </select>

        {/* 来源过滤 */}
        {showSource && (
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">所有来源</option>
            <option value="ai">AI 检查</option>
            <option value="rule">本地规则</option>
          </select>
        )}

        {/* 排序 */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "severity" | "created_at" | "page")}
          className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="severity">按严重程度</option>
          <option value="created_at">按时间</option>
          <option value="page">按页码</option>
        </select>
      </div>

      {/* 问题列表 */}
      <div className="space-y-3">
        {filteredAndSortedIssues.map((issue, idx) => (
          <div
            key={`${issue.id}-${idx}`}
            className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer bg-white"
            onClick={() => onIssueClick?.(issue)}
          >
            {/* 头部信息 */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center space-x-2 flex-wrap">
                {showSource && (
                  <span
                    className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getSourceBadge(
                      issue.source
                    )}`}
                  >
                    {issue.source === "ai" ? "AI" : "规则"}
                  </span>
                )}
                <span
                  className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getSeverityBadge(
                    issue.severity
                  )}`}
                >
                  {getSeverityText(issue.severity)}
                </span>
                {issue.rule_id && (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-gray-100 text-gray-700">
                    {issue.rule_id}
                  </span>
                )}
              </div>
              <div className="flex items-center space-x-2 text-xs text-gray-500">
                {issue.location.page && (
                  <span>第 {issue.location.page} 页</span>
                )}
                <span>{new Date(issue.created_at * 1000).toLocaleTimeString()}</span>
              </div>
            </div>
            
            {/* 标题和描述 */}
            <h4 className="font-medium text-gray-900 mb-2 line-clamp-2">{issue.title}</h4>
            <p className="text-sm text-gray-600 mb-3 line-clamp-3">{issue.message}</p>
            
            {/* 位置信息 */}
            {(issue.location.section || issue.location.table) && (
              <div className="text-xs text-gray-500 mb-2">
                <span className="font-medium">位置：</span>
                {issue.location.section && <span>{issue.location.section}</span>}
                {issue.location.table && (
                  <span>
                    {issue.location.section && " > "}
                    {issue.location.table}
                  </span>
                )}
                {issue.location.row && <span> (行: {issue.location.row})</span>}
                {issue.location.col && <span> (列: {issue.location.col})</span>}
              </div>
            )}
            
            {/* 证据预览 */}
            {(issue.evidence && issue.evidence.length > 0) && (
              <div className="text-xs text-gray-500 mb-2">
                <span className="font-medium">证据：</span>
                <span className="italic">
                  "{(issue.evidence?.[0]?.text || "").substring(0, 120)}"
                  {((issue.evidence?.[0]?.text || "").length > 120) && "..."}
                </span>
              </div>
            )}

            {/* 指标信息 */}
            {Object.keys(issue.metrics).length > 0 && (
              <div className="text-xs text-gray-500 mb-2">
                <span className="font-medium">指标：</span>
                {Object.entries(issue.metrics).slice(0, 3).map(([key, value]) => (
                  <span key={key} className="ml-1">
                    {key}: {typeof value === 'number' ? value.toLocaleString() : value}
                  </span>
                ))}
              </div>
            )}
            
            {/* 标签 */}
            {issue.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {issue.tags.slice(0, 5).map((tag, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700"
                  >
                    {tag}
                  </span>
                ))}
                {issue.tags.length > 5 && (
                  <span className="text-xs text-gray-500">
                    +{issue.tags.length - 5} 更多
                  </span>
                )}
              </div>
            )}

            {/* 建议 */}
            {issue.suggestion && (
              <div className="mt-2 p-2 bg-blue-50 rounded text-xs">
                <span className="font-medium text-blue-700">建议：</span>
                <span className="text-blue-600">{issue.suggestion}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 无搜索结果 */}
      {filteredAndSortedIssues.length === 0 && issues.length > 0 && (
        <div className="text-center py-8 text-gray-500">
          <p>没有找到匹配的问题</p>
          <button
            onClick={() => {
              setSearchTerm("");
              setSeverityFilter("all");
              setSourceFilter("all");
            }}
            className="mt-2 text-indigo-600 hover:text-indigo-500 text-sm"
          >
            清除筛选条件
          </button>
        </div>
      )}
    </div>
  );
}