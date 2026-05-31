import { Form, Input, InputNumber, Switch, Typography } from "antd";
import { JsonSchema } from "../api";
import PathInput from "./PathInput";

const { Text } = Typography;

const isSecret = (key: string) => /key|password|secret|token/i.test(key);
const isPath = (key: string) => /path|dir/i.test(key);

/** 根据 JSON schema 的 properties 渲染一组 antd 表单项。
 *  name 为 [...prefix, key]，供嵌套（如 config.xxx）使用。 */
export default function SchemaFields({
  schema,
  prefix = [],
}: {
  schema: JsonSchema;
  prefix?: (string | number)[];
}) {
  const props = schema.properties ?? {};
  const required = schema.required ?? [];
  const fields = Object.keys(props);

  if (fields.length === 0) {
    return <Text type="secondary">该订阅器无可配置参数。</Text>;
  }

  return (
    <>
      {fields.map((key) => {
        const p = props[key];
        const label = p.title || key;
        const name = [...prefix, key];
        const req = required.includes(key);
        const rules = req ? [{ required: true, message: `请填写 ${label}` }] : [];

        if (p.type === "boolean") {
          return (
            <Form.Item key={key} name={name} label={label} valuePropName="checked" tooltip={p.description}>
              <Switch />
            </Form.Item>
          );
        }
        let control;
        if (p.type === "integer" || p.type === "number") {
          control = <InputNumber style={{ width: "100%" }} />;
        } else if (isSecret(key)) {
          control = <Input.Password placeholder={req ? "必填" : "可选"} />;
        } else if (isPath(key)) {
          control = <PathInput placeholder={req ? "必填" : "可选"} />;
        } else {
          control = <Input placeholder={req ? "必填" : "可选"} />;
        }
        return (
          <Form.Item key={key} name={name} label={label} rules={rules} tooltip={p.description}>
            {control}
          </Form.Item>
        );
      })}
    </>
  );
}

/** schema 的字段名列表（用于收集/清洗值）。 */
export function schemaFieldNames(schema: JsonSchema): string[] {
  return Object.keys(schema.properties ?? {});
}
