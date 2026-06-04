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
  description?: string;
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

export interface SubscriptionFilter {
  resolutions: string[];
  include_keywords: string[];
  exclude_keywords: string[];
  include_regex: string | null;
  exclude_regex: string | null;
  min_size_mb: number | null;
  max_size_mb: number | null;
  prefer: string[];
}

export interface SubscriptionRow {
  id: string;
  name: string;
  subscriber: string;
  enabled: boolean;
  downloader?: string | null;
  config: Record<string, unknown>;
  filters?: SubscriptionFilter;
  skip_existing?: boolean;
  processed: number;
  grabbed_episodes?: number;
}

export interface ScanResult {
  dry_run: boolean;
  summary: Record<string, number>;
  items: { source: string; status: string; dest: string | null }[];
}

export interface DownloadTask {
  id: string;
  name: string;
  downloader: string;
  state: string; // downloading/paused/seeding/completed/queued/error/unknown
  progress: number; // 0~1
  size: number | null;
  downloaded: number | null;
  dl_speed: number | null;
  up_speed: number | null;
  eta: number | null; // 秒
  error: string | null;
}

export interface DownloaderInfo {
  name: string;
  supports_management: boolean;
}

export interface ParsedInfo {
  title: string;
  year: number | null;
  season: number | null;
  episode: number | null;
  media_type: string; // movie / episode / unknown
  category: string; // tv / anime
}

export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: number;
  // 仅源目录 meta=1 时附带
  is_video?: boolean;
  organized?: boolean;
  dst_path?: string | null;
  parsed?: ParsedInfo | null;
}

export interface MatchedInfo {
  title: string;
  year: number | null;
  tmdb_id: number | null;
  season: number | null;
  episode: number | null;
  episode_title: string | null;
  confidence: number;
  poster_url: string | null;
}

export interface IdentifyResult {
  parsed: ParsedInfo | null;
  matched: MatchedInfo | null;
  has_key: boolean;
  dest_preview: string | null;
}

export interface TmdbPreview {
  title: string;
  year: number | null;
  episode_title: string | null;
  dest_preview: string;
}

export interface ManualOrganizeBody {
  path: string;
  tmdb_id: number;
  media_type: string; // movie / episode
  season?: number | null;
  episode?: number | null;
  category?: string | null; // tv / anime
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
  filesList: (path: string, meta = 0) =>
    get<{ path: string; parent: string; entries: FileEntry[] }>(
      `/api/files?path=${encodeURIComponent(path)}${meta ? "&meta=1" : ""}`
    ),
  filesDelete: (path: string) => post<{ ok: boolean }>("/api/files/delete", { path }),
  filesRename: (path: string, name: string) =>
    post<{ ok: boolean; path: string }>("/api/files/rename", { path, name }),
  organizeIdentify: (path: string) =>
    post<IdentifyResult>("/api/organize/identify", { path }),
  organizeManual: (body: ManualOrganizeBody) =>
    post<{ status: string; dest: string | null; error: string | null }>(
      "/api/organize/manual",
      body
    ),
  tmdbPreview: (p: {
    tmdb_id: number;
    media_type: string;
    season?: number | null;
    episode?: number | null;
  }) => {
    const q = new URLSearchParams({ tmdb_id: String(p.tmdb_id), media_type: p.media_type });
    if (p.season != null) q.set("season", String(p.season));
    if (p.episode != null) q.set("episode", String(p.episode));
    return get<TmdbPreview>(`/api/organize/tmdb-preview?${q.toString()}`);
  },
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
  parseTestDir: (path: string) =>
    post<{ results: (ParseTestResult & { name: string; path: string })[] }>(
      "/api/parse/test-dir",
      { path }
    ),
  subscriberTypes: () => get<{ subscribers: SubscriberType[] }>("/api/subscribers"),
  subscriptions: () => get<{ subscriptions: SubscriptionRow[] }>("/api/subscriptions"),
  createSubscription: (body: {
    name: string;
    subscriber: string;
    enabled: boolean;
    downloader?: string | null;
    config: Record<string, unknown>;
    filters?: Partial<SubscriptionFilter>;
    skip_existing?: boolean;
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
  batchDownloadReleases: (releases: ReleaseRow[], sub_id?: string) =>
    post<{ submitted: number; failed: number; failed_guids: string[] }>(
      "/api/releases/batch-download",
      { releases: releases.map((r) => ({ ...r, sub_id })) }
    ),
  markReleasesProcessed: (releases: ReleaseRow[], sub_id?: string) =>
    post<{ marked: number }>("/api/releases/mark-processed", {
      releases: releases.map((r) => ({ ...r, sub_id })),
    }),
  config: () => get<{ path: string; text: string }>("/api/config"),
  scan: (dry_run: boolean) => post<ScanResult>("/api/scan", { dry_run }),
  subscribe: () => post<{ submitted: number }>("/api/subscribe"),
  downloaders: () =>
    get<{ downloaders: { name: string; description: string }[] }>("/api/downloaders"),
  downloads: () =>
    get<{ downloaders: DownloaderInfo[]; tasks: DownloadTask[] }>("/api/downloads"),
  createDownload: (body: { downloader: string; uri: string; save_path?: string }) =>
    post<{ ok: boolean }>("/api/downloads", body),
  cancelDownload: (name: string, id: string, deleteFiles: boolean) =>
    send<{ ok: boolean }>(
      "DELETE",
      `/api/downloads/${encodeURIComponent(name)}/${encodeURIComponent(id)}?delete_files=${deleteFiles}`
    ),
  pauseDownload: (name: string, id: string) =>
    post<{ ok: boolean }>(
      `/api/downloads/${encodeURIComponent(name)}/${encodeURIComponent(id)}/pause`
    ),
  resumeDownload: (name: string, id: string) =>
    post<{ ok: boolean }>(
      `/api/downloads/${encodeURIComponent(name)}/${encodeURIComponent(id)}/resume`
    ),
};
