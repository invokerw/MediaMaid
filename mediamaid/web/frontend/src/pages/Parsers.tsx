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
  Select,
  Popconfirm,
  Card,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { PlusOutlined, ThunderboltOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { api, ParserRow, SubscriberType, ParseTestResult } from "../api";
import SchemaFields from "../components/SchemaFields";
import DirPicker from "../components/DirPicker";
import { ELLIPSIS, ellipsisCell } from "../components/EllipsisCell";

const { Paragraph, Text } = Typography;

export default function Parsers() {
  const [parsers, setParsers] = useState<ParserRow[]>([]);
  const [types, setTypes] = useState<SubscriberType[]>([]);
  const [editing, setEditing] = useState<ParserRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();
  const selectedType = Form.useWatch("parser", form);

  // 解析测试框（单个文件名）
  const [sample, setSample] = useState("");
  const [result, setResult] = useState<ParseTestResult | null>(null);
  // 目录测试（真实下载文件）
  const [pickDir, setPickDir] = useState(false);
  const [dirRows, setDirRows] = useState<
    (ParseTestResult & { name: string; path: string })[] | null
  >(null);
  const [dirLoading, setDirLoading] = useState(false);

  async function testDir(path: string) {
    setDirLoading(true);
    try {
      const d = await api.parseTestDir(path);
      setDirRows(d.results);
    } catch (e) {
      message.error(String(e));
    } finally {
      setDirLoading(false);
    }
  }

  const load = () =>
    api.parsers().then((d) => setParsers(d.parsers)).catch((e) => message.error(String(e)));

  useEffect(() => {
    load();
    api.parserTypes().then((d) => setTypes(d.parsers)).catch(() => {});
  }, []);

  function openAdd() {
    setEditing(null);
    setAdding(true);
    form.resetFields();
    form.setFieldsValue({ parser: types[0]?.name });
  }
  function openEdit(p: ParserRow) {
    setEditing(p);
    setAdding(true);
    form.resetFields();
    form.setFieldsValue({ name: p.name, parser: p.parser, config: p.config });
  }

  async function onSubmit() {
    const v = await form.validateFields();
    const body = {
      name: v.name,
      parser: v.parser,
      enabled: editing ? editing.enabled : true,
      config: v.config || {},
    };
    try {
      if (editing) await api.updateParser(editing.id, body);
      else await api.createParser(body);
      message.success("已保存");
      setAdding(false);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  async function toggle(p: ParserRow, enabled: boolean) {
    try {
      await api.updateParser(p.id, { enabled });
      setParsers((arr) => arr.map((x) => (x.id === p.id ? { ...x, enabled } : x)));
    } catch (e) {
      message.error(String(e));
    }
  }
  async function remove(p: ParserRow) {
    try {
      await api.deleteParser(p.id);
      message.success(`已删除 ${p.name}`);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }
  async function runTest() {
    if (!sample.trim()) return;
    try {
      setResult(await api.parseTest(sample.trim()));
    } catch (e) {
      message.error(String(e));
    }
  }

  const schema = types.find((t) => t.name === selectedType)?.schema ?? { properties: {} };

  const columns: ColumnsType<ParserRow> = [
    { title: "名称", dataIndex: "name" },
    { title: "类型", dataIndex: "parser", width: 100, render: (s) => <Tag color="purple">{s}</Tag> },
    {
      title: "pattern/参数",
      dataIndex: "config",
      ellipsis: ELLIPSIS,
      render: (c: Record<string, unknown>) => {
        const s = String(c.pattern ?? Object.values(c)[0] ?? "");
        return ellipsisCell(s, <span className="mono">{s}</span>);
      },
    },
    {
      title: "启用",
      dataIndex: "enabled",
      width: 80,
      render: (v, p) => <Switch checked={v} onChange={(e) => toggle(p, e)} />,
    },
    {
      title: "操作",
      width: 150,
      render: (_, p) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(p)}>编辑</Button>
          <Popconfirm title={`删除「${p.name}」？`} onConfirm={() => remove(p)}>
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Paragraph type="secondary">
        解析器按从上到下顺序尝试，首个解析出标题者胜出；留空则用内置 guessit。
        正则解析器用命名组提取：<Text code>{"(?P<title>…) (?P<season>\\d+) (?P<episode>\\d+) (?P<year>\\d+)"}</Text>
      </Paragraph>

      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>添加解析器</Button>
      </Space>

      <Table rowKey="id" size="middle" columns={columns} dataSource={parsers} pagination={false} />

      <Card size="small" title="测试：单个文件名" style={{ marginTop: 16 }}>
        <Space.Compact style={{ width: "100%" }}>
          <Input
            placeholder="粘贴一个文件名（注意是文件名，不是种子/合集名）"
            value={sample}
            onChange={(e) => setSample(e.target.value)}
            onPressEnter={runTest}
          />
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={runTest}>测试</Button>
        </Space.Compact>
        {result && (
          <div style={{ marginTop: 12 }}>
            {result.matched ? (
              <Space wrap>
                <Tag color="green">命中: {result.matched}</Tag>
                <Tag>类型: {result.type}</Tag>
                <Tag color="blue">标题: {result.title}</Tag>
                {result.season != null && <Tag>S{result.season}</Tag>}
                {result.episode != null && <Tag>E{result.episode}</Tag>}
                {result.year && <Tag>年份: {result.year}</Tag>}
              </Space>
            ) : (
              <Text type="warning">无解析器命中（标题解析不出）</Text>
            )}
          </div>
        )}
      </Card>

      <Card
        size="small"
        title="测试：目录中的真实文件（合集会逐个文件解析）"
        style={{ marginTop: 16 }}
        extra={
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => setPickDir(true)}>
            选择目录测试
          </Button>
        }
      >
        {dirRows ? (
          <Table
            rowKey="path"
            size="small"
            loading={dirLoading}
            pagination={dirRows.length > 20 ? { pageSize: 20 } : false}
            dataSource={dirRows}
            columns={[
              { title: "文件名", dataIndex: "name", ellipsis: ELLIPSIS, render: (v) => ellipsisCell(v) },
              {
                title: "解析结果",
                render: (_: unknown, r) =>
                  r.matched ? (
                    <Space wrap>
                      <Tag color="green">{r.matched}</Tag>
                      <Tag color="blue">{r.title}</Tag>
                      {r.type && <Tag>{r.type}</Tag>}
                      {r.season != null && <Tag>S{r.season}</Tag>}
                      {r.episode != null && <Tag>E{r.episode}</Tag>}
                    </Space>
                  ) : (
                    <Tag color="warning">未解析出</Tag>
                  ),
              },
            ]}
          />
        ) : (
          <Text type="secondary">选择源/下载目录，对里面真实下载的文件逐个测试解析。</Text>
        )}
      </Card>

      <DirPicker
        open={pickDir}
        onClose={() => setPickDir(false)}
        onSelect={(p) => testDir(p)}
      />

      <Modal
        title={editing ? "编辑解析器" : "添加解析器"}
        open={adding}
        onOk={onSubmit}
        onCancel={() => setAdding(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="如：遮天字幕组" />
          </Form.Item>
          <Form.Item name="parser" label="解析器类型" rules={[{ required: true }]}>
            <Select options={types.map((t) => ({ value: t.name, label: t.name }))} disabled={!!editing} />
          </Form.Item>
          <SchemaFields schema={schema} prefix={["config"]} />
        </Form>
      </Modal>
    </>
  );
}
