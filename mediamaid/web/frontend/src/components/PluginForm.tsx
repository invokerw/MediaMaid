import { useState } from "react";
import { Form, Button, Space, message } from "antd";
import { api, PluginEntry } from "../api";
import SchemaFields, { schemaFieldNames } from "./SchemaFields";

export default function PluginForm({
  category,
  entry,
  onSaved,
}: {
  category: string;
  entry: PluginEntry;
  onSaved: (updated: PluginEntry) => void;
}) {
  const fields = schemaFieldNames(entry.schema);
  const props = entry.schema.properties ?? {};
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const initial: Record<string, unknown> = {};
  for (const key of fields) initial[key] = entry.config[key] ?? props[key].default;

  function collect(): Record<string, unknown> {
    const values = form.getFieldsValue();
    const config: Record<string, unknown> = {};
    for (const key of fields) {
      const v = values[key];
      if (v !== undefined && v !== null && v !== "") config[key] = v;
    }
    return config;
  }

  async function onFinish() {
    setSaving(true);
    try {
      const updated = await api.updatePlugin(category, entry.name, {
        enabled: entry.enabled,
        config: collect(),
      });
      message.success("已保存");
      onSaved(updated);
    } catch (e) {
      message.error(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    setTesting(true);
    try {
      const r = await api.testPlugin(category, entry.name, collect());
      if (r.ok) message.success(r.message);
      else message.error(r.message);
    } catch (e) {
      message.error(String(e));
    } finally {
      setTesting(false);
    }
  }

  return (
    <Form form={form} layout="vertical" initialValues={initial} onFinish={onFinish}>
      <SchemaFields schema={entry.schema} />
      <Space>
        <Button type="primary" htmlType="submit" loading={saving}>
          保存
        </Button>
        <Button onClick={onTest} loading={testing}>
          测试连接
        </Button>
      </Space>
    </Form>
  );
}
