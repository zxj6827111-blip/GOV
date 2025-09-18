export const runtime = 'nodejs';

export async function GET(_req: Request, { params }: { params: { job_id: string }}) {
  const r = await fetch(`http://localhost:8000/jobs/${params.job_id}/status`, { cache: 'no-store' });
  const text = await r.text();
  return new Response(text, {
    status: r.status,
    headers: { 'content-type': r.headers.get('content-type') || 'application/json' },
  });
}
