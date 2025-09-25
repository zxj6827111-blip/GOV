"use client";

import { useState } from "react";
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

interface EnhancedIssueItem extends IssueItem {
  evidence?: Evidence[];
  attachments?: {
    screenshots?: string[];
    documents?: string[];
  };
}

interface EnhancedIssueCardProps {
  issue: EnhancedIssueItem;
  jobId?: string;
  onClick?: () => void;
  showSource?: boolean;
  compact?: boolean;
  enableExport?: boolean;
}

export default function EnhancedIssueCard({ 
  issue, 
  jobId,
  onClick, 
  showSource = true, 
  compact = false,
  enableExport = true
}: EnhancedIssueCardProps) {
  const [showEvidence, setShowEvidence] = useState(false);
  const [loadingScreenshots, setLoadingScreenshots] = useState(false);
  
  const getSeverityColor = (severity: string) => {
    const colors = {
      critical: "border-red-500 bg-red-50",
      high: "border-red-400 bg-red-50", 
      medium: "border-yellow-400 bg-yellow-50",
      low: "border-blue-400 bg-blue-50",
      info: "border-gray-400 bg-gray-50",
    };
    return colors[severity as keyof typeof colors] || colors.info;
  };

  const getSeverityBadge = (severity: string) => {
    const colors = {
      critical: "bg-red-100 text-red-800 border-red-200",
      high: "bg-red-100 text-red-800 border-red-200",
      medium: "bg-yellow-100 text-yellow-800 border-yellow-200", 
      low: "bg-blue-100 text-blue-800 border-blue-200",
      info: "bg-gray-100 text-gray-800 border-gray-200",
    };
    return colors[severity as keyof typeof colors] || colors.info;
  };

  const getSourceBadge = (source: string) => {
    return source === "ai"
      ? "bg-green-100 text-green-800 border-green-200"
      : "bg-purple-100 text-purple-800 border-purple-200";
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "critical":
      case "high":
        return (
          <svg className="w-4 h-4 text-red-600" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        );
      case "medium":
        return (
          <svg className="w-4 h-4 text-yellow-600" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        );
      default:
        return (
          <svg className="w-4 h-4 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
        );
    }
  };

  const handleDownloadEvidence = async () => {
    if (!jobId) return;
    
    try {
      setLoadingScreenshots(true);
      const response = await fetch(`/api/jobs/${jobId}/evidence.zip`);
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `evidence_${jobId}.zip`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        throw new Error('证据文件下载失败');
      }
    } catch (error) {
      console.error('下载证据文件失败:', error);
      alert('证据文件下载失败，请稍后重试');
    } finally {
      setLoadingScreenshots(false);
    }
  };

  const handleExportCSV = async () => {
    if (!jobId) return;
    
    try {
      const response = await fetch(`/api/jobs/${jobId}/export?format=csv`);
      if (response.ok) {
        const data = await response.json();
        if (data.csv_data) {
          const blob = new Blob([data.csv_data], { type: 'text/csv;charset=utf-8;' });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `results_${jobId}.csv`;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
        }
      } else {
        throw new Error('CSV导出失败');
      }
    } catch (error) {
      console.error('CSV导出失败:', error);
      alert('CSV导出失败，请稍后重试');
    }
  };

  const handleExportJSON = async () => {
    if (!jobId) return;
    
    try {
      const response = await fetch(`/api/jobs/${jobId}/export?format=json`);
      if (response.ok) {
        const data = await response.json();
        const blob = new Blob([JSON.stringify(data.result, null, 2)], { 
          type: 'application/json;charset=utf-8;' 
        });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `results_${jobId}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        throw new Error('JSON导出失败');
      }
    } catch (error) {
      console.error('JSON导出失败:', error);
      alert('JSON导出失败，请稍后重试');
    }
  };

  if (compact) {
    return (
      <div
        className={`border-l-4 ${getSeverityColor(issue.severity)} p-3 cursor-pointer hover:shadow-sm transition-shadow`}
        onClick={onClick}
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2 mb-1">
              {getSeverityIcon(issue.severity)}
              <span className="text-sm font-medium text-gray-900 truncate">
                {issue.title}
              </span>
              {issue.rule_id && (
                <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                  {issue.rule_id}
                </span>
              )}
              {issue.evidence && issue.evidence.length > 0 && (
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded flex items-center">
                  <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clipRule="evenodd" />
                  </svg>
                  {issue.evidence.length}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-600 line-clamp-2">{issue.message}</p>
          </div>
          {issue.location.page && (
            <span className="text-xs text-gray-500 ml-2 flex-shrink-0">
              P{issue.location.page}
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="border rounded-lg bg-white shadow-sm hover:shadow-md transition-shadow duration-200">
      {/* 头部 */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center space-x-2 flex-wrap">
            {showSource && (
              <span
                className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${getSourceBadge(
                  issue.source
                )}`}
              >
                {issue.source === "ai" ? "AI检测" : "规则检测"}
              </span>
            )}
            <span
              className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${getSeverityBadge(
                issue.severity
              )}`}
            >
              {getSeverityIcon(issue.severity)}
              <span className="ml-1">
                {issue.severity === 'critical' ? '严重' : 
                 issue.severity === 'high' ? '高' :
                 issue.severity === 'medium' ? '中' :
                 issue.severity === 'low' ? '低' : '信息'}
              </span>
            </span>
            {issue.rule_id && (
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-gray-100 text-gray-700 border border-gray-200">
                {issue.rule_id}
              </span>
            )}
          </div>
          
          <div className="flex items-center space-x-2 text-xs text-gray-500">
            {issue.location.page && (
              <span className="bg-gray-100 px-2 py-1 rounded flex items-center">
                <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                </svg>
                第 {issue.location.page} 页
              </span>
            )}
          </div>
        </div>

        {/* 标题和描述 */}
        <h4 className="font-semibold text-gray-900 mb-2 text-base leading-tight cursor-pointer" onClick={onClick}>
          {issue.title}
        </h4>
        <p className="text-sm text-gray-600 leading-relaxed">{issue.message}</p>
      </div>

      {/* 证据和截图区域 */}
      {issue.evidence && issue.evidence.length > 0 && (
        <div className="p-4 bg-gray-50">
          <div className="flex items-center justify-between mb-3">
            <h5 className="text-sm font-medium text-gray-700 flex items-center">
              <svg className="w-4 h-4 mr-2 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clipRule="evenodd" />
              </svg>
              证据片段 ({issue.evidence.length})
            </h5>
            <button
              onClick={() => setShowEvidence(!showEvidence)}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
            >
              {showEvidence ? '收起' : '展开'}
            </button>
          </div>
          
          {showEvidence && (
            <div className="space-y-3">
              {issue.evidence.map((evidence, index) => (
                <div key={evidence.id || index} className="bg-white rounded border p-3">
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-xs text-gray-500">第 {evidence.page} 页</span>
                    {evidence.confidence && (
                      <span className="text-xs text-gray-500">
                        置信度: {Math.round(evidence.confidence * 100)}%
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-700 mb-2">{evidence.text}</p>
                  {evidence.screenshot_url && (
                    <div className="mt-2">
                      <img 
                        src={evidence.screenshot_url} 
                        alt={`证据截图 ${index + 1}`}
                        className="max-w-full h-auto rounded border border-gray-200 cursor-pointer hover:shadow-lg transition-shadow"
                        onClick={() => window.open(evidence.screenshot_url, '_blank')}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 操作按钮区域 */}
      {enableExport && (
        <div className="p-4 border-t border-gray-100 bg-gray-50">
          <div className="flex items-center justify-between">
            <div className="flex space-x-2">
              {jobId && (
                <button
                  onClick={handleDownloadEvidence}
                  disabled={loadingScreenshots}
                  className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
                >
                  {loadingScreenshots ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-gray-500" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      下载中...
                    </>
                  ) : (
                    <>
                      <svg className="-ml-1 mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      下载证据
                    </>
                  )}
                </button>
              )}
            </div>
            
            <div className="flex space-x-2">
              <button
                onClick={handleExportCSV}
                className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
              >
                <svg className="-ml-1 mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                导出CSV
              </button>
              <button
                onClick={handleExportJSON}
                className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                <svg className="-ml-1 mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                导出JSON
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}