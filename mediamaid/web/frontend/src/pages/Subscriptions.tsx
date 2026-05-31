import { useEffect, useState } from "react";
import { Tabs, Table, Tag, Button, Space, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, DownloadOutlined } from "@ant-design/icons";
import { api, ReleaseRow, SeenRelease } from "../api";

const { Paragraph, Text } = Typography;

function fmtSize(n: number | null): string {
  if (!n) return "-";
  const gb = n / 1024 ** 3;
  if (gb >= 1) return gb.toFixed(2) + " GB";
  return (n / 1024 ** 2).toFixed(1) + " MB";
}

function PreviewTab() {
  const [rows, setRows] = useState<ReleaseRow[]>([]);
  const [subs, setSubs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [dl, setDl] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api
      .subPreview()
      .then((d) => {
        setRows(d.releases);
        setSubs(d.subscribers);
      })
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  async function download(r: ReleaseRow) {
    setDl(r.guid);
    try {
      await api.downloadRelease({
        title: r.title,
        guid: r.guid,
        magnet: r.magnet,
        torrent_url: r.torrent_url,
        link: r.link,
      });
      message.success(`已提交下载：${r.title}`);
      load();
    } catch (e) {
      message.error(String(e));
    } finally {
      setDl(null);
    }
  }

  const columns: ColumnsType<ReleaseRow> = [
    {
      title: "状态",
      dataIndex: "seen",
      width: 90,
      filters: [
        { text: "新", value: false },
        { text: "已处理", value: true },
      ],
      onFilter: (v, r) => r.seen === v,
      render: (seen: boolean) =>
        seen ? <Tag color="default">已处理</Tag> : <Tag color="processing">新</Tag>,
    },
    { title: "标题", dataIndex: "title", ellipsis: true },
    { title: "大小", dataIndex: "size", width: 110, render: fmtSize },
    { title: "来源", dataIndex: "source", width: 160, ellipsis: true },
    {
      title: "操作",
      width: 100,
      render: (_, r) => (
        <Button
          type="link"
          icon={<DownloadOutlined />}
          loading={dl === r.guid}
          disabled={r.seen || (!r.magnet && !r.torrent_url)}
          onClick={() => download(r)}
        >
          下载
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Space>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          刷新
        </Button>
        <Text type="secondary">
          订阅器：{subs.length ? subs.join(", ") : "（未配置，去插件页启用订阅器）"}
        </Text>
      </Space>
      <Table
        rowKey="guid"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={rows.length > 20 ? { pageSize: 20 } : false}
      />
    </Space>
  );
}

function SeenTab() {
  const [rows, setRows] = useState<SeenRelease[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .seenReleases()
      .then((d) => setRows(d.releases))
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const columns: ColumnsType<SeenRelease> = [
    { title: "标题", dataIndex: "title", ellipsis: true, render: (t, r) => t || r.guid },
    {
      title: "处理时间",
      dataIndex: "ts",
      width: 200,
      render: (ts: number) => new Date(ts * 1000).toLocaleString(),
    },
  ];

  return (
    <Table
      rowKey="guid"
      size="small"
      loading={loading}
      columns={columns}
      dataSource={rows}
      pagination={rows.length > 20 ? { pageSize: 20 } : false}
    />
  );
}

export default function Subscriptions() {
  return (
    <>
      <Paragraph type="secondary">
        预览订阅源当前可见的资源及其处理状态；「新」资源可手动提交下载（需配置下载器）。
      </Paragraph>
      <Tabs
        items={[
          { key: "preview", label: "当前可见资源", children: <PreviewTab /> },
          { key: "seen", label: "已处理资源", children: <SeenTab /> },
        ]}
      />
    </>
  );
}
