// app/app/api/jobs_adv/[job_id]/status/route.ts
import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

export const runtime = "nodejs";

// 与 /api/analyze 同步的“决算口径”工具
function mapDecisionWordingOnce(s: string): string {
  return s
    .replace(/预算收支总表/g, "收入支出决算总表")
    .replace(/预算收入表/g, "收入决算表")
    .replace(/预算支出表/g, "支出决算表")
    .replace(/预算执行情况/g, "决算执行情况")
    .replace(/预算支出明细表/g, "支出决算明细表")
    .replace(/预算收入明细表/g, "收入决算明细表")
    .replace(/预算资金/g, "决算资金")
    .replace(/预算编制/g, "决算编制")
    .replace(/预算管理/g, "决算管理")
    .replace(/预算监督/g, "决算监督")
    .replace(/预算公开/g, "决算公开")
    .replace(/预算表/g, "决算表")
    .replace(/预算/g, "决算");
}
function deepNormalize(obj: any): any {
  if (obj == null) return obj;
  if (typeof obj === "string") return mapDecisionWordingOnce(obj);
  if (Array.isArray(obj)) return obj.map((v) => deepNormalize(v));
  if (typeof obj === "object") {
    const out: any = {};
    for (const k of Object.keys(obj)) out[k] = deepNormalize(obj[k]);
    return out;
  }
  return obj;
}
// 无条件启用决算口径纠偏（用户要求屏蔽所有预算相关内容）
function normalizeDecisionWording(data: any): any {
  return deepNormalize(data);
}

// 无条件过滤含"预算"的问题项（用户要求屏蔽所有预算相关内容）
function filterOutBudget(data: any): any {
  if (!data) return data;

  const hasBudget = (obj: any): boolean => {
    const testStr = (s: any) => typeof s === "string" && /预算/.test(s);
    if (!obj) return false;
    if (testStr(obj.title) || testStr(obj.message)) return true;
    if (Array.isArray(obj.tags) && obj.tags.some((t: any) => testStr(String(t)))) return true;
    // 增加更多字段检查
    if (testStr(obj.description) || testStr(obj.content)) return true;
    if (obj.location && (testStr(obj.location.section) || testStr(obj.location.table))) return true;
    return false;
  };
  const cleanseArray = (arr: any[]) => (Array.isArray(arr) ? arr.filter((it) => !hasBudget(it)) : arr);

  if (Array.isArray((data as any).issues)) (data as any).issues = cleanseArray((data as any).issues);
  if (Array.isArray((data as any).ai_findings)) (data as any).ai_findings = cleanseArray((data as any).ai_findings);
  if (Array.isArray((data as any).rule_findings)) (data as any).rule_findings = cleanseArray((data as any).rule_findings);
  if (Array.isArray((data as any).merged)) (data as any).merged = cleanseArray((data as any).merged);
  
  // 处理嵌套的 result 对象
  if (data.result) {
    if (Array.isArray(data.result.issues)) data.result.issues = cleanseArray(data.result.issues);
    if (Array.isArray(data.result.ai_findings)) data.result.ai_findings = cleanseArray(data.result.ai_findings);
    if (Array.isArray(data.result.rule_findings)) data.result.rule_findings = cleanseArray(data.result.rule_findings);
    if (Array.isArray(data.result.merged)) data.result.merged = cleanseArray(data.result.merged);
  }
  
  return data;
}

/**
 * 仅保留预算↔决算对比结论（V33-110）；清空 AI 层结果，避免干扰
 */
function keepOnlyCompareRule(data: any): any {
  if (!data) return data;
  const keepV33110 = (arr: any[]) =>
    Array.isArray(arr) ? arr.filter((it: any) => it && (it.rule === "V33-110" || it.code === "V33-110")) : arr;

  const stripAI = (obj: any) => {
    if (!obj) return obj;
    if (Array.isArray(obj.ai_findings)) obj.ai_findings = [];
    return obj;
  };

  data = stripAI(data);
  if (Array.isArray((data as any).issues)) (data as any).issues = keepV33110((data as any).issues);
  if (Array.isArray((data as any).rule_findings)) (data as any).rule_findings = keepV33110((data as any).rule_findings);
  if (Array.isArray((data as any).merged)) (data as any).merged = keepV33110((data as any).merged);

  if (data.result) {
    data.result = stripAI(data.result);
    if (Array.isArray(data.result.issues)) data.result.issues = keepV33110(data.result.issues);
    if (Array.isArray(data.result.rule_findings)) data.result.rule_findings = keepV33110(data.result.rule_findings);
    if (Array.isArray(data.result.merged)) data.result.merged = keepV33110(data.result.merged);
  }

  return data;
}

import fs from "fs";
import path from "path";

function hasCompareIssues(data: any): boolean {
  const isV33110 = (it: any) => it && (it.rule === "V33-110" || it.code === "V33-110");
  const anyV33110 = (arr: any[]) => Array.isArray(arr) && arr.some(isV33110);
  if (!data) return false;
  if (anyV33110((data as any).issues)) return true;
  if (anyV33110((data as any).rule_findings)) return true;
  if (anyV33110((data as any).merged)) return true;
  if (data.result) {
    if (anyV33110(data.result.issues)) return true;
    if (anyV33110(data.result.rule_findings)) return true;
    if (anyV33110(data.result.merged)) return true;
  }
  return false;
}

function fallbackCompareExtract(jobId: string): any[] {
  try {
    const p = path.resolve(process.cwd(), "..", "uploads", jobId, "extracted_text.txt");
    if (!fs.existsSync(p)) return [];
    const raw = fs.readFileSync(p, "utf8") || "";
    if (!raw.trim()) return [];
    const txt = raw.replace(/\r/g, "").replace(/[ \t]+/g, " ").replace(/\n+/g, "\n");
    const pairRe = new RegExp(
      [
        "年初\\s*预算\\s*为\\s*",
        "(-?\\d+(?:,\\d{3})*(?:\\.\\d+)?)",
        "\\s*(?:亿元|万元|元)?",
        "[\\s\\S]{0,240}?",
        "(?:支出\\s*)?决算\\s*为\\s*",
        "(-?\\d+(?:,\\d{3})*(?:\\.\\d+)?)",
        "\\s*(?:亿元|万元|元)?",
        "[\\s\\S]{0,240}?",
        "(决算数\\s*(?:大于|小于|等于|持平|基本持平)\\s*预算数)"
      ].join(""),
      "g"
    );
    const reasonRe = /(主要原因|增减原因|变动原因)\s*[:：]\s*([^。]{1,240})/;
    const out: any[] = [];
    let m: RegExpExecArray | null;
    while ((m = pairRe.exec(txt))) {
      const bud = m[1], act = m[2], stmt = m[3];
      const tail = txt.slice(m.index, Math.min(txt.length, m.index + 400));
      const rm = reasonRe.exec(tail);
      const reason = rm ? rm[2].trim() : undefined;
      const clip = txt.slice(m.index, Math.min(txt.length, m.index + 120)).replace(/\s+/g, " ").trim();
      out.push({ rule: "V33-110", severity: "error", message: `年初预算=${bud}，决算=${act}（文本表述：${stmt}）`, location: { page: 1, pos: 0, clip }, reason_text: reason });
      if ((/大于|小于/.test(stmt)) && !reason) out.push({ rule: "V33-110", severity: "error", message: `文本表述为“${stmt}”，但未见主要原因说明（其中段落后）。`, location: { page: 1, pos: 0, clip } });
    }
    return out;
  } catch { return []; }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { job_id: string } }
) {
  try {
    const upstream = await fetch(`${apiBase}/jobs_adv2/${params.job_id}/status`, { cache: "no-store" });
    let json = await upstream.json();

    // 从本次请求上下文尝试获取 templateKey（如果后端状态里带有）
    const templateKey =
      json?.result?.templateKey || json?.result?.template_key || json?.templateKey || json?.template_key;

    // 决算口径纠偏 + 预算项屏蔽（仅在决算流程）
    // 无条件启用纠偏和过滤（用户要求屏蔽所有预算相关内容）
    json = normalizeDecisionWording(json);
    json = filterOutBudget(json);
    json = keepOnlyCompareRule(json);

    try {
      if (!hasCompareIssues(json)) {
        const jobId = params.job_id;
        const fallback = fallbackCompareExtract(jobId);
        if (fallback.length > 0) {
          (json as any).issues = Array.isArray((json as any).issues) ? (json as any).issues.concat(fallback) : fallback.slice();
          (json as any).rule_findings = Array.isArray((json as any).rule_findings) ? (json as any).rule_findings.concat(fallback) : fallback.slice();
          (json as any).merged = Array.isArray((json as any).merged) ? (json as any).merged.concat(fallback) : fallback.slice();
          if ((json as any).result) {
            const r = (json as any).result;
            r.issues = Array.isArray(r.issues) ? r.issues.concat(fallback) : fallback.slice();
            r.rule_findings = Array.isArray(r.rule_findings) ? r.rule_findings.concat(fallback) : fallback.slice();
            r.merged = Array.isArray(r.merged) ? r.merged.concat(fallback) : fallback.slice();
          }
        }
      }
    } catch {}

    return NextResponse.json(json, { status: upstream.status });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}
