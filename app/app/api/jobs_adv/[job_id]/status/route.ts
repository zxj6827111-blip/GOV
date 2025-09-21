import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

export const runtime = "nodejs";

export async function GET(
  _req: NextRequest,
  { params }: { params: { job_id: string } }
) {
  try {
  const upstream = await fetch(`${apiBase}/jobs_adv2/${params.job_id}/status`, { cache: "no-store" });
    const json = await upstream.json();
    return NextResponse.json(json, { status: upstream.status });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}
