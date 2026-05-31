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
import { PlusOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { api, ParserRow, SubscriberType, ParseTestResult } from "../api";
import SchemaFields from "../components/SchemaFields";

const { Paragraph, Text } = Typography;

export default function Parsers() {
  const [parsers, setParsers] = useState<ParserRow[]>([]);
  const [types, setTypes] = useState<SubscriberType[]>([]);
  const [editing, setEditing] = useState<ParserRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();
  const selectedType = Form.useWatch("parser", form);

  // 解析测试框
  const [sample, setSample] = useState("");
  const [result, setResult] = useState<ParseTestResult | null>(null);

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
      ellipsis: true,
      render: (c: Record<string, unknown>) =>
        <span className="mono">{String(c.pattern ?? Object.values(c)[0] ?? "")}</span>,
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

      <Card size="small" title="解析测试" style={{ marginTop: 16 }}>
        <Space.Compact style={{ width: "100%" }}>
          <Input
            placeholder="粘贴一个文件名，如 [GM-Team][遮天][162]...mkv"
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
