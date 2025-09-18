export const runtime = 'nodejs';
export async function GET() {
  const r = await fetch('http://localhost:8000/health', { cache: 'no-store' });
  return Response.json(await r.json(), { status: r.status });
}
