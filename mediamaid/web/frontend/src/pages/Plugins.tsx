import { useEffect, useState } from "react";
import { Card, Switch, Button, Typography, Space, Modal, Tag, Empty, Row, Col, message } from "antd";
import { SettingOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { api, PluginCategory, PluginEntry } from "../api";
import PluginForm from "../components/PluginForm";

const { Paragraph, Text } = Typography;

const CATEGORY_LABEL: Record<string, string> = {
  scraper: "刮削器",
  subscriber: "订阅器",
  downloader: "下载器",
  notifier: "通知器",
  mediaserver: "媒体服务器",
};

export default function Plugins() {
  const [categories, setCategories] = useState<PluginCategory[]>([]);
  const [modal, setModal] = useState<{ category: string; entry: PluginEntry } | null>(null);

  const load = () =>
    api
      .plugins()
      // 订阅器改由「订阅」页管理，这里不展示
      .then((d) => setCategories(d.categories.filter((c) => c.category !== "subscriber")))
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
    if (modal && modal.category === category && modal.entry.name === updated.name) {
      setModal({ category, entry: updated });
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

  async function testPlugin(category: string, entry: PluginEntry) {
    message.loading({ content: `测试 ${entry.name}…`, key: "test" });
    try {
      const r = await api.testPlugin(category, entry.name, entry.config);
      if (r.ok) message.success({ content: r.message, key: "test" });
      else message.error({ content: r.message, key: "test" });
    } catch (e) {
      message.error({ content: String(e), key: "test" });
    }
  }

  const hasParams = (e: PluginEntry) =>
    Object.keys(e.schema.properties ?? {}).length > 0;

  return (
    <>
      <Paragraph type="secondary">
        切换开关启停插件；点「配置」编辑参数。改动会写回 config.yaml 并即时生效。
      </Paragraph>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        {categories.map((cat) => (
          <div key={cat.category}>
            <Typography.Title level={5} style={{ marginBottom: 12 }}>
              {CATEGORY_LABEL[cat.category] || cat.category}
              <Text type="secondary" style={{ fontWeight: 400, marginLeft: 8 }}>
                {cat.category}
              </Text>
            </Typography.Title>
            {cat.entries.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="（无）" />
            ) : (
              <Row gutter={[16, 16]}>
                {cat.entries.map((e) => (
                  <Col key={e.name} xs={24} sm={12} md={8} xl={6}>
                    <Card
                      size="small"
                      hoverable
                      title={
                        <Space>
                          <Text strong>{e.name}</Text>
                          {e.enabled && <Tag color="success">已启用</Tag>}
                        </Space>
                      }
                      extra={
                        <Switch
                          checked={e.enabled}
                          onChange={(v) => toggle(cat.category, e, v)}
                        />
                      }
                      actions={[
                        <Button
                          key="test"
                          type="text"
                          icon={<ThunderboltOutlined />}
                          onClick={() => testPlugin(cat.category, e)}
                        >
                          测试
                        </Button>,
                        <Button
                          key="cfg"
                          type="text"
                          icon={<SettingOutlined />}
                          disabled={!hasParams(e)}
                          onClick={() => setModal({ category: cat.category, entry: e })}
                        >
                          配置
                        </Button>,
                      ]}
                    >
                      <Text type="secondary">
                        {hasParams(e) ? `${Object.keys(e.schema.properties ?? {}).length} 项参数` : "无参数"}
                      </Text>
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </div>
        ))}
      </Space>

      <Modal
        title={modal ? `配置 ${modal.category}/${modal.entry.name}` : ""}
        open={!!modal}
        onCancel={() => setModal(null)}
        footer={null}
        destroyOnClose
        width={480}
      >
        {modal && (
          <PluginForm
            category={modal.category}
            entry={modal.entry}
            onSaved={(u) => apply(modal.category, u)}
          />
        )}
      </Modal>
    </>
  );
}
