import { useEffect, useState } from "react";
import {
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Button,
  Card,
  Collapse,
  Divider,
  Typography,
  message,
} from "antd";
import { api, Settings } from "../api";

const { Paragraph } = Typography;

export default function Config() {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [raw, setRaw] = useState<{ path: string; text: string } | null>(null);

  const loadRaw = () => api.config().then(setRaw).catch(() => {});

  useEffect(() => {
    api
      .settings()
      .then((s) => form.setFieldsValue(s))
      .catch((e) => message.error(String(e)));
    loadRaw();
  }, []);

  async function onFinish(values: Settings) {
    setSaving(true);
    try {
      const updated = await api.updateSettings(values);
      form.setFieldsValue(updated);
      message.success("已保存，配置已热重载");
      loadRaw();
    } catch (e) {
      message.error(String(e));
    } finally {
      setSaving(false);
    }
  }

  const tags = (placeholder: string) => (
    <Select mode="tags" tokenSeparators={[",", " "]} placeholder={placeholder} />
  );

  return (
    <Form form={form} layout="vertical" onFinish={onFinish}>
      <Card size="small" title="路径">
        <Form.Item
          name="source_dirs"
          label="源目录（可多个，回车分隔）"
          rules={[{ required: true, message: "至少一个源目录" }]}
        >
          {tags("/data/downloads")}
        </Form.Item>
        <Form.Item name="library_dir" label="媒体库根目录" rules={[{ required: true }]}>
          <Input placeholder="/data/media" />
        </Form.Item>
      </Card>

      <Card size="small" title="落地" style={{ marginTop: 16 }}>
        <Form.Item name="action" label="落地方式">
          <Select
            options={[
              { value: "hardlink", label: "硬链接（跨盘回退复制）" },
              { value: "copy", label: "复制" },
              { value: "move", label: "移动" },
            ]}
          />
        </Form.Item>
        <Form.Item name="on_conflict" label="目标已存在时">
          <Select
            options={[
              { value: "skip", label: "跳过" },
              { value: "overwrite", label: "覆盖" },
              { value: "rename", label: "重命名" },
            ]}
          />
        </Form.Item>
      </Card>

      <Card size="small" title="守护进程" style={{ marginTop: 16 }}>
        <Form.Item name="stable_seconds" label="文件稳定判定（秒）">
          <InputNumber min={1} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="rescan_interval" label="兜底重扫间隔（秒，0 关闭）">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="subscribe_interval" label="订阅轮询间隔（秒）">
          <InputNumber min={1} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="poll_completed" label="轮询下载器已完成任务" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="poll_interval" label="完成轮询间隔（秒）">
          <InputNumber min={1} style={{ width: "100%" }} />
        </Form.Item>
      </Card>

      <Card size="small" title="刮削后处理" style={{ marginTop: 16 }}>
        <Form.Item name="write_nfo" label="生成 .nfo" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="download_artwork" label="下载封面/fanart" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Card>

      <Card size="small" title="过滤" style={{ marginTop: 16 }}>
        <Form.Item name={["filters", "video_extensions"]} label="视频扩展名">
          {tags("mkv")}
        </Form.Item>
        <Form.Item name={["filters", "min_size_mb"]} label="最小体积（MB）">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name={["filters", "exclude_keywords"]} label="排除关键词">
          {tags("sample")}
        </Form.Item>
      </Card>

      <Card size="small" title="命名模板" style={{ marginTop: 16 }}>
        <Form.Item name={["naming", "movie"]} label="电影">
          <Input />
        </Form.Item>
        <Form.Item name={["naming", "movie_no_year"]} label="电影（无年份）">
          <Input />
        </Form.Item>
        <Form.Item name={["naming", "episode"]} label="剧集">
          <Input />
        </Form.Item>
        <Form.Item name={["naming", "episode_no_year"]} label="剧集（无年份）">
          <Input />
        </Form.Item>
      </Card>

      <Divider />
      <Form.Item>
        <Button type="primary" htmlType="submit" loading={saving}>
          保存配置
        </Button>
      </Form.Item>

      <Collapse
        items={[
          {
            key: "raw",
            label: `查看原始 YAML（${raw?.path ?? ""}）`,
            children: (
              <Paragraph className="result mono" style={{ marginBottom: 0 }}>
                {raw?.text ?? "加载中…"}
              </Paragraph>
            ),
          },
        ]}
      />
    </Form>
  );
}
