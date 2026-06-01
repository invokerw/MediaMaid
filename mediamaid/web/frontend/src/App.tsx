import { useState } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Typography } from "antd";
import {
  DashboardOutlined,
  UnorderedListOutlined,
  ApiOutlined,
  SettingOutlined,
  CloudDownloadOutlined,
  FolderOpenOutlined,
  FilterOutlined,
} from "@ant-design/icons";
import Dashboard from "./pages/Dashboard";
import Records from "./pages/Records";
import Plugins from "./pages/Plugins";
import Config from "./pages/Config";
import Subscriptions from "./pages/Subscriptions";
import Files from "./pages/Files";
import Parsers from "./pages/Parsers";

const { Header, Content, Sider } = Layout;

const items = [
  { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/subscriptions", icon: <CloudDownloadOutlined />, label: "订阅" },
  { key: "/files", icon: <FolderOpenOutlined />, label: "文件" },
  { key: "/parsers", icon: <FilterOutlined />, label: "解析器" },
  { key: "/records", icon: <UnorderedListOutlined />, label: "记录" },
  { key: "/plugins", icon: <ApiOutlined />, label: "插件" },
  { key: "/config", icon: <SettingOutlined />, label: "配置" },
];

const TITLES: Record<string, string> = {
  "/": "仪表盘",
  "/subscriptions": "订阅资源",
  "/files": "文件管理",
  "/parsers": "解析器",
  "/records": "处理记录",
  "/plugins": "插件",
  "/config": "配置",
};

export default function App() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} theme="dark">
        <div className="logo">{collapsed ? "🎬" : "🎬 MediaMaid"}</div>
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[pathname]}
          items={items}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ paddingInline: 24, display: "flex", alignItems: "center" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {TITLES[pathname] ?? "MediaMaid"}
          </Typography.Title>
        </Header>
        <Content style={{ padding: 24 }}>
          <div style={{ maxWidth: 1320, margin: "0 auto" }}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/subscriptions" element={<Subscriptions />} />
              <Route path="/files" element={<Files />} />
              <Route path="/parsers" element={<Parsers />} />
              <Route path="/records" element={<Records />} />
              <Route path="/plugins" element={<Plugins />} />
              <Route path="/config" element={<Config />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
