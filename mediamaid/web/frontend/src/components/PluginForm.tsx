import { useState } from "react";
import { Form, Input, InputNumber, Switch, Button, Space, Typography, message } from "antd";
import { api, PluginEntry } from "../api";

const { Text } = Typography;

const isSecret = (key: string) => /key|password|secret|token/i.test(key);

export default function PluginForm({
  category,
  entry,
  onSaved,
}: {
  category: string;
  entry: PluginEntry;
  onSaved: (updated: PluginEntry) => void;
}) {
  const props = entry.schema.properties ?? {};
  const required = entry.schema.required ?? [];
  const fields = Object.keys(props);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  // 初始值：当前配置优先，否则用 schema 默认
  const initial: Record<string, unknown> = {};
  for (const key of fields) {
    initial[key] = entry.config[key] ?? props[key].default;
  }

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
      {fields.length === 0 && (
        <Text type="secondary">该插件无可配置参数，可直接用开关启停。</Text>
      )}
      {fields.map((key) => {
        const p = props[key];
        const label = p.title || key;
        const req = required.includes(key);
        const rules = req ? [{ required: true, message: `请填写 ${label}` }] : [];
        let control;
        if (p.type === "boolean") {
          return (
            <Form.Item key={key} name={key} label={label} valuePropName="checked" tooltip={p.description}>
              <Switch />
            </Form.Item>
          );
        } else if (p.type === "integer" || p.type === "number") {
          control = <InputNumber style={{ width: "100%" }} />;
        } else if (isSecret(key)) {
          control = <Input.Password placeholder={req ? "必填" : "可选"} />;
        } else {
          control = <Input placeholder={req ? "必填" : "可选"} />;
        }
        return (
          <Form.Item key={key} name={key} label={label} rules={rules} tooltip={p.description}>
            {control}
          </Form.Item>
        );
      })}
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
