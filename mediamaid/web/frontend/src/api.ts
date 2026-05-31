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

export interface Settings {
  source_dirs: string[];
  library_dir: string;
  action: string;
  on_conflict: string;
  stable_seconds: number;
  rescan_interval: number;
  subscribe_interval: number;
  poll_completed: boolean;
  poll_interval: number;
  write_nfo: boolean;
  download_artwork: boolean;
  anime_keywords: string[];
  filters: {
    video_extensions: string[];
    min_size_mb: number;
    exclude_keywords: string[];
  };
  naming: {
    movie: string;
    episode: string;
    movie_no_year: string;
    episode_no_year: string;
    anime: string;
    anime_no_year: string;
  };
}

export interface ReleaseRow {
  title: string;
  guid: string;
  magnet: string | null;
  torrent_url: string | null;
  link: string | null;
  size: number | null;
  pub_date: string | null;
  source: string | null;
  seen: boolean;
}

export interface SeenRelease {
  guid: string;
  title: string;
  ts: number;
}

export interface SubscriberType {
  name: string;
  schema: JsonSchema;
}

export interface ParserRow {
  id: string;
  name: string;
  parser: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface ParseTestResult {
  matched: string | null;
  type?: string;
  title?: string;
  year?: number | null;
  season?: number | null;
  episode?: number | null;
}

export interface SubscriptionRow {
  id: string;
  name: string;
  subscriber: string;
  enabled: boolean;
  config: Record<string, unknown>;
  processed: number;
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
  testPlugin: (category: string, name: string, config: Record<string, unknown>) =>
    post<{ ok: boolean; message: string }>(`/api/plugins/${category}/${name}/test`, {
      config,
    }),
  settings: () => get<Settings>("/api/settings"),
  updateSettings: (body: Partial<Settings>) => put<Settings>("/api/settings", body),
  filesRoots: () => get<{ roots: { label: string; path: string }[] }>("/api/files/roots"),
  filesList: (path: string) =>
    get<{
      path: string;
      parent: string;
      entries: { name: string; path: string; is_dir: boolean; size: number; mtime: number }[];
    }>(`/api/files?path=${encodeURIComponent(path)}`),
  filesDelete: (path: string) => post<{ ok: boolean }>("/api/files/delete", { path }),
  filesRename: (path: string, name: string) =>
    post<{ ok: boolean; path: string }>("/api/files/rename", { path, name }),
  diagHardlink: () =>
    get<{
      action: string;
      results: { source: string; library: string; ok: boolean; detail: string }[];
    }>("/api/diag/hardlink"),
  fsList: (path?: string) =>
    get<{ path: string; parent: string; dirs: { name: string; path: string }[]; error: string | null }>(
      "/api/fs" + (path ? `?path=${encodeURIComponent(path)}` : "")
    ),
  parserTypes: () => get<{ parsers: SubscriberType[] }>("/api/parsers/types"),
  parsers: () => get<{ parsers: ParserRow[] }>("/api/parsers"),
  createParser: (body: {
    name: string;
    parser: string;
    enabled: boolean;
    config: Record<string, unknown>;
  }) => post<ParserRow>("/api/parsers", body),
  updateParser: (id: string, body: Partial<ParserRow>) =>
    put<ParserRow>(`/api/parsers/${id}`, body),
  deleteParser: (id: string) => send<{ ok: boolean }>("DELETE", `/api/parsers/${id}`),
  parseTest: (name: string) => post<ParseTestResult>("/api/parse/test", { name }),
  subscriberTypes: () => get<{ subscribers: SubscriberType[] }>("/api/subscribers"),
  subscriptions: () => get<{ subscriptions: SubscriptionRow[] }>("/api/subscriptions"),
  createSubscription: (body: {
    name: string;
    subscriber: string;
    enabled: boolean;
    config: Record<string, unknown>;
  }) => post<SubscriptionRow>("/api/subscriptions", body),
  updateSubscription: (id: string, body: Partial<SubscriptionRow>) =>
    put<SubscriptionRow>(`/api/subscriptions/${id}`, body),
  deleteSubscription: (id: string) =>
    send<{ ok: boolean }>("DELETE", `/api/subscriptions/${id}`),
  subPreview: (id: string) =>
    get<{ releases: ReleaseRow[] }>(`/api/subscriptions/${id}/preview`),
  subReleases: (id: string) =>
    get<{ releases: SeenRelease[] }>(`/api/subscriptions/${id}/releases`),
  downloadRelease: (rel: {
    title: string;
    guid: string;
    magnet: string | null;
    torrent_url: string | null;
    link: string | null;
    sub_id?: string;
  }) => post<{ ok: boolean }>("/api/releases/download", rel),
  config: () => get<{ path: string; text: string }>("/api/config"),
  scan: (dry_run: boolean) => post<ScanResult>("/api/scan", { dry_run }),
  subscribe: () => post<{ submitted: number }>("/api/subscribe"),
};
