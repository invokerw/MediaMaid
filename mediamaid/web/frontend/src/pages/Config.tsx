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
  Alert,
  Space,
  Typography,
  message,
} from "antd";
import { FolderOpenOutlined, LinkOutlined } from "@ant-design/icons";
import { api, Settings } from "../api";
import PathInput from "../components/PathInput";
import DirPicker from "../components/DirPicker";

const { Paragraph } = Typography;

export default function Config() {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [raw, setRaw] = useState<{ path: string; text: string } | null>(null);
  const [pickSrc, setPickSrc] = useState(false);
  const [checking, setChecking] = useState(false);
  const [hl, setHl] = useState<
    { source: string; library: string; ok: boolean; detail: string }[] | null
  >(null);

  async function checkHardlink() {
    setChecking(true);
    try {
      const r = await api.diagHardlink();
      setHl(r.results);
    } catch (e) {
      message.error(String(e));
    } finally {
      setChecking(false);
    }
  }

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
          label="源目录（可多个）"
          rules={[{ required: true, message: "至少一个源目录" }]}
        >
          {tags("回车输入或点下方按钮选择")}
        </Form.Item>
        <Space style={{ marginBottom: 16 }}>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => setPickSrc(true)}>
            添加目录
          </Button>
        </Space>
        <Form.Item name="library_dir" label="媒体库根目录" rules={[{ required: true }]}>
          <PathInput placeholder="/data/media" />
        </Form.Item>
        <Form.Item
          name="failed_dir"
          label="转移失败目录（可选）"
          tooltip="整理/识别失败的文件移此隔离，扫描与监控不再自动重试；可在「文件」页用「手动转移」修复。留空则不启用。建议放在源目录之外。"
        >
          <PathInput placeholder="留空=不启用，如 /data/failed" />
        </Form.Item>
        <Button icon={<LinkOutlined />} loading={checking} onClick={checkHardlink}>
          检测硬链接可用性
        </Button>
        {hl && (
          <Space direction="vertical" style={{ width: "100%", marginTop: 12 }}>
            {hl.map((r) => (
              <Alert
                key={r.source}
                type={r.ok ? "success" : "warning"}
                showIcon
                message={r.source}
                description={r.detail}
              />
            ))}
          </Space>
        )}
      </Card>

      <DirPicker
        open={pickSrc}
        onClose={() => setPickSrc(false)}
        onSelect={(p) => {
          const cur: string[] = form.getFieldValue("source_dirs") || [];
          if (!cur.includes(p)) form.setFieldValue("source_dirs", [...cur, p]);
        }}
      />

      <Card size="small" title="落地" style={{ marginTop: 16 }}>
        <Form.Item name="action" label="落地方式">
          <Select
            options={[
              { value: "hardlink", label: "硬链接（跨盘回退复制）" },
              { value: "symlink", label: "软链接（symlink）" },
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
        <Form.Item
          name="anime_keywords"
          label="动漫归类关键词"
          tooltip="源文件路径命中任一关键词的剧集归入 Anime/ 目录。建议动漫订阅下载到名含 anime 的子目录，或填字幕组名。"
        >
          {tags("如 anime、动漫、字幕组名")}
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
        <Form.Item name={["naming", "anime"]} label="动漫">
          <Input />
        </Form.Item>
        <Form.Item name={["naming", "anime_no_year"]} label="动漫（无年份）">
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
