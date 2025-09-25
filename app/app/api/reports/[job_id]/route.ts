import { NextRequest, NextResponse } from "next/server";
import { readFile, stat } from "fs/promises";
import path from "path";

export const runtime = "nodejs";

function toArray<T = any>(v: any): T[] {
  if (!v) return [];
  return Array.isArray(v) ? v : [v];
}

function pickIssues(json: any): any[] {
  const root = json || {};
  const res = root.result || root;

  // 优先使用标准 issues
  let issues: any[] = toArray(res.issues);

  // 如果没有 issues，则合并 ai_findings 和 rule_findings
  if (!issues.length) {
    const ai = toArray(res.ai_findings).map((x: any) => ({ ...x, source: "ai" }));
    const rule = toArray(res.rule_findings).map((x: any) => ({ ...x, source: "rule" }));
    issues = [...ai, ...rule];
  }
  return issues;
}

function getVal(obj: any, pathArr: string[], def: any = undefined) {
  try {
    let cur = obj;
    for (const k of pathArr) {
      if (cur == null) return def;
      cur = cur[k];
    }
    return cur == null ? def : cur;
  } catch {
    return def;
  }
}

function renderIssueLine(issue: any): string {
  const id = issue.id || "";
  const source = issue.source || (issue.rule_id ? "rule" : "ai");
  const severity = issue.severity || "info";
  const title = issue.title || "";
  const msg = issue.message || "";
  const page = getVal(issue, ["location", "page"]);
  const section = getVal(issue, ["location", "section"]);
  const table = getVal(issue, ["location", "table"]);
  const tags = (Array.isArray(issue.tags) ? issue.tags : []).join(", ");

  const locBits: string[] = [];
  if (page != null) locBits.push(`页码: ${page}`);
  if (section) locBits.push(`章节: ${section}`);
  if (table) locBits.push(`表格: ${table}`);
  const loc = locBits.length ? `（${locBits.join("，")}）` : "";

  return `- [${severity}] [${source}] ${title}${loc}\n  - 说明: ${msg || "无"}\n  - 标签: ${tags || "无"}\n  - ID: ${id || "无"}\n`;
}

function buildMarkdownFromStatus(job_id: string, json: any): string {
  const res = json?.result || json || {};
  const templateKey = res.templateKey || res.template_key || json?.templateKey || json?.template_key || "未知模板";
  const name = res.templateName || res.template_name || res.profile || "";
  const confidence = res.confidence != null ? String(res.confidence) : "";

  const issues = pickIssues(json);
  const total = issues.length;

  const severityCount: Record<string, number> = {};
  const sourceCount: Record<string, number> = {};
  for (const it of issues) {
    const sev = (it.severity || "info").toLowerCase();
    severityCount[sev] = (severityCount[sev] || 0) + 1;
    const src = (it.source || (it.rule_id ? "rule" : "ai")).toLowerCase();
    sourceCount[src] = (sourceCount[src] || 0) + 1;
  }

  const header = [
    `# 模板对齐报告`,
    ``,
    `- Job ID: ${job_id}`,
    `- 模板: ${templateKey}${name ? `（${name}）` : ""}`,
    confidence ? `- 识别置信度: ${confidence}` : ``,
    `- 问题总数: ${total}`,
    `- 按来源: AI=${sourceCount.ai || 0} / 规则=${sourceCount.rule || 0}`,
    `- 按严重度: ${Object.entries(severityCount).map(([k, v]) => `${k}=${v}`).join("，") || "无"}`,
    ``,
    `---`,
    ``,
    `## 问题清单`,
    ``,
  ]
    .filter(Boolean)
    .join("\n");

  const lines: string[] = [header];

  // 可按严重度分组输出
  const order = ["critical", "high", "medium", "low", "info"];
  for (const sev of order) {
    const subset = issues.filter((i) => (i.severity || "info").toLowerCase() === sev);
    if (!subset.length) continue;
    lines.push(`### 严重度：${sev}（${subset.length}）\n`);
    for (const it of subset) {
      lines.push(renderIssueLine(it));
    }
    lines.push("");
  }

  // 其余（未在 order 中）
  const rest = issues.filter((i) => !order.includes((i.severity || "info").toLowerCase()));
  if (rest.length) {
    lines.push(`### 其他（${rest.length}）\n`);
    for (const it of rest) {
      lines.push(renderIssueLine(it));
    }
    lines.push("");
  }

  return lines.join("\n");
}

export async function GET(
  req: NextRequest,
  { params }: { params: { job_id: string } }
) {
  try {
    const { job_id } = params || {};
    if (!job_id) {
      return NextResponse.json({ ok: false, error: "missing_job_id" }, { status: 400 });
    }

    // 1) 优先尝试读取离线报告文件
    const base = path.join(process.cwd(), "..", "..");
    const reportPath = path.join(base, "reports", `alignment_${job_id}.md`);
    try {
      await stat(reportPath);
      const md = await readFile(reportPath, "utf-8");
      return new Response(md, {
        status: 200,
        headers: { "Content-Type": "text/markdown; charset=utf-8" },
      });
    } catch {
      // 继续尝试即时生成
    }

    // 2) 即时生成：从当前应用的代理状态接口读取数据（已含纠偏与过滤）
    const origin = new URL(req.url).origin;

    let statusJson: any = null;
    let statusOk = false;

    // 先尝试 jobs_adv2
    try {
      const r2 = await fetch(`${origin}/api/jobs_adv2/${encodeURIComponent(job_id)}/status`, { cache: "no-store" });
      if (r2.ok) {
        statusJson = await r2.json();
        statusOk = true;
      }
    } catch {}

    // 再尝试 jobs_adv
    if (!statusOk) {
      try {
        const r1 = await fetch(`${origin}/api/jobs_adv/${encodeURIComponent(job_id)}/status`, { cache: "no-store" });
        if (r1.ok) {
          statusJson = await r1.json();
          statusOk = true;
        }
      } catch {}
    }

    if (!statusOk || !statusJson) {
      const fallback =
        "# 模板对齐报告

" +
        `- Job ID: ${job_id}

` +
        "> 暂无报告内容：未找到离线报告文件，且状态接口不可用或尚未产出结果。

" +
        "请稍后重试，或返回结果页等待分析完成后再查看。
";
      return new Response(fallback, {
        status: 200,
        headers: { "Content-Type": "text/markdown; charset=utf-8" },
      });
    }

    const md = buildMarkdownFromStatus(job_id, statusJson);
    return new Response(md || "# 暂无报告内容", {
      status: 200,
      headers: { "Content-Type": "text/markdown; charset=utf-8" },
    });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message || String(e) }, { status: 500 });
  }
}