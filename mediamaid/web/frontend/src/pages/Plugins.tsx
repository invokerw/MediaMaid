import { useEffect, useState } from "react";
import { Card, Tag, Typography, Space, message } from "antd";
import { api, PluginCategory } from "../api";

const { Paragraph, Text } = Typography;

const CATEGORY_LABEL: Record<string, string> = {
  scraper: "刮削器",
  subscriber: "订阅器",
  downloader: "下载器",
  notifier: "通知器",
};

export default function Plugins() {
  const [categories, setCategories] = useState<PluginCategory[]>([]);

  useEffect(() => {
    api
      .plugins()
      .then((d) => setCategories(d.categories))
      .catch((e) => message.error(String(e)));
  }, []);

  return (
    <>
      <Paragraph type="secondary">
        绿色为配置中已启用。新增插件只需在{" "}
        <Text code>mediamaid/plugins/&lt;类别&gt;/</Text> 放一个文件并{" "}
        <Text code>@register</Text>。
      </Paragraph>
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        {categories.map((cat) => (
          <Card
            key={cat.category}
            size="small"
            title={`${CATEGORY_LABEL[cat.category] || cat.category} · ${cat.category}`}
          >
            {cat.entries.length === 0 ? (
              <Text type="secondary">（无）</Text>
            ) : (
              <Space wrap>
                {cat.entries.map((e) => (
                  <Tag key={e.name} color={e.enabled ? "success" : "default"}>
                    {e.name}
                    {e.enabled ? " ✓" : ""}
                  </Tag>
                ))}
              </Space>
            )}
          </Card>
        ))}
      </Space>
    </>
  );
}
