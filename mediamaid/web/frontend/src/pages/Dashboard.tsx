import { useEffect, useState } from "react";
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
} from "@ant-design/icons";
import { api, Dashboard as DashboardData, ScanResult } from "../api";
import RecordsTable from "../components/RecordsTable";

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
  { title: "源文件", dataIndex: "source", ellipsis: true },
  {
    title: "目标",
    dataIndex: "dest",
    ellipsis: true,
    render: (d: string | null) =>
      d ? <span className="mono">{d}</span> : <span style={{ opacity: 0.5 }}>—</span>,
  },
];

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResult | null>(null);

  const load = () =>
    api
      .dashboard()
      .then(setData)
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));

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
    { label: "总处理", key: "__total", value: total, color: "#4ea1ff", icon: <DatabaseOutlined /> },
    { label: "已整理", key: "done", value: counts.done ?? 0, color: "#3fb950", icon: <CheckCircleOutlined /> },
    { label: "跳过", key: "skipped", value: counts.skipped ?? 0, color: "#d4a72c", icon: <MinusCircleOutlined /> },
    { label: "失败", key: "failed", value: counts.failed ?? 0, color: "#f85149", icon: <CloseCircleOutlined /> },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        {stats.map((s) => (
          <Col key={s.key} xs={12} sm={6}>
            <Card hoverable>
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

      <Card title="最近记录" size="small">
        <RecordsTable records={data?.records ?? []} loading={loading} />
      </Card>
    </Space>
  );
}
