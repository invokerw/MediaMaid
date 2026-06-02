import { useEffect, useRef, useState } from "react";
import {
  Table,
  Tag,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  Checkbox,
  Progress,
  Typography,
  Empty,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  PlusOutlined,
  ReloadOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { api, DownloadTask, DownloaderInfo } from "../api";
import { ELLIPSIS, ellipsisCell } from "../components/EllipsisCell";

const { Paragraph } = Typography;

// 归一化状态 -> 中文标签 + 颜色
const STATE_META: Record<string, { text: string; color: string }> = {
  downloading: { text: "下载中", color: "processing" },
  seeding: { text: "做种", color: "cyan" },
  completed: { text: "已完成", color: "success" },
  paused: { text: "已暂停", color: "default" },
  queued: { text: "排队中", color: "gold" },
  error: { text: "错误", color: "error" },
  unknown: { text: "未知", color: "default" },
};

function fmtBytes(n: number | null | undefined): string {
  if (!n) return "-";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
}

function fmtSpeed(n: number | null | undefined): string {
  if (!n) return "-";
  return `${fmtBytes(n)}/s`;
}

function fmtEta(secs: number | null | undefined): string {
  if (secs == null || secs < 0) return "-";
  if (secs < 60) return `${secs}秒`;
  if (secs < 3600) return `${Math.floor(secs / 60)}分`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}时${Math.floor((secs % 3600) / 60)}分`;
  return `${Math.floor(secs / 86400)}天`;
}

export default function Downloads() {
  const [tasks, setTasks] = useState<DownloadTask[]>([]);
  const [downloaders, setDownloaders] = useState<DownloaderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<DownloadTask | null>(null);
  const [deleteFiles, setDeleteFiles] = useState(false);
  const [form] = Form.useForm();
  const first = useRef(true);

  const load = () => {
    if (first.current) setLoading(true);
    api
      .downloads()
      .then((d) => {
        setTasks(d.tasks);
        setDownloaders(d.downloaders);
      })
      .catch((e) => {
        // 轮询出错只在首次提示，避免反复弹
        if (first.current) message.error(String(e));
      })
      .finally(() => {
        first.current = false;
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 支持管理（可新建/控制）的下载器
  const manageable = downloaders.filter((d) => d.supports_management);

  function openAdd() {
    form.resetFields();
    form.setFieldsValue({ downloader: manageable[0]?.name });
    setAdding(true);
  }

  async function onSubmit() {
    const v = await form.validateFields();
    try {
      await api.createDownload({
        downloader: v.downloader,
        uri: v.uri,
        save_path: v.save_path || undefined,
      });
      message.success("已提交下载");
      setAdding(false);
      first.current = true; // 立刻刷新一次（带 loading）
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  async function pause(t: DownloadTask) {
    try {
      await api.pauseDownload(t.downloader, t.id);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  async function resume(t: DownloadTask) {
    try {
      await api.resumeDownload(t.downloader, t.id);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  async function doCancel() {
    if (!cancelTarget) return;
    try {
      await api.cancelDownload(cancelTarget.downloader, cancelTarget.id, deleteFiles);
      message.success("已取消");
      setCancelTarget(null);
      setDeleteFiles(false);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  const columns: ColumnsType<DownloadTask> = [
    {
      title: "名称",
      dataIndex: "name",
      ellipsis: ELLIPSIS,
      render: (v) => ellipsisCell(v),
    },
    {
      title: "下载器",
      dataIndex: "downloader",
      width: 110,
      render: (s) => <Tag color="blue">{s}</Tag>,
    },
    {
      title: "状态",
      dataIndex: "state",
      width: 90,
      render: (s: string) => {
        const m = STATE_META[s] ?? STATE_META.unknown;
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: "进度",
      dataIndex: "progress",
      width: 160,
      render: (p: number, r) => (
        <Progress
          percent={Math.round((p || 0) * 1000) / 10}
          size="small"
          status={r.state === "error" ? "exception" : r.state === "completed" ? "success" : "active"}
        />
      ),
    },
    {
      title: "速度",
      dataIndex: "dl_speed",
      width: 100,
      render: (n) => fmtSpeed(n),
    },
    {
      title: "大小",
      dataIndex: "size",
      width: 100,
      render: (n) => fmtBytes(n),
    },
    {
      title: "剩余",
      dataIndex: "eta",
      width: 90,
      render: (n) => fmtEta(n),
    },
    {
      title: "操作",
      width: 180,
      render: (_, t) => (
        <Space>
          {t.state === "paused" ? (
            <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => resume(t)}>
              继续
            </Button>
          ) : (
            <Button
              type="link"
              size="small"
              icon={<PauseCircleOutlined />}
              onClick={() => pause(t)}
              disabled={t.state === "completed"}
            >
              暂停
            </Button>
          )}
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => {
              setDeleteFiles(false);
              setCancelTarget(t);
            }}
          >
            取消
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={openAdd}
          disabled={manageable.length === 0}
        >
          新建下载
        </Button>
        <Button icon={<ReloadOutlined />} onClick={load}>
          刷新
        </Button>
      </Space>
      <Paragraph type="secondary">
        汇总各下载器（qBittorrent / Transmission / aria2）的任务，每 2 秒自动刷新。可暂停/恢复、取消或手动新建下载。
      </Paragraph>

      {downloaders.length > 0 && manageable.length === 0 ? (
        <Empty description="已配置的下载器不支持任务管理（如测试下载器 dummy）" />
      ) : (
        <Table
          rowKey={(t) => `${t.downloader}:${t.id}`}
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={tasks}
          locale={{ emptyText: downloaders.length === 0 ? "未配置下载器" : "暂无下载任务" }}
          pagination={tasks.length > 20 ? { pageSize: 20 } : false}
        />
      )}

      <Modal
        title="新建下载"
        open={adding}
        onOk={onSubmit}
        onCancel={() => setAdding(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="downloader" label="下载器" rules={[{ required: true }]}>
            <Select options={manageable.map((d) => ({ value: d.name, label: d.name }))} />
          </Form.Item>
          <Form.Item
            name="uri"
            label="下载链接"
            rules={[{ required: true, message: "请填写磁力 / 种子 URL / HTTP 链接" }]}
          >
            <Input.TextArea
              rows={3}
              placeholder="magnet:?xt=... 或 https://.../xxx.torrent 或 http 直链"
            />
          </Form.Item>
          <Form.Item name="save_path" label="保存路径（可选）" tooltip="留空则用下载器默认/配置的目录">
            <Input placeholder="如 /downloads" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="取消下载"
        open={!!cancelTarget}
        onOk={doCancel}
        okText="确认取消"
        okButtonProps={{ danger: true }}
        onCancel={() => setCancelTarget(null)}
        destroyOnClose
      >
        <p>
          确定取消任务「{cancelTarget?.name}」？
        </p>
        <Checkbox checked={deleteFiles} onChange={(e) => setDeleteFiles(e.target.checked)}>
          同时删除已下载的文件（不可恢复）
        </Checkbox>
        {cancelTarget?.downloader === "aria2" && deleteFiles && (
          <Paragraph type="warning" style={{ marginTop: 8, marginBottom: 0 }}>
            aria2 无法连同文件删除，仅会移除任务记录。
          </Paragraph>
        )}
      </Modal>
    </>
  );
}
