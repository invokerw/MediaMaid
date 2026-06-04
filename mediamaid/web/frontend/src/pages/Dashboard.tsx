import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Row,
  Col,
  Card,
  Statistic,
  Button,
  Space,
  Table,
  Tag,
  Tooltip,
  Alert,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  EyeOutlined,
  PlayCircleOutlined,
  CloudDownloadOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  MinusCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  WarningOutlined,
  DownloadOutlined,
} from "@ant-design/icons";
import { api, Dashboard as DashboardData, ScanResult, LogEntry } from "../api";
import RecordsTable from "../components/RecordsTable";
import { ELLIPSIS, ellipsisCell } from "../components/EllipsisCell";

const LOG_COLOR: Record<string, string> = { ERROR: "#f85149", WARNING: "#d4a72c" };

const STATUS_COLOR: Record<string, string> = {
  done: "success",
  skipped: "warning",
  failed: "error",
};

interface ScanItem {
  source: string;
  status: string;
  dest: string | null;
}

const scanColumns: ColumnsType<ScanItem> = [
  {
    title: "状态",
    dataIndex: "status",
    width: 90,
    filters: [
      { text: "done", value: "done" },
      { text: "skipped", value: "skipped" },
      { text: "failed", value: "failed" },
    ],
    onFilter: (v, r) => r.status === v,
    render: (s: string) => <Tag color={STATUS_COLOR[s] || "default"}>{s}</Tag>,
  },
  { title: "源文件", dataIndex: "source", ellipsis: ELLIPSIS, render: (v) => ellipsisCell(v) },
  {
    title: "目标",
    dataIndex: "dest",
    ellipsis: ELLIPSIS,
    render: (d: string | null) =>
      d ? ellipsisCell(d, <span className="mono">{d}</span>) : <span style={{ opacity: 0.5 }}>—</span>,
  },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [dlCount, setDlCount] = useState<number | null>(null);

  const load = () => {
    api
      .dashboard()
      .then(setData)
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
    api.logs(8).then((d) => setLogs(d.logs)).catch(() => {});
    // 下载任务数为尽力而为（需连下载器，失败忽略）
    api.downloads().then((d) => setDlCount(d.tasks.length)).catch(() => setDlCount(null));
  };

  useEffect(() => {
    load();
  }, []);

  async function runScan(dry: boolean) {
    setBusy(dry ? "dry" : "scan");
    try {
      const r = await api.scan(dry);
      setScan(r);
      const done = r.summary.done ?? 0;
      message.success(`${dry ? "预览" : "整理"}完成：done ${done} / 共 ${r.items.length}`);
      await load();
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function runSubscribe() {
    setBusy("sub");
    try {
      const r = await api.subscribe();
      message.success(`订阅完成，新提交 ${r.submitted} 个下载`);
      await load();
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(null);
    }
  }

  const counts = data?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  const stats = [
    { label: "总处理", value: total, color: "#4ea1ff", icon: <DatabaseOutlined />, to: "/records" },
    { label: "已整理", value: counts.done ?? 0, color: "#3fb950", icon: <CheckCircleOutlined />, to: "/records?status=done" },
    { label: "跳过", value: counts.skipped ?? 0, color: "#d4a72c", icon: <MinusCircleOutlined />, to: "/records?status=skipped" },
    { label: "失败", value: counts.failed ?? 0, color: "#f85149", icon: <CloseCircleOutlined />, to: "/records?status=failed" },
    { label: "订阅", value: data?.subscriptions ?? 0, color: "#a371f7", icon: <CloudDownloadOutlined />, to: "/subscriptions" },
    { label: "下载任务", value: dlCount ?? "-", color: "#4ea1ff", icon: <DownloadOutlined />, to: "/downloads" },
  ];

  const noKey = data?.health && data.health.tmdb_key === false;
  const backlog = data?.failed && data.failed.count > 0;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {(noKey || backlog) && (
        <Space direction="vertical" size="small" style={{ width: "100%" }}>
          {noKey && (
            <Alert
              type="error"
              showIcon
              icon={<WarningOutlined />}
              message="未配置 TMDB API Key——扫描整理会直接报错。请到「插件」页填写。"
              action={<Button size="small" onClick={() => navigate("/plugins")}>去配置</Button>}
            />
          )}
          {backlog && (
            <Alert
              type="warning"
              showIcon
              message={`有 ${data!.failed!.count} 个文件转移/识别失败被隔离，待人工处理。`}
              action={<Button size="small" onClick={() => navigate("/files")}>去文件页</Button>}
            />
          )}
        </Space>
      )}

      <Row gutter={[16, 16]}>
        {stats.map((s) => (
          <Col key={s.label} xs={12} sm={8} md={4}>
            <Card hoverable onClick={() => navigate(s.to)} style={{ cursor: "pointer" }}>
              <Statistic
                title={s.label}
                value={s.value}
                valueStyle={{ color: s.color }}
                prefix={s.icon}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        title="操作"
        size="small"
        extra={
          <Tooltip title="刷新数据">
            <Button
              type="text"
              icon={<ReloadOutlined />}
              onClick={() => {
                setLoading(true);
                load();
              }}
            />
          </Tooltip>
        }
      >
        <Space wrap>
          <Button icon={<EyeOutlined />} loading={busy === "dry"} onClick={() => runScan(true)}>
            扫描预览 (dry-run)
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={busy === "scan"}
            onClick={() => runScan(false)}
          >
            执行扫描整理
          </Button>
          <Button
            icon={<CloudDownloadOutlined />}
            loading={busy === "sub"}
            onClick={runSubscribe}
          >
            运行订阅一轮
          </Button>
        </Space>
      </Card>

      {scan && (
        <Card
          size="small"
          title={
            <Space>
              {scan.dry_run && <Tag color="processing">预览</Tag>}
              <span>扫描结果</span>
              {Object.entries(scan.summary).map(([k, v]) => (
                <Tag key={k} color={STATUS_COLOR[k] || "default"}>
                  {k}: {v}
                </Tag>
              ))}
            </Space>
          }
          extra={
            <Button type="text" size="small" onClick={() => setScan(null)}>
              清除
            </Button>
          }
        >
          <Table
            rowKey={(r) => r.source}
            size="small"
            columns={scanColumns}
            dataSource={scan.items}
            pagination={scan.items.length > 10 ? { pageSize: 10 } : false}
          />
        </Card>
      )}

      <Card
        title="最近日志"
        size="small"
        extra={<Button type="link" size="small" onClick={() => navigate("/logs")}>查看全部</Button>}
      >
        {logs.length === 0 ? (
          <Typography.Text type="secondary">暂无日志</Typography.Text>
        ) : (
          <div className="mono" style={{ fontSize: 13, lineHeight: 1.9 }}>
            {logs.map((l, i) => (
              <div key={i} style={{ color: LOG_COLOR[l.level] }}>
                <Typography.Text type="secondary">
                  {new Date(l.ts * 1000).toLocaleTimeString()}
                </Typography.Text>{" "}
                [{l.level}] {l.message}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="最近记录" size="small">
        <RecordsTable records={data?.records ?? []} loading={loading} />
      </Card>
    </Space>
  );
}
