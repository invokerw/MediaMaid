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

export interface JsonSchemaProp {
  type?: string;
  title?: string;
  default?: unknown;
  description?: string;
}
export interface JsonSchema {
  properties?: Record<string, JsonSchemaProp>;
  required?: string[];
}
export interface PluginEntry {
  name: string;
  enabled: boolean;
  configured: boolean;
  config: Record<string, unknown>;
  schema: JsonSchema;
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

async function send<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return r.json();
}

const post = <T>(url: string, body?: unknown) => send<T>("POST", url, body);
const put = <T>(url: string, body?: unknown) => send<T>("PUT", url, body);

export const api = {
  dashboard: () => get<Dashboard>("/api/dashboard"),
  records: (status?: string) =>
    get<{ records: RecordRow[] }>(
      "/api/records" + (status ? `?status=${encodeURIComponent(status)}` : "")
    ),
  plugins: () => get<{ categories: PluginCategory[] }>("/api/plugins"),
  updatePlugin: (
    category: string,
    name: string,
    body: { enabled: boolean; config: Record<string, unknown> }
  ) => put<PluginEntry>(`/api/plugins/${category}/${name}`, body),
  config: () => get<{ path: string; text: string }>("/api/config"),
  scan: (dry_run: boolean) => post<ScanResult>("/api/scan", { dry_run }),
  subscribe: () => post<{ submitted: number }>("/api/subscribe"),
};
