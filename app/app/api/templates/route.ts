import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

export const runtime = "nodejs";

// 简易解析：仅根据文本提取 templates 列表中的 key/name/path/profile
function naiveParseTemplates(raw: string) {
  const normalized = raw.split("\r").join("");
  const lines = normalized.split("\n");
  const items: Array<{ key?: string; name?: string; path?: string; profile?: string }> = [];
  let inTemplates = false;
  let current: Record<string, string> | null = null;

  for (const line of lines) {
    const l = line.trim();
    if (!inTemplates && l.startsWith("templates:")) {
      inTemplates = true;
      continue;
    }
    if (!inTemplates) continue;

    if (l.startsWith("-")) {
      if (current && (current.key || current.name)) items.push(current as any);
      current = {};
      continue;
    }
    if (!current) continue;

    // 匹配 key/name/path/profile: 值
    const m = l.match(/^(key|name|path|profile):\s*(.+)$/);
    if (m) {
      const k = m[1];
      let v = m[2];
      // 去掉可能的引号
      v = v.replace(/^["']|["']$/g, "");
      current[k] = v;
    }
  }

  if (current && (current.key || current.name)) items.push(current as any);
  return items.filter((x) => x.key && x.name) as Array<{ key: string; name: string; path?: string; profile?: string }>;
}

export async function GET() {
  const defaults = [
    { key: "dept_decision_template_v1", name: "附件2：部门决算模板", path: "samples/templates/部门决算模板.yaml", profile: "决算公开" },
    { key: "unit_decision_template_district_v1", name: "附件2-2：单位决算公开模板（区级）", path: "samples/templates/单位决算公开模板（区级）.yaml", profile: "决算公开" }
  ];

  try {
    const filePath = path.join(process.cwd(), "templates", "index.yaml");
    const raw = await readFile(filePath, "utf-8");

    // 优先用 YAML 解析
    try {
      const yamlMod = await import("yaml").then((m: any) => m.default || m);
      const parsed: any = yamlMod.parse(raw);
      if (parsed?.templates && Array.isArray(parsed.templates) && parsed.templates.length > 0) {
        return NextResponse.json({ ok: true, templates: parsed.templates, version: parsed.version ?? 1 });
      }
    } catch {
      // 忽略 YAML 解析错误，走兜底
    }

    // 兜底：文本解析
    const naive = naiveParseTemplates(raw);
    if (naive.length > 0) {
      return NextResponse.json({ ok: true, templates: naive, version: 1, parsed: "naive" });
    }

    // 最终回退：内置默认模板
    return NextResponse.json({ ok: true, templates: defaults, version: 1, fallback: "defaults" });
  } catch {
    // 文件缺失或读取失败时也回退至默认
    return NextResponse.json({ ok: true, templates: defaults, version: 1, fallback: "defaults" });
  }
}