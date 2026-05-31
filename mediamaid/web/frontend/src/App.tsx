import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu } from "antd";
import {
  DashboardOutlined,
  UnorderedListOutlined,
  ApiOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import Dashboard from "./pages/Dashboard";
import Records from "./pages/Records";
import Plugins from "./pages/Plugins";
import Config from "./pages/Config";

const { Header, Content } = Layout;

const items = [
  { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/records", icon: <UnorderedListOutlined />, label: "记录" },
  { key: "/plugins", icon: <ApiOutlined />, label: "插件" },
  { key: "/config", icon: <SettingOutlined />, label: "配置" },
];

export default function App() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", paddingInline: 24 }}>
        <div className="brand">🎬 MediaMaid</div>
        <Menu
          mode="horizontal"
          theme="dark"
          selectedKeys={[pathname]}
          items={items}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, minWidth: 0, marginLeft: 32 }}
        />
      </Header>
      <Content style={{ padding: "28px", maxWidth: 1040, width: "100%", margin: "0 auto" }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/records" element={<Records />} />
          <Route path="/plugins" element={<Plugins />} />
          <Route path="/config" element={<Config />} />
        </Routes>
      </Content>
    </Layout>
  );
}
