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
  Radio,
  Select,
  Popconfirm,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { PlusOutlined, MinusCircleOutlined } from "@ant-design/icons";
import { api, TmdbRuleRow } from "../api";
import { ELLIPSIS, ellipsisCell } from "../components/EllipsisCell";

const { Paragraph, Text } = Typography;

function typeTag(mediaType: string, category: string) {
  if (mediaType === "movie") return <Tag color="purple">电影</Tag>;
  if (category === "anime") return <Tag color="magenta">动漫</Tag>;
  return <Tag color="geekblue">剧集</Tag>;
}

function ignoreSummary(r: TmdbRuleRow): string {
  const parts: string[] = [];
  if (r.ignore_seasons.length) parts.push("季 " + r.ignore_seasons.join(","));
  for (const ie of r.ignore_episodes) parts.push(`S${ie.season}: ${ie.episodes.join(",")}`);
  return parts.join(" / ");
}

export default function TmdbRules() {
  const [rules, setRules] = useState<TmdbRuleRow[]>([]);
  const [editing, setEditing] = useState<TmdbRuleRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();
  const mediaType = Form.useWatch("media_type", form);
  const isEpisode = mediaType !== "movie";
  const [preview, setPreview] = useState<string | null>(null);

  const load = () =>
    api.tmdbRules().then((d) => setRules(d.rules)).catch((e) => message.error(String(e)));

  useEffect(() => {
    load();
  }, []);

  function openAdd() {
    setEditing(null);
    setAdding(true);
    setPreview(null);
    form.resetFields();
    form.setFieldsValue({ media_type: "episode", category: "tv", patterns: [""], ignore_seasons: [] });
  }
  function openEdit(r: TmdbRuleRow) {
    setEditing(r);
    setAdding(true);
    setPreview(null);
    form.resetFields();
    form.setFieldsValue({
      tmdb_id: r.tmdb_id,
      title: r.title,
      media_type: r.media_type,
      category: r.category,
      season: r.season ?? undefined,
      patterns: r.patterns.length ? r.patterns : [""],
      ignore_seasons: r.ignore_seasons.map(String),
      ignore_episodes: r.ignore_episodes.map((ie) => ({
        season: ie.season,
        episodes: ie.episodes.map(String),
      })),
    });
  }

  async function doPreview() {
    const v = form.getFieldsValue();
    if (!v.tmdb_id) {
      message.warning("请先填写 TMDB ID");
      return;
    }
    try {
      const r = await api.tmdbPreview({
        tmdb_id: v.tmdb_id,
        media_type: v.media_type,
        season: isEpisode ? v.season : undefined,
      });
      setPreview(`${r.title}${r.year ? ` (${r.year})` : ""} → ${r.dest_preview}`);
      if (!v.title) form.setFieldsValue({ title: r.title });
    } catch (e) {
      message.error(String(e));
    }
  }

  async function onSubmit() {
    const v = await form.validateFields();
    const body = {
      tmdb_id: v.tmdb_id,
      title: v.title || "",
      media_type: v.media_type,
      category: isEpisode ? v.category || "tv" : "tv",
      enabled: editing ? editing.enabled : true,
      patterns: (v.patterns || []).filter((p: string) => p && p.trim()),
      season: isEpisode ? (v.season ?? null) : null,
      ignore_seasons: isEpisode ? (v.ignore_seasons || []).map(Number) : [],
      ignore_episodes: isEpisode
        ? (v.ignore_episodes || []).map((ie: { season: number; episodes: string[] }) => ({
            season: Number(ie.season),
            episodes: (ie.episodes || []).map(Number),
          }))
        : [],
    };
    try {
      if (editing) await api.updateTmdbRule(editing.id, body);
      else await api.createTmdbRule(body);
      message.success("已保存");
      setAdding(false);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  async function toggle(r: TmdbRuleRow, enabled: boolean) {
    try {
      await api.updateTmdbRule(r.id, { enabled });
      setRules((arr) => arr.map((x) => (x.id === r.id ? { ...x, enabled } : x)));
    } catch (e) {
      message.error(String(e));
    }
  }
  async function remove(r: TmdbRuleRow) {
    try {
      await api.deleteTmdbRule(r.id);
      message.success("已删除");
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  const columns: ColumnsType<TmdbRuleRow> = [
    {
      title: "TMDB",
      width: 90,
      render: (_, r) => <a href={`https://www.themoviedb.org/${r.media_type === "movie" ? "movie" : "tv"}/${r.tmdb_id}`} target="_blank" rel="noreferrer">#{r.tmdb_id}</a>,
    },
    { title: "标题", dataIndex: "title", ellipsis: ELLIPSIS, render: (v) => ellipsisCell(v || "-") },
    { title: "类型", width: 80, render: (_, r) => typeTag(r.media_type, r.category) },
    {
      title: "绑定正则",
      dataIndex: "patterns",
      ellipsis: ELLIPSIS,
      render: (p: string[]) =>
        p.length ? ellipsisCell(p.join("  |  "), <span className="mono">{p.length} 条</span>) : <Text type="secondary">-</Text>,
    },
    {
      title: "忽略",
      render: (_, r) => {
        const s = ignoreSummary(r);
        return s ? <Text type="warning">{s}</Text> : <Text type="secondary">-</Text>;
      },
    },
    {
      title: "启用",
      width: 70,
      render: (_, r) => <Switch checked={r.enabled} onChange={(e) => toggle(r, e)} />,
    },
    {
      title: "操作",
      width: 130,
      render: (_, r) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="删除该规则？" onConfirm={() => remove(r)}>
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Paragraph type="secondary">
        每条规则把命中正则的文件直接钉到一个 TMDB 条目（跳过按标题搜索），并可忽略其某些季/集。
        正则用命名组取季集：<Text code>{"(?P<season>\\d+) (?P<episode>\\d+)"}</Text>；未命中任何规则的文件由内置 guessit 解析。
      </Paragraph>

      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>添加规则</Button>
      </Space>

      <Table rowKey="id" size="middle" columns={columns} dataSource={rules} pagination={false} />

      <Modal
        title={editing ? "编辑 TMDB 规则" : "添加 TMDB 规则"}
        open={adding}
        onOk={onSubmit}
        onCancel={() => setAdding(false)}
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="media_type" label="类型">
            <Radio.Group>
              <Radio.Button value="movie">电影</Radio.Button>
              <Radio.Button value="episode">剧集</Radio.Button>
            </Radio.Group>
          </Form.Item>
          {isEpisode && (
            <Form.Item name="category" label="分类">
              <Radio.Group>
                <Radio.Button value="tv">普通剧集</Radio.Button>
                <Radio.Button value="anime">动漫</Radio.Button>
              </Radio.Group>
            </Form.Item>
          )}
          <Space align="end">
            <Form.Item name="tmdb_id" label="TMDB ID" rules={[{ required: true, message: "必填" }]}>
              <InputNumber style={{ width: 160 }} min={1} placeholder="如 207468" />
            </Form.Item>
            <Form.Item label=" ">
              <Button onClick={doPreview}>按 ID 预览</Button>
            </Form.Item>
            <Form.Item name="title" label="标题（显示用）" style={{ flex: 1 }}>
              <Input placeholder="预览后自动填" />
            </Form.Item>
          </Space>
          {preview && <Paragraph type="secondary" className="mono">{preview}</Paragraph>}

          <Form.Item label="绑定正则（命名组取季集；命中任一即绑定）">
            <Form.List name="patterns">
              {(fields, { add, remove: rm }) => (
                <>
                  {fields.map((f) => (
                    <Space key={f.key} style={{ display: "flex", marginBottom: 8 }} align="baseline">
                      <Form.Item {...f} noStyle>
                        <Input className="mono" style={{ width: 420 }} placeholder={"\\[(?P<episode>\\d+)\\]"} />
                      </Form.Item>
                      <MinusCircleOutlined onClick={() => rm(f.name)} />
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add("")} icon={<PlusOutlined />}>加一条正则</Button>
                </>
              )}
            </Form.List>
          </Form.Item>

          {isEpisode && (
            <>
              <Form.Item name="season" label="固定季号（留空则用正则的 season 组）">
                <InputNumber min={0} />
              </Form.Item>
              <Form.Item name="ignore_seasons" label="忽略整季（季号）">
                <Select mode="tags" tokenSeparators={[","]} placeholder="如 0（specials）" />
              </Form.Item>
              <Form.Item label="忽略具体集（按季）">
                <Form.List name="ignore_episodes">
                  {(fields, { add, remove: rm }) => (
                    <>
                      {fields.map((f) => (
                        <Space key={f.key} style={{ display: "flex", marginBottom: 8 }} align="baseline">
                          <Form.Item {...f} name={[f.name, "season"]} noStyle rules={[{ required: true, message: "季" }]}>
                            <InputNumber min={0} placeholder="季" style={{ width: 80 }} />
                          </Form.Item>
                          <Form.Item {...f} name={[f.name, "episodes"]} noStyle>
                            <Select mode="tags" tokenSeparators={[","]} style={{ width: 300 }} placeholder="集号，如 13,14" />
                          </Form.Item>
                          <MinusCircleOutlined onClick={() => rm(f.name)} />
                        </Space>
                      ))}
                      <Button type="dashed" onClick={() => add({ season: undefined, episodes: [] })} icon={<PlusOutlined />}>加一季</Button>
                    </>
                  )}
                </Form.List>
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </>
  );
}
