'use client';
import { useEffect, useRef, useState } from 'react';

export default function UploadBox() {
  const inputRef = useRef<HTMLInputElement|null>(null);
  const [msg, setMsg] = useState('就绪');
  const [jobId, setJobId] = useState<string|undefined>(undefined);
  const [status, setStatus] = useState<'idle'|'queued'|'polling'|'done'>('idle');

  const onPick = async (f: File) => {
    try {
      const fd = new FormData();
      fd.append('file', f, f.name);
      setMsg('上传中…'); setJobId(undefined); setStatus('idle');
      const res = await fetch('/api/upload', { method: 'POST', body: fd });
      const text = await res.text();
      setMsg(`HTTP ${res.status} → ${text}`);
      try { const j = JSON.parse(text); if (j?.job_id) setJobId(j.job_id); } catch {}
    } catch (e:any) {
      setMsg(`失败：${e?.message || e}`);
    } finally {
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const onAnalyze = async () => {
    if (!jobId) return;
    setStatus('queued');
    const r = await fetch(`/api/analyze/${jobId}`, { method: 'POST' });
    const t = await r.text();
    setMsg(`解析返回：HTTP ${r.status} → ${t}`);
    setStatus('polling');
  };

  useEffect(() => {
    if (!jobId || status !== 'polling') return;
    let alive = true;
    const tick = async () => {
      const r = await fetch(`/api/jobs_adv/${jobId}/status`, { cache: 'no-store' });
      const t = await r.text();
      setMsg(prev => `${prev}\n状态：HTTP ${r.status} → ${t}`);
      try { const j = JSON.parse(t); if (j.status === 'done') { setStatus('done'); return; } } catch {}
      if (alive) setTimeout(tick, 1200);
    };
    const id = setTimeout(tick, 800);
    return () => { alive = false; clearTimeout(id); };
  }, [jobId, status]);

  return (
    <div className="space-y-3">
      <button type="button" className="px-3 py-2 rounded bg-black text-white"
              onClick={() => inputRef.current?.click()}>
        选择 PDF 并上传
      </button>
      <input ref={inputRef} type="file" accept="application/pdf" className="hidden"
             onChange={e => { const f = e.target.files?.[0]; if (f) onPick(f); }} />

      {jobId && (
        <div className="flex items-center gap-3">
          <button type="button" className="px-3 py-2 rounded bg-gray-800 text-white"
                  onClick={onAnalyze}>
            开始解析（job {jobId.slice(0,8)}…）
          </button>
          <button type="button" className="px-3 py-2 rounded border border-gray-300"
                  onClick={() => window.open(`/api/reports/${jobId}`, "_blank")}
                  title="打开该 Job 的离线模板对齐报告（Markdown）">
            查看对齐报告
          </button>
        </div>
      )}

      <pre className="bg-gray-100 p-2 rounded text-sm whitespace-pre-wrap">{msg}</pre>
    </div>
  );
}
