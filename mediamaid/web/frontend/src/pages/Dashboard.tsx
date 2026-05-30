import { useEffect, useState } from "react";
import { api, Dashboard as DashboardData, ScanResult } from "../api";
import RecordsTable from "../components/RecordsTable";

const CARDS: [string, string][] = [
  ["已整理", "done"],
  ["跳过", "skipped"],
  ["失败", "failed"],
];

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.dashboard().then(setData).catch((e) => setError(String(e)));
  useEffect(() => {
    load();
  }, []);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      setResult(r);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>仪表盘</h1>

      <section className="cards">
        {CARDS.map(([label, key]) => (
          <div className="card" key={key}>
            <div className="num">{data?.counts[key] ?? 0}</div>
            <div className="lbl">{label}</div>
          </div>
        ))}
      </section>

      <section className="actions">
        <button onClick={() => run(() => api.scan(true))} disabled={busy}>
          扫描预览 (dry-run)
        </button>
        <button
          className="primary"
          onClick={() => run(() => api.scan(false))}
          disabled={busy}
        >
          执行扫描整理
        </button>
        <button onClick={() => run(() => api.subscribe())} disabled={busy}>
          运行订阅一轮
        </button>
        {busy && <span>⏳ 处理中…</span>}
      </section>

      {error && <pre className="result error">{error}</pre>}
      {result != null && (
        <pre className="result">{formatResult(result)}</pre>
      )}

      <h2>最近记录</h2>
      <RecordsTable records={data?.records ?? []} />
    </>
  );
}

function formatResult(r: unknown): string {
  const s = r as ScanResult;
  if (s && s.summary) {
    const head = s.dry_run ? "[预览] " : "";
    const summary = Object.entries(s.summary)
      .map(([k, v]) => `${k}: ${v}`)
      .join("  ");
    const lines = (s.items || []).map(
      (i) => `  ${i.status.padEnd(8)} ${i.source}${i.dest ? "  →  " + i.dest : ""}`
    );
    return [head + summary, ...lines].join("\n");
  }
  return JSON.stringify(r, null, 2);
}
