// 后端 JSON API 封装

export interface RecordRow {
  id: number;
  status: string;
  action: string | null;
  src_path: string;
  src_name: string;
  dst_path: string | null;
  dst_name: string | null;
  ts: number;
}

export interface Dashboard {
  counts: Record<string, number>;
  records: RecordRow[];
}

export interface PluginEntry {
  name: string;
  enabled: boolean;
}
export interface PluginCategory {
  category: string;
  entries: PluginEntry[];
}

export interface ScanResult {
  dry_run: boolean;
  summary: Record<string, number>;
  items: { source: string; status: string; dest: string | null }[];
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  dashboard: () => get<Dashboard>("/api/dashboard"),
  records: (status?: string) =>
    get<{ records: RecordRow[] }>(
      "/api/records" + (status ? `?status=${encodeURIComponent(status)}` : "")
    ),
  plugins: () => get<{ categories: PluginCategory[] }>("/api/plugins"),
  config: () => get<{ path: string; text: string }>("/api/config"),
  scan: (dry_run: boolean) => post<ScanResult>("/api/scan", { dry_run }),
  subscribe: () => post<{ submitted: number }>("/api/subscribe"),
};
