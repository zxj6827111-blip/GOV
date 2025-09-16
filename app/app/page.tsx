export default function HomePage() {
  return (
    <section className="space-y-6">
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center">
        <h2 className="text-xl font-semibold">上传预算/决算 PDF</h2>
        <p className="mt-2 text-sm text-slate-500">
          下一步：接入文件上传、解析与规则执行引擎。
        </p>
      </div>
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h3 className="text-lg font-semibold">快速检查流程</h3>
        <ol className="mt-4 list-decimal space-y-2 pl-6 text-sm text-slate-600">
          <li>上传 PDF 或提供公开链接。</li>
          <li>解析封面、目录并定位“九张表”。</li>
          <li>执行规则集 v3.3 并生成问题清单。</li>
        </ol>
      </div>
    </section>
  );
}
