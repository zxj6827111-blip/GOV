import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

export const runtime = "nodejs";

export async function POST(
  _req: NextRequest,
  { params }: { params: { job_id: string } }
) {
  try {
    const upstream = await fetch(`${apiBase}/analyze2/${params.job_id}`, {
      method: "POST",
    });
    const json = await upstream.json();
    return NextResponse.json(json, { status: upstream.status });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}
