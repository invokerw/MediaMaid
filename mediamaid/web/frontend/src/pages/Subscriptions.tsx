import { useEffect, useState } from "react";
import {
  Table,
  Tag,
  Button,
  Space,
  Switch,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Tabs,
  Divider,
  Popconfirm,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  PlusOutlined,
  DownloadOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  api,
  SubscriptionRow,
  SubscriberType,
  ReleaseRow,
  SeenRelease,
} from "../api";
import SchemaFields from "../components/SchemaFields";
import { ELLIPSIS, ellipsisCell } from "../components/EllipsisCell";

const { Paragraph } = Typography;

export default function Subscriptions() {
  const [subs, setSubs] = useState<SubscriptionRow[]>([]);
  const [types, setTypes] = useState<SubscriberType[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<SubscriptionRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [detail, setDetail] = useState<SubscriptionRow | null>(null);
  const [form] = Form.useForm();
  const selectedType = Form.useWatch("subscriber", form);

  const load = () => {
    setLoading(true);
    api
      .subscriptions()
      .then((d) => setSubs(d.subscriptions))
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    api.subscriberTypes().then((d) => setTypes(d.subscribers)).catch(() => {});
  }, []);

  function openAdd() {
    setEditing(null);
    setAdding(true);
    form.resetFields();
    form.setFieldsValue({ subscriber: types[0]?.name, skip_existing: true });
  }

  function openEdit(s: SubscriptionRow) {
    setEditing(s);
    setAdding(true);
    form.resetFields();
    form.setFieldsValue({
      name: s.name,
      subscriber: s.subscriber,
      config: s.config,
      filters: s.filters,
      skip_existing: s.skip_existing ?? true,
    });
  }

  async function onSubmit() {
    const v = await form.validateFields();
    const body = {
      name: v.name,
      subscriber: v.subscriber,
      enabled: editing ? editing.enabled : true,
      config: v.config || {},
      filters: v.filters || {},
      skip_existing: v.skip_existing ?? true,
    };
    try {
      if (editing) await api.updateSubscription(editing.id, body);
      else await api.createSubscription(body);
      message.success("已保存");
      setAdding(false);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  async function toggle(s: SubscriptionRow, enabled: boolean) {
    try {
      await api.updateSubscription(s.id, { enabled });
      setSubs((arr) => arr.map((x) => (x.id === s.id ? { ...x, enabled } : x)));
    } catch (e) {
      message.error(String(e));
    }
  }

  async function remove(s: SubscriptionRow) {
    try {
      await api.deleteSubscription(s.id);
      message.success(`已删除 ${s.name}`);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  const schema = types.find((t) => t.name === selectedType)?.schema ?? { properties: {} };

  const columns: ColumnsType<SubscriptionRow> = [
    { title: "名称", dataIndex: "name" },
    {
      title: "订阅器",
      dataIndex: "subscriber",
      width: 110,
      render: (s) => <Tag color="blue">{s}</Tag>,
    },
    {
      title: "URL/参数",
      dataIndex: "config",
      ellipsis: ELLIPSIS,
      render: (c: Record<string, unknown>) => {
        const s = String(c.url ?? Object.values(c)[0] ?? "");
        return ellipsisCell(s, <span className="mono">{s}</span>);
      },
    },
    { title: "已处理", dataIndex: "processed", width: 80 },
    {
      title: "已抓集数",
      dataIndex: "grabbed_episodes",
      width: 90,
      render: (n?: number) => n ?? 0,
    },
    {
      title: "启用",
      dataIndex: "enabled",
      width: 80,
      render: (v, s) => <Switch checked={v} onChange={(e) => toggle(s, e)} />,
    },
    {
      title: "操作",
      width: 200,
      render: (_, s) => (
        <Space>
          <Button type="link" size="small" onClick={() => setDetail(s)}>
            详情
          </Button>
          <Button type="link" size="small" onClick={() => openEdit(s)}>
            编辑
          </Button>
          <Popconfirm title={`删除订阅「${s.name}」？`} onConfirm={() => remove(s)}>
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
          添加订阅
        </Button>
        <Button icon={<ReloadOutlined />} onClick={load}>
          刷新
        </Button>
      </Space>
      <Paragraph type="secondary">
        每条订阅选一个订阅器类型并填参数（如 RSS 的 URL）。点「详情」查看该订阅可见/已处理的资源。
      </Paragraph>

      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={subs}
        pagination={false}
      />

      <Modal
        title={editing ? "编辑订阅" : "添加订阅"}
        open={adding}
        onOk={onSubmit}
        onCancel={() => setAdding(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="如：遮天" />
          </Form.Item>
          <Form.Item name="subscriber" label="订阅器" rules={[{ required: true }]}>
            <Select
              options={types.map((t) => ({ value: t.name, label: t.name }))}
              disabled={!!editing}
            />
          </Form.Item>
          <SchemaFields schema={schema} prefix={["config"]} />

          <Divider orientation="left" plain style={{ marginTop: 8 }}>
            高级过滤（可选）
          </Divider>
          <Form.Item name={["filters", "resolutions"]} label="分辨率（命中其一）">
            <Select
              mode="tags"
              placeholder="如 1080p、2160p；留空不限"
              tokenSeparators={[",", " "]}
            />
          </Form.Item>
          <Form.Item name={["filters", "include_keywords"]} label="必含关键词（全部命中）">
            <Select mode="tags" placeholder="如 中字、内封" tokenSeparators={[",", " "]} />
          </Form.Item>
          <Form.Item name={["filters", "exclude_keywords"]} label="排除关键词（命中即丢弃）">
            <Select mode="tags" placeholder="如 HDTV、枪版" tokenSeparators={[",", " "]} />
          </Form.Item>
          <Space>
            <Form.Item name={["filters", "min_size_mb"]} label="最小体积(MB)">
              <InputNumber min={0} placeholder="不限" />
            </Form.Item>
            <Form.Item name={["filters", "max_size_mb"]} label="最大体积(MB)">
              <InputNumber min={0} placeholder="不限" />
            </Form.Item>
          </Space>
          <Form.Item
            name={["filters", "prefer"]}
            label="择优优先级（同一集多候选时靠前者优先）"
          >
            <Select
              mode="tags"
              placeholder="如 2160p、REMUX、内封"
              tokenSeparators={[",", " "]}
            />
          </Form.Item>
          <Form.Item
            name="skip_existing"
            label="跳过媒体库已有"
            valuePropName="checked"
            tooltip="启用后，已在媒体服务器库中的资源不再重复下载"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={detail ? `订阅详情 · ${detail.name}` : ""}
        width={760}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        destroyOnClose
      >
        {detail && <SubDetail sub={detail} />}
      </Modal>
    </>
  );
}

function SubDetail({ sub }: { sub: SubscriptionRow }) {
  return (
    <Tabs
      items={[
        { key: "preview", label: "当前可见资源", children: <PreviewTab sub={sub} /> },
        { key: "done", label: `已处理 (${sub.processed})`, children: <DoneTab sub={sub} /> },
      ]}
    />
  );
}

function PreviewTab({ sub }: { sub: SubscriptionRow }) {
  const [rows, setRows] = useState<ReleaseRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [dl, setDl] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api
      .subPreview(sub.id)
      .then((d) => setRows(d.releases))
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(load, [sub.id]);

  async function download(r: ReleaseRow) {
    setDl(r.guid);
    try {
      await api.downloadRelease({
        title: r.title,
        guid: r.guid,
        magnet: r.magnet,
        torrent_url: r.torrent_url,
        link: r.link,
        sub_id: sub.id,
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
      width: 80,
      render: (s) => (s ? <Tag>已处理</Tag> : <Tag color="processing">新</Tag>),
    },
    { title: "标题", dataIndex: "title", ellipsis: ELLIPSIS, render: (v) => ellipsisCell(v) },
    {
      title: "操作",
      width: 110,
      render: (_, r) => (
        <Button
          type="link"
          size="small"
          icon={<DownloadOutlined />}
          loading={dl === r.guid}
          disabled={!r.magnet && !r.torrent_url}
          onClick={() => download(r)}
        >
          {r.seen ? "重新处理" : "下载"}
        </Button>
      ),
    },
  ];

  return (
    <>
      <Button size="small" icon={<ReloadOutlined />} onClick={load} style={{ marginBottom: 8 }}>
        刷新
      </Button>
      <Table
        rowKey="guid"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={rows.length > 15 ? { pageSize: 15 } : false}
      />
    </>
  );
}

function DoneTab({ sub }: { sub: SubscriptionRow }) {
  const [rows, setRows] = useState<SeenRelease[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .subReleases(sub.id)
      .then((d) => setRows(d.releases))
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }, [sub.id]);

  const columns: ColumnsType<SeenRelease> = [
    {
      title: "标题",
      dataIndex: "title",
      ellipsis: ELLIPSIS,
      render: (t, r) => ellipsisCell(t || r.guid),
    },
    {
      title: "处理时间",
      dataIndex: "ts",
      width: 180,
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
      pagination={rows.length > 15 ? { pageSize: 15 } : false}
    />
  );
}
