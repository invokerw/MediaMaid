import { useEffect, useState } from "react";
import {
  Row,
  Col,
  Card,
  Statistic,
  Button,
  Space,
  Typography,
  message,
} from "antd";
import {
  EyeOutlined,
  PlayCircleOutlined,
  CloudDownloadOutlined,
} from "@ant-design/icons";
import { api, Dashboard as DashboardData, ScanResult } from "../api";
import RecordsTable from "../components/RecordsTable";

const { Title, Paragraph } = Typography;

const CARDS: { label: string; key: string; color?: string }[] = [
  { label: "已整理", key: "done", color: "#3fb950" },
  { label: "跳过", key: "skipped", color: "#d4a72c" },
  { label: "失败", key: "failed", color: "#f85149" },
];

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const load = () =>
    api
      .dashboard()
      .then(setData)
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  async function run(tag: string, fn: () => Promise<unknown>, okMsg: string) {
    setBusy(tag);
    try {
      const r = await fn();
      setResult(formatResult(r));
      message.success(okMsg);
      await load();
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Title level={3}>仪表盘</Title>

      <Row gutter={16}>
        {CARDS.map((c) => (
          <Col key={c.key} xs={8}>
            <Card>
              <Statistic
                title={c.label}
                value={data?.counts[c.key] ?? 0}
                valueStyle={{ color: c.color }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Space style={{ margin: "20px 0" }} wrap>
        <Button
          icon={<EyeOutlined />}
          loading={busy === "dry"}
          onClick={() => run("dry", () => api.scan(true), "预览完成")}
        >
          扫描预览 (dry-run)
        </Button>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={busy === "scan"}
          onClick={() => run("scan", () => api.scan(false), "扫描整理完成")}
        >
          执行扫描整理
        </Button>
        <Button
          icon={<CloudDownloadOutlined />}
          loading={busy === "sub"}
          onClick={() => run("sub", () => api.subscribe(), "订阅已运行")}
        >
          运行订阅一轮
        </Button>
      </Space>

      {result && (
        <Card size="small" title="执行结果" style={{ marginBottom: 24 }}>
          <Paragraph className="result mono" style={{ marginBottom: 0 }}>
            {result}
          </Paragraph>
        </Card>
      )}

      <Title level={4}>最近记录</Title>
      <RecordsTable records={data?.records ?? []} loading={loading} />
    </>
  );
}

function formatResult(r: unknown): string {
  const s = r as ScanResult;
  if (s && s.summary) {
    const head = (s.dry_run ? "[预览] " : "") +
      Object.entries(s.summary).map(([k, v]) => `${k}: ${v}`).join("   ");
    const lines = (s.items || []).map(
      (i) => `  ${i.status.padEnd(8)} ${i.source}${i.dest ? "  →  " + i.dest : ""}`
    );
    return [head, ...lines].join("\n");
  }
  return JSON.stringify(r, null, 2);
}
