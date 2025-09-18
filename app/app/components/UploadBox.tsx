'use client';
import { useRef, useState } from 'react';

export default function UploadBox() {
  const inputRef = useRef<HTMLInputElement|null>(null);
  const [msg, setMsg] = useState('就绪');

  const onPick = async (f: File) => {
    try {
      const fd = new FormData();
      fd.append('file', f, f.name);       // 不要手动设 Content-Type
      setMsg('上传中…');
      const res = await fetch('/api/upload', { method: 'POST', body: fd });
      const text = await res.text();
      setMsg(`HTTP ${res.status} → ${text}`);
    } catch (e:any) {
      setMsg(`失败：${e?.message || e}`);
    } finally {
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-3">
      <button type="button" className="px-3 py-2 rounded bg-black text-white"
              onClick={() => inputRef.current?.click()}>
        选择 PDF 并上传
      </button>
      <input ref={inputRef} type="file" accept="application/pdf" className="hidden"
             onChange={e => { const f = e.target.files?.[0]; if (f) onPick(f); }} />
      <pre className="bg-gray-100 p-2 rounded text-sm whitespace-pre-wrap">{msg}</pre>
    </div>
  );
}
