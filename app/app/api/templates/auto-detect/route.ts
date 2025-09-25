import { NextRequest, NextResponse } from "next/server";
import { readFile, stat } from "fs/promises";
import path from "path";

export const runtime = "nodejs";

type TemplateItem = { key: string; name: string; path?: string; profile?: string; aliases?: string[] };

// 读取上传目录文本（优先 extracted_text.txt，回退到 status.json 里 summary/evidence）
async function readJobText(jobId: string): Promise<string> {
  const base = path.join(process.cwd(), "..", ".."); // app/ 下到项目根
  const uploads = path.join(base, "uploads", jobId);
  const tryFiles = [
    path.join(uploads, "extracted_text.txt"),
    path.join(uploads, "status.json"),
  ];
  for (const p of tryFiles) {
    try {
      await stat(p);
      const raw = await readFile(p, "utf-8");
      if (p.endsWith(".txt")) return raw;
      try {
        const js = JSON.parse(raw);
        const parts: string[] = [];
        if (js?.result?.summary) parts.push(js.result.summary);
        if (Array.isArray(js?.result?.ai_findings)) {
          for (const it of js.result.ai_findings) {
            if (it?.message) parts.push(it.message);
            if (Array.isArray(it?.evidence)) {
              for (const ev of it.evidence) if (ev?.text) parts.push(ev.text);
            }
          }
        }
        return parts.join("\n");
      } catch {
        return raw;
      }
    } catch {
      // ignore
    }
  }
  return "";
}

// 从模板 YAML 中提取 required_tables 和 aliases 作为锚点
async function readTemplateAnchors(tplPath: string): Promise<string[]> {
  try {
    const full = path.isAbsolute(tplPath)
      ? tplPath
      : path.join(process.cwd(), "..", "..", tplPath);
    const raw = await readFile(full, "utf-8");
    const lines = raw.split("\r").join("").split("\n");
    const anchors: string[] = [];
    let inReq = false;
    for (const line of lines) {
      const l = line.trim();
      if (l.startsWith("required_tables:")) {
        inReq = true;
        continue;
      }
      if (inReq) {
        if (/^[a-zA-Z_]/.test(l)) break; // 下一个大段落开始
        const mName = l.match(/^-\s*name:\s*(.+)$/);
        if (mName) {
          anchors.push(mName[1].replace(/^["']|["']$/g, ""));
          continue;
        }
        const mAlias = l.match(/^aliases:\s*\[(.+)\]$/);
        if (mAlias) {
          const arr = mAlias[1]
            .split(",")
            .map((s) => s.trim().replace(/^["']|["']$/g, ""));
          anchors.push(...arr);
          continue;
        }
      }
    }
    return anchors.filter(Boolean);
  } catch {
    return [];
  }
}

// 载入模板索引
async function loadTemplates(): Promise<TemplateItem[]> {
  const idxPath = path.join(process.cwd(), "templates", "index.yaml");
  const raw = await readFile(idxPath, "utf-8");
  // YAML优先
  try {
    const yaml = await import("yaml").then((m) => m.default || m);
    const parsed: any = yaml.parse(raw);
    if (parsed?.templates && Array.isArray(parsed.templates)) {
      return parsed.templates as TemplateItem[];
    }
  } catch {
    // ignore
  }
  // 文本兜底解析
  const lines = raw.split("\r").join("").split("\n");
  const items: TemplateItem[] = [];
  let inTemplates = false;
  let current: any = null;
  for (const line of lines) {
    const l = line.trim();
    if (l.startsWith("templates:")) {
      inTemplates = true;
      continue;
    }
    if (!inTemplates) continue;
    if (l.startsWith("-")) {
      if (current?.key && current?.name) items.push(current as TemplateItem);
      current = {};
      continue;
    }
    if (!current) continue;
    const m = l.match(/^(key|name|path|profile):\s*(.+)$/);
    if (m) {
      const k = m[1];
      let v = m[2];
      v = v.replace(/^["']|["']$/g, "");
      (current as any)[k] = v;
    }
  }
  if (current?.key && current?.name) items.push(current as TemplateItem);
  return items;
}

export async function POST(req: NextRequest) {
  try {
    const { job_id } = await req.json();
    if (!job_id)
      return NextResponse.json(
        { ok: false, error: "missing job_id" },
        { status: 400 }
      );

    const [templates, textRaw] = await Promise.all([
      loadTemplates(),
      readJobText(job_id),
    ]);
    const text = (textRaw || "").replace(/\s+/g, "");
    if (templates.length === 0 || !text) {
      return NextResponse.json({
        ok: true,
        templateKey: "dept_decision_template_v1",
        templateName: "附件2：部门决算模板",
        confidence: 0.1,
        reason: "fallback",
      });
    }

    // 封面强特征（取前若干字符作为“封面/开头”区域）
    const coverZone = (textRaw || "").slice(0, 4000).replace(/\s+/g, "");
    const hasJuesuan = coverZone.includes("决算");
    const hasOpen = coverZone.includes("决算公开");
    const hasDeptWord = coverZone.includes("部门");
    const hasUnitWord = coverZone.includes("单位");
    const hintFujian22 = coverZone.includes("附件2-2") || coverZone.includes("附件2-2：");
    const hintFujian2 = coverZone.includes("附件2："); // 注意：弱证据

    const scores: any[] = [];
    for (const tpl of templates) {
      const anchors = await readTemplateAnchors(tpl.path || "");
      const reasons: Array<{ type: string; weight: number; detail: string }> = [];
      const hits: string[] = [];
      let score = 0;

      // 表名/别名命中（次要证据）
      let anchorHits = 0;
      for (const a of anchors) {
        const token = a.replace(/\s+/g, "");
        if (!token) continue;
        if (text.includes(token)) {
          score += 2;
          anchorHits += 1;
          if (hits.length < 10) hits.push(`锚点:${a}`);
        }
      }
      if (anchorHits > 0) reasons.push({ type: "anchors", weight: anchorHits * 2, detail: `锚点命中 ${anchorHits} 次` });

      // 模板名/别名命中（轻权重）
      let nameAliasHit = 0;
      if (tpl.name && text.includes(tpl.name.replace(/\s+/g, ""))) {
        score += 1;
        nameAliasHit += 1;
        hits.length < 10 && hits.push(`模板名:${tpl.name}`);
      }
      if (Array.isArray((tpl as any).aliases)) {
        for (const al of (tpl as any).aliases as string[]) {
          if (text.includes(al.replace(/\s+/g, ""))) {
            score += 1;
            nameAliasHit += 1;
            if (hits.length < 10) hits.push(`别名:${al}`);
          }
        }
      }
      if (nameAliasHit > 0) reasons.push({ type: "name_alias", weight: nameAliasHit, detail: `名称/别名命中 ${nameAliasHit} 次` });

      // 封面强特征（主要证据）
      let coverBoost = 0;
      const nameStr = (tpl.name || "");
      const deptInTpl = /部门/.test(nameStr);
      const unitInTpl = /单位/.test(nameStr);

      if (deptInTpl && hasDeptWord && (hasJuesuan || hasOpen)) {
        coverBoost += 8;
        hits.length < 10 && hits.push("封面:部门+决算");
      }
      if (unitInTpl && hasUnitWord && (hasJuesuan || hasOpen)) {
        coverBoost += 8;
        hits.length < 10 && hits.push("封面:单位+决算");
      }
      if (/附件2-2/.test(nameStr) && hintFujian22) {
        coverBoost += 3;
        hits.length < 10 && hits.push("封面:附件2-2");
      }
      if (/附件2(?!-2)/.test(nameStr) && hintFujian2 && !hintFujian22) {
        coverBoost += 3;
        hits.length < 10 && hits.push("封面:附件2");
      }
      if (coverBoost > 0) reasons.push({ type: "cover", weight: coverBoost, detail: `封面强信号 +${coverBoost}` });

      // 惩罚项：封面信号冲突（同时出现部门与单位）
      if (hasDeptWord && hasUnitWord && (hasJuesuan || hasOpen)) {
        score -= 3;
        reasons.push({ type: "penalty_conflict_cover", weight: -3, detail: "封面同时出现‘部门’与‘单位’，冲突惩罚 -3" });
      }

      // 覆盖轻微鼓励：如果仅有“决算公开”而无部门/单位词
      if (!hasDeptWord && !hasUnitWord && (hasJuesuan || hasOpen)) {
        score += 1;
        reasons.push({ type: "weak_cover", weight: +1, detail: "封面仅出现‘决算(公开)’弱信号 +1" });
      }

      // 锚点过少时的弱化（如果没有封面强信号且锚点命中不足2）
      if (coverBoost === 0 && anchorHits > 0 && anchorHits < 2) {
        score -= 1;
        reasons.push({ type: "penalty_low_anchor", weight: -1, detail: "锚点命中过少，可信度弱化 -1" });
      }

      scores.push({ key: tpl.key, name: tpl.name, score, reasons, hits, anchorHits, coverBoost, nameAliasHit });
    }
    scores.sort((a, b) => b.score - a.score);
    const best = scores[0];
    const second = scores[1];

    const margin = best && second ? best.score - second.score : (best ? best.score : 0);
    // 置信度：基于分差和总得分的简化函数
    let confidence = best ? Math.max(0, Math.min(0.99, 0.5 + 0.1 * (margin || 0) + 0.02 * (best.score || 0))) : 0.3;

    // 阈值与冲突策略
    const threshold = 0.6;
    const conflictMargin = 3; // 分差过小则认为存在冲突
    const needManual = !best || confidence < threshold || (second && margin < conflictMargin);
    const conflict = Boolean(second && margin < conflictMargin);

    return NextResponse.json({
      ok: true,
      templateKey: best?.key || null,
      templateName: best?.name || null,
      confidence,
      threshold,
      needManual,
      conflict,
      margin,
      detectedSignals: {
        hasJuesuan, hasOpen, hasDeptWord, hasUnitWord, hintFujian22, hintFujian2
      },
      bestDetail: best ? { key: best.key, name: best.name, score: best.score, reasons: best.reasons, hits: best.hits } : null,
      runner: { textLength: (textRaw || "").length },
      scores: scores.slice(0, 5),
    });
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message || String(e) },
      { status: 500 }
    );
  }
}

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const job_id =
      url.searchParams.get("job_id") ||
      url.searchParams.get("id") ||
      url.searchParams.get("jobId");

    if (!job_id) {
      return NextResponse.json(
        {
          ok: false,
          error: "missing job_id",
          usage: "POST with {job_id} or GET ?job_id=xxx",
        },
        { status: 400 }
      );
    }

    // 复用 POST 逻辑
    const res = await fetch(`${url.origin}/api/templates/auto-detect`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ job_id }),
      cache: "no-store",
    });
    const js = await res.json();
    return NextResponse.json(js, { status: res.status });
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message || String(e) },
      { status: 500 }
    );
  }
}