"use client";

type Issue = {
  rule: string;
  severity: "critical" | "error" | "warn" | "info" | string;
  message: string;
  location?: { page?: number; [k: string]: any };
};

export default function ResultCard({
  title,
  issues,
  tone = "info",
}: {
  title: string;
  issues: Issue[];
  tone?: "danger" | "warning" | "info" | "ok";
}) {
  const color =
    tone === "danger"
      ? "border-red-300 bg-red-50"
      : tone === "warning"
      ? "border-amber-300 bg-amber-50"
      : tone === "ok"
      ? "border-emerald-300 bg-emerald-50"
      : "border-sky-300 bg-sky-50";

  return (
    <div className={`rounded-lg border ${color} p-4`}>
      <h4 className="mb-2 text-base font-semibold">{title}</h4>

      {issues.length === 0 ? (
        <p className="text-slate-600 text-sm">没有发现问题。</p>
      ) : (
        <ul className="space-y-2">
          {issues.map((it, i) => (
            <li key={i} className="text-sm leading-6">
              <span className="font-medium">{it.rule}</span>：{it.message}
              {it.location?.page != null && (
                <span className="ml-2 text-slate-500">(第 {it.location.page} 页)</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
