import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData(); // 期待字段名：file
    const upstream = await fetch(`${apiBase}/upload`, {
      method: "POST",
      body: formData as any,
    });
    const txt = await upstream.text();

    // 后端统一返回 JSON
    let data: any;
    try { data = JSON.parse(txt); } catch { data = { raw: txt }; }

    return NextResponse.json(data, { status: upstream.status });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}
