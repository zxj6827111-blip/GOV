// app/app/api/jobs/[job_id]/status/route.ts
import { NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

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

export async function GET(
  _req: Request,
  { params }: { params: { job_id: string } }
) {
  const job = encodeURIComponent(params.job_id);

  // 优先尝试后端 /jobs_adv2/{job}/status，回退到 /jobs/{job}/status
  const candidates = [
    `${apiBase}/jobs_adv2/${job}/status`,
    `${apiBase}/jobs/${job}/status`,
  ];

  for (let i = 0; i < candidates.length; i++) {
    try {
      const res = await fetch(candidates[i], { cache: "no-store" });
      const { data, status } = await toSafeJson(res);
      return NextResponse.json(data, { status: res.ok ? 200 : status });
    } catch (e: any) {
      if (i === candidates.length - 1) {
        return NextResponse.json(
          { error: "proxy_fetch_failed", message: String(e) },
          { status: 502 }
        );
      }
    }
  }

  return NextResponse.json({ error: "unreachable" }, { status: 500 });
}
