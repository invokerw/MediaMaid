import { useEffect, useState } from "react";
import {
  Table,
  Button,
  Space,
  Select,
  Modal,
  Input,
  InputNumber,
  Radio,
  Form,
  Popconfirm,
  Tag,
  Tooltip,
  Descriptions,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  FolderFilled,
  FileOutlined,
  ArrowUpOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  SearchOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { api, FileEntry, IdentifyResult, TmdbPreview } from "../api";
import { ELLIPSIS, ellipsisCell } from "../components/EllipsisCell";

const { Text, Paragraph } = Typography;

function fmtSize(n: number, isDir: boolean): string {
  if (isDir) return "-";
  if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(2) + " GB";
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}

const TYPE_LABEL: Record<string, { text: string; color: string }> = {
  movie: { text: "电影", color: "purple" },
  episode: { text: "剧集", color: "geekblue" },
  unknown: { text: "未知", color: "default" },
};

function typeTag(mediaType?: string, category?: string) {
  if (!mediaType) return null;
  if (mediaType === "episode" && category === "anime")
    return <Tag color="magenta">动漫</Tag>;
  const t = TYPE_LABEL[mediaType] ?? TYPE_LABEL.unknown;
  return <Tag color={t.color}>{t.text}</Tag>;
}

function parsedText(e: FileEntry): string {
  const p = e.parsed;
  if (!p) return "";
  let s = p.title || "";
  if (p.year) s += ` (${p.year})`;
  if (p.media_type === "episode" && p.season != null && p.episode != null) {
    s += `  S${String(p.season).padStart(2, "0")}E${String(p.episode).padStart(2, "0")}`;
  }
  return s;
}

export default function Files() {
  const [roots, setRoots] = useState<{ label: string; path: string }[]>([]);
  const [root, setRoot] = useState<string>("");
  const [path, setPath] = useState<string>("");
  const [parent, setParent] = useState<string>("");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [rename, setRename] = useState<{ entry: FileEntry; name: string } | null>(null);
  const [identify, setIdentify] = useState<{
    entry: FileEntry;
    loading: boolean;
    result: IdentifyResult | null;
  } | null>(null);
  const [manual, setManual] = useState<FileEntry | null>(null);

  // 源目录与失败目录都展示识别信息/操作（失败目录用于人工修复）
  function isSourceRoot(p: string, rootsList = roots): boolean {
    return rootsList.some(
      (r) =>
        (r.label.startsWith("源目录") || r.label.startsWith("失败")) &&
        (p === r.path || p.startsWith(r.path + "/"))
    );
  }

  useEffect(() => {
    api.filesRoots().then((d) => {
      setRoots(d.roots);
      if (d.roots[0]) {
        setRoot(d.roots[0].path);
        browse(d.roots[0].path, d.roots);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function browse(p: string, rootsList = roots) {
    setLoading(true);
    api
      .filesList(p, isSourceRoot(p, rootsList) ? 1 : 0)
      .then((d) => {
        setPath(d.path);
        setParent(d.parent);
        setEntries(d.entries);
      })
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }

  // 不允许越过当前根的上级
  const canUp = path !== root && path.startsWith(root);
  const sourceView = isSourceRoot(path);

  async function doDelete(e: FileEntry) {
    try {
      await api.filesDelete(e.path);
      message.success(`已删除 ${e.name}`);
      browse(path);
    } catch (err) {
      message.error(String(err));
    }
  }

  async function doRename() {
    if (!rename) return;
    try {
      await api.filesRename(rename.entry.path, rename.name);
      message.success("已重命名");
      setRename(null);
      browse(path);
    } catch (err) {
      message.error(String(err));
    }
  }

  async function openIdentify(e: FileEntry) {
    setIdentify({ entry: e, loading: true, result: null });
    try {
      const result = await api.organizeIdentify(e.path);
      setIdentify({ entry: e, loading: false, result });
    } catch (err) {
      message.error(String(err));
      setIdentify(null);
    }
  }

  const columns: ColumnsType<FileEntry> = [
    {
      title: "名称",
      dataIndex: "name",
      ellipsis: ELLIPSIS,
      render: (name, e) =>
        ellipsisCell(
          name,
          e.is_dir ? (
            <a onClick={() => browse(e.path)}>
              <FolderFilled style={{ color: "#e0b341", marginRight: 6 }} />
              {name}
            </a>
          ) : (
            <span>
              <FileOutlined style={{ marginRight: 6 }} />
              {name}
            </span>
          )
        ),
    },
    { title: "大小", dataIndex: "size", width: 110, render: (n, e) => fmtSize(n, e.is_dir) },
    {
      title: "修改时间",
      dataIndex: "mtime",
      width: 170,
      render: (t: number) => new Date(t * 1000).toLocaleString(),
    },
  ];

  if (sourceView) {
    columns.push(
      {
        title: "状态",
        width: 100,
        render: (_, e) =>
          !e.is_video ? (
            <Text type="secondary">-</Text>
          ) : e.organized ? (
            <Tooltip title={e.dst_path || ""}>
              <Tag color="success">已转移</Tag>
            </Tooltip>
          ) : (
            <Tag>未转移</Tag>
          ),
      },
      {
        title: "识别",
        ellipsis: ELLIPSIS,
        render: (_, e) =>
          !e.is_video ? (
            <Text type="secondary">-</Text>
          ) : e.parsed ? (
            ellipsisCell(
              parsedText(e),
              <Space size={4}>
                {typeTag(e.parsed.media_type, e.parsed.category)}
                <Text>{parsedText(e)}</Text>
              </Space>
            )
          ) : (
            <Text type="warning">无法解析</Text>
          ),
      }
    );
  }

  columns.push({
    title: "操作",
    width: sourceView ? 230 : 150,
    render: (_, e) => (
      <Space size={0} wrap>
        {sourceView && e.is_video && (
          <>
            <Button
              type="link"
              size="small"
              icon={<SearchOutlined />}
              onClick={() => openIdentify(e)}
            >
              识别
            </Button>
            <Button
              type="link"
              size="small"
              icon={<SwapOutlined />}
              onClick={() => setManual(e)}
            >
              手动转移
            </Button>
          </>
        )}
        <Button
          type="link"
          size="small"
          icon={<EditOutlined />}
          onClick={() => setRename({ entry: e, name: e.name })}
        >
          重命名
        </Button>
        <Popconfirm
          title={`删除「${e.name}」？${e.is_dir ? "（含其中全部内容）" : ""}`}
          onConfirm={() => doDelete(e)}
        >
          <Button type="link" size="small" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      </Space>
    ),
  });

  return (
    <>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          style={{ minWidth: 280 }}
          value={root}
          options={roots.map((r) => ({ value: r.path, label: r.label }))}
          onChange={(v) => {
            setRoot(v);
            browse(v);
          }}
        />
        <Button icon={<ArrowUpOutlined />} disabled={!canUp} onClick={() => browse(parent)}>
          上级
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => browse(path)}>
          刷新
        </Button>
      </Space>
      <div style={{ marginBottom: 8 }}>
        <Text type="secondary" className="mono">
          {path}
        </Text>
      </div>

      <Table
        rowKey="path"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={entries}
        pagination={entries.length > 50 ? { pageSize: 50 } : false}
      />

      <Modal
        title="重命名"
        open={!!rename}
        onOk={doRename}
        onCancel={() => setRename(null)}
        destroyOnClose
      >
        <Input
          value={rename?.name}
          onChange={(e) => rename && setRename({ ...rename, name: e.target.value })}
          onPressEnter={doRename}
        />
      </Modal>

      <IdentifyModal state={identify} onClose={() => setIdentify(null)} />

      <ManualModal
        entry={manual}
        onClose={() => setManual(null)}
        onDone={() => {
          setManual(null);
          browse(path);
        }}
      />
    </>
  );
}

// ---- 识别结果（只读预览，不落地）----
function IdentifyModal({
  state,
  onClose,
}: {
  state: { entry: FileEntry; loading: boolean; result: IdentifyResult | null } | null;
  onClose: () => void;
}) {
  const r = state?.result;
  return (
    <Modal
      title={state ? `识别：${state.entry.name}` : ""}
      open={!!state}
      onCancel={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}
      width={560}
      destroyOnClose
    >
      {state?.loading && <Paragraph>识别中…</Paragraph>}
      {r && (
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="解析结果">
            {r.parsed
              ? `${r.parsed.title}${r.parsed.year ? ` (${r.parsed.year})` : ""}` +
                (r.parsed.media_type === "episode" && r.parsed.season != null
                  ? `  S${String(r.parsed.season).padStart(2, "0")}E${String(
                      r.parsed.episode ?? 0
                    ).padStart(2, "0")}`
                  : "")
              : "无法解析"}
          </Descriptions.Item>
          <Descriptions.Item label="TMDB 匹配">
            {!r.has_key ? (
              <Text type="warning">未配置 TMDB API Key，仅解析文件名</Text>
            ) : r.matched ? (
              <span>
                {r.matched.title}
                {r.matched.year ? ` (${r.matched.year})` : ""}
                {r.matched.episode_title ? ` — ${r.matched.episode_title}` : ""}
                <Tag style={{ marginLeft: 8 }}>
                  TMDB #{r.matched.tmdb_id} · 置信度 {(r.matched.confidence * 100).toFixed(0)}%
                </Tag>
              </span>
            ) : (
              <Text type="secondary">未匹配到条目</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="目标路径预览">
            <Text className="mono">{r.dest_preview || "-"}</Text>
          </Descriptions.Item>
        </Descriptions>
      )}
    </Modal>
  );
}

// ---- 手动转移 ----
function ManualModal({
  entry,
  onClose,
  onDone,
}: {
  entry: FileEntry | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form] = Form.useForm();
  const mediaType = Form.useWatch("media_type", form);
  const [preview, setPreview] = useState<TmdbPreview | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (entry) {
      const p = entry.parsed;
      form.setFieldsValue({
        media_type: p?.media_type === "movie" ? "movie" : "episode",
        category: p?.category === "anime" ? "anime" : "tv",
        tmdb_id: undefined,
        season: p?.season ?? undefined,
        episode: p?.episode ?? undefined,
      });
      setPreview(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry]);

  const isEpisode = mediaType === "episode";

  async function doPreview() {
    const v = form.getFieldsValue();
    if (!v.tmdb_id) {
      message.warning("请先填写 TMDB ID");
      return;
    }
    setBusy(true);
    try {
      const r = await api.tmdbPreview({
        tmdb_id: v.tmdb_id,
        media_type: v.media_type,
        season: isEpisode ? v.season : undefined,
        episode: isEpisode ? v.episode : undefined,
      });
      setPreview(r);
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doTransfer() {
    if (!entry) return;
    const v = await form.validateFields();
    setBusy(true);
    try {
      const r = await api.organizeManual({
        path: entry.path,
        tmdb_id: v.tmdb_id,
        media_type: v.media_type,
        season: isEpisode ? v.season : undefined,
        episode: isEpisode ? v.episode : undefined,
        category: isEpisode ? v.category : undefined,
      });
      if (r.status === "done") {
        message.success(`已转移到 ${r.dest}`);
        onDone();
      } else {
        message.error(`转移未完成（${r.status}）：${r.error || ""}`);
      }
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={entry ? `手动转移：${entry.name}` : ""}
      open={!!entry}
      onCancel={onClose}
      destroyOnClose
      width={520}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button key="preview" onClick={doPreview} loading={busy}>
          按 ID 预览
        </Button>,
        <Button key="ok" type="primary" onClick={doTransfer} loading={busy}>
          转移
        </Button>,
      ]}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="media_type" label="类型">
          <Radio.Group>
            <Radio.Button value="movie">电影</Radio.Button>
            <Radio.Button value="episode">剧集</Radio.Button>
          </Radio.Group>
        </Form.Item>
        {isEpisode && (
          <Form.Item name="category" label="分类">
            <Radio.Group>
              <Radio.Button value="tv">普通剧集</Radio.Button>
              <Radio.Button value="anime">动漫</Radio.Button>
            </Radio.Group>
          </Form.Item>
        )}
        <Form.Item
          name="tmdb_id"
          label="TMDB ID"
          rules={[{ required: true, message: "请填写 TMDB ID" }]}
        >
          <InputNumber style={{ width: "100%" }} min={1} placeholder="如 603" />
        </Form.Item>
        {isEpisode && (
          <Space>
            <Form.Item name="season" label="季">
              <InputNumber min={0} />
            </Form.Item>
            <Form.Item name="episode" label="集">
              <InputNumber min={0} />
            </Form.Item>
          </Space>
        )}
      </Form>
      {preview && (
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="匹配条目">
            {preview.title}
            {preview.year ? ` (${preview.year})` : ""}
            {preview.episode_title ? ` — ${preview.episode_title}` : ""}
          </Descriptions.Item>
          <Descriptions.Item label="目标路径">
            <Text className="mono">{preview.dest_preview}</Text>
          </Descriptions.Item>
        </Descriptions>
      )}
    </Modal>
  );
}
