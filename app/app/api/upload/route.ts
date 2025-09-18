export const runtime = 'nodejs';

export async function POST(req: Request) {
  try {
    // 读取浏览器上送的 multipart
    const inForm = await req.formData();
    // 重新组装一个 FormData（避免直接透传 req.body 导致的 500）
    const outForm = new FormData();
    for (const [k, v] of inForm.entries()) {
      if (v instanceof File) outForm.append(k, v, v.name);
      else outForm.append(k, v as string);
    }

    // 转发到后端
    const r = await fetch('http://localhost:8000/upload', {
      method: 'POST',
      body: outForm,           // 交给 fetch 自动设置 Content-Type 和 boundary
    });

    // 把后端的正文取出来，包装成明确的响应（便于前端显示）
    const text = await r.text();
    return new Response(text, {
      status: r.status,
      headers: { 'content-type': r.headers.get('content-type') || 'text/plain' },
    });
  } catch (e: any) {
    return Response.json({ detail: e?.message || String(e) }, { status: 502 });
  }
}
