import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

export const runtime = "nodejs";

export async function POST(
  req: NextRequest,
  { params }: { params: { job_id: string } }
) {
  try {
    // 透传请求体到后端，支持选择模式/开关
    let body: any = undefined;
    try {
      body = await req.json();
    } catch {}

    const upstream = await fetch(`${apiBase}/analyze2/${params.job_id}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const json = await upstream.json();
    return NextResponse.json(json, { status: upstream.status });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}
