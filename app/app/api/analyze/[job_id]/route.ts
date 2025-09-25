import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

export const runtime = "nodejs";

async function toSafeJson(res: Response) {
  const ct = res.headers.get("content-type") || "";
  const text = await res.text();
  if (ct.includes("application/json")) {
    try {
      return { data: JSON.parse(text), status: res.status };
    } catch (e: any) {
      return {
        data: { error: "json_parse_failed", raw: text, message: String(e) },
        status: res.status,
      };
    }
  }
  return {
    data: { error: "non_json_from_backend", status: res.status, body: text },
    status: res.status,
  };
}

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

// 深度遍历，将所有字符串字段做决算口径映射
function deepNormalize(obj: any): any {
  if (obj == null) return obj;
  if (typeof obj === "string") return mapDecisionWordingOnce(obj);
  if (Array.isArray(obj)) return obj.map((v) => deepNormalize(v));
  if (typeof obj === "object") {
    const out: any = Array.isArray(obj) ? [] : {};
    for (const k of Object.keys(obj)) {
      out[k] = deepNormalize(obj[k]);
    }
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

  if (Array.isArray(data.issues)) data.issues = cleanseArray(data.issues);
  if (Array.isArray((data as any).ai_findings)) (data as any).ai_findings = cleanseArray((data as any).ai_findings);
  if (Array.isArray((data as any).rule_findings)) (data as any).rule_findings = cleanseArray((data as any).rule_findings);
  if (Array.isArray((data as any).merged)) (data as any).merged = cleanseArray((data as any).merged);
  return data;
}

export async function POST(
  req: NextRequest,
  { params }: { params: { job_id: string } }
) {
  try {
    // 透传请求体到后端，支持选择模式/开关/模板键
    let body: any = undefined;
    try {
      body = await req.json();
    } catch {}

    // 支持从 query 读取 templateKey（前端也可直接放到 body）
    const url = new URL(req.url);
    let templateKey = url.searchParams.get("templateKey") || url.searchParams.get("template_key") || (body?.templateKey || body?.template_key);

    // 若未指定模板键，则服务端自动识别一次作为兜底
    if (!templateKey) {
      try {
        const auto = await fetch(`${url.origin}/api/templates/auto-detect`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ job_id: params.job_id }),
          cache: "no-store",
        });
        if (auto.ok) {
          const js = await auto.json();
          if (js?.ok && js?.templateKey) {
            templateKey = js.templateKey;
          }
        }
      } catch {
        // 忽略自动识别失败，继续无模板键流程
      }
    }

    if (templateKey) {
      body = { ...(body || {}), templateKey, template_key: templateKey };
    }

    const upstream = await fetch(`${apiBase}/api/analyze/${encodeURIComponent(params.job_id)}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });

    let { data, status } = await toSafeJson(upstream);
    // 无条件启用决算口径文案映射（深度遍历替换）+ 屏蔽预算项
    data = normalizeDecisionWording(data);
    data = filterOutBudget(data);
    return NextResponse.json(data, { status: upstream.ok ? 200 : status });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}