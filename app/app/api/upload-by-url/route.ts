import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/apiBase";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  try {
    const { url } = await req.json();
    if (!url || typeof url !== "string") {
      return NextResponse.json({ error: "missing url" }, { status: 400 });
    }

    const r = await fetch(url);
    if (!r.ok) {
      return NextResponse.json({ error: `download failed: ${r.status}` }, { status: 400 });
    }
    const blob = await r.blob();
    const name = (new URL(url).pathname.split("/").pop() || "link.pdf");
    const file = new File([blob], name, { type: r.headers.get("content-type") || "application/pdf" });

    const fd = new FormData();
    fd.set("file", file);

    const upstream = await fetch(`${apiBase}/upload`, { method: "POST", body: fd as any });
    const json = await upstream.json();
    return NextResponse.json(json, { status: upstream.status });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}
