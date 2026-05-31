import { useEffect, useState } from "react";
import { Card, Switch, Button, Typography, Space, Drawer, Tag, List, message } from "antd";
import { SettingOutlined } from "@ant-design/icons";
import { api, PluginCategory, PluginEntry } from "../api";
import PluginForm from "../components/PluginForm";

const { Paragraph, Text } = Typography;

const CATEGORY_LABEL: Record<string, string> = {
  scraper: "刮削器",
  subscriber: "订阅器",
  downloader: "下载器",
  notifier: "通知器",
};

export default function Plugins() {
  const [categories, setCategories] = useState<PluginCategory[]>([]);
  const [drawer, setDrawer] = useState<{ category: string; entry: PluginEntry } | null>(null);

  const load = () =>
    api
      .plugins()
      .then((d) => setCategories(d.categories))
      .catch((e) => message.error(String(e)));

  useEffect(() => {
    load();
  }, []);

  // 更新本地某条插件状态
  function apply(category: string, updated: PluginEntry) {
    setCategories((cats) =>
      cats.map((c) =>
        c.category !== category
          ? c
          : { ...c, entries: c.entries.map((e) => (e.name === updated.name ? updated : e)) }
      )
    );
    if (drawer && drawer.category === category && drawer.entry.name === updated.name) {
      setDrawer({ category, entry: updated });
    }
  }

  async function toggle(category: string, entry: PluginEntry, enabled: boolean) {
    try {
      const updated = await api.updatePlugin(category, entry.name, {
        enabled,
        config: entry.config,
      });
      apply(category, updated);
      message.success(enabled ? `已启用 ${entry.name}` : `已停用 ${entry.name}`);
    } catch (e) {
      message.error(String(e));
    }
  }

  const hasParams = (e: PluginEntry) =>
    Object.keys(e.schema.properties ?? {}).length > 0;

  return (
    <>
      <Paragraph type="secondary">
        切换开关启停插件；点「配置」编辑参数。改动会写回 config.yaml 并即时生效。
      </Paragraph>
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        {categories.map((cat) => (
          <Card
            key={cat.category}
            size="small"
            title={`${CATEGORY_LABEL[cat.category] || cat.category} · ${cat.category}`}
          >
            <List
              dataSource={cat.entries}
              locale={{ emptyText: "（无）" }}
              renderItem={(e) => (
                <List.Item
                  actions={[
                    <Switch
                      key="sw"
                      checked={e.enabled}
                      onChange={(v) => toggle(cat.category, e, v)}
                    />,
                    <Button
                      key="cfg"
                      type="link"
                      icon={<SettingOutlined />}
                      disabled={!hasParams(e)}
                      onClick={() => setDrawer({ category: cat.category, entry: e })}
                    >
                      配置
                    </Button>,
                  ]}
                >
                  <Space>
                    <Text strong>{e.name}</Text>
                    {e.enabled && <Tag color="success">已启用</Tag>}
                    {!hasParams(e) && <Text type="secondary">无参数</Text>}
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        ))}
      </Space>

      <Drawer
        title={drawer ? `配置 ${drawer.category}/${drawer.entry.name}` : ""}
        width={420}
        open={!!drawer}
        onClose={() => setDrawer(null)}
        destroyOnClose
      >
        {drawer && (
          <PluginForm
            category={drawer.category}
            entry={drawer.entry}
            onSaved={(u) => apply(drawer.category, u)}
          />
        )}
      </Drawer>
    </>
  );
}
