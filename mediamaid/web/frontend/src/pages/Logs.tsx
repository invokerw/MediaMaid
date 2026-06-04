import { useEffect, useRef, useState } from "react";
import { Card, Space, Switch, Button, Tag, Typography, message } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { api, LogEntry } from "../api";

const LEVEL_COLOR: Record<string, string> = {
  ERROR: "error",
  WARNING: "warning",
  INFO: "default",
  DEBUG: "default",
};

export default function Logs() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [auto, setAuto] = useState(true);
  const timer = useRef<number | null>(null);

  function load() {
    api
      .logs(300)
      .then((d) => setLogs(d.logs))
      .catch((e) => message.error(String(e)));
  }

  useEffect(() => {
    load();
    if (auto) {
      timer.current = window.setInterval(load, 3000);
      return () => {
        if (timer.current) window.clearInterval(timer.current);
      };
    }
  }, [auto]);

  return (
    <Card
      size="small"
      title="通知 / 流水线日志（最新在上，进程内最近 500 条）"
      extra={
        <Space>
          <span>自动刷新</span>
          <Switch checked={auto} onChange={setAuto} size="small" />
          <Button size="small" icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
        </Space>
      }
    >
      <div
        className="mono"
        style={{ maxHeight: "70vh", overflow: "auto", fontSize: 13, lineHeight: 1.9 }}
      >
        {logs.length === 0 ? (
          <Typography.Text type="secondary">暂无日志</Typography.Text>
        ) : (
          logs.map((l, i) => (
            <div key={i}>
              <Typography.Text type="secondary">
                {new Date(l.ts * 1000).toLocaleTimeString()}
              </Typography.Text>{" "}
              <Tag color={LEVEL_COLOR[l.level] || "default"}>{l.level}</Tag>
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                {l.logger.replace(/^mediamaid\.?/, "")}
              </Typography.Text>{" "}
              {l.message}
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
