import { useContext, useEffect, useState } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Typography, Space, Button, Spin, message, theme as antdTheme } from "antd";
import {
  DashboardOutlined,
  UnorderedListOutlined,
  ApiOutlined,
  SettingOutlined,
  CloudDownloadOutlined,
  DownloadOutlined,
  FolderOpenOutlined,
  FilterOutlined,
  FileTextOutlined,
  BulbOutlined,
  LogoutOutlined,
  UserOutlined,
} from "@ant-design/icons";
import Dashboard from "./pages/Dashboard";
import Records from "./pages/Records";
import Plugins from "./pages/Plugins";
import Config from "./pages/Config";
import Subscriptions from "./pages/Subscriptions";
import Downloads from "./pages/Downloads";
import Files from "./pages/Files";
import TmdbRules from "./pages/TmdbRules";
import Logs from "./pages/Logs";
import Login from "./pages/Login";
import { api, getToken, clearToken, setOnUnauthorized } from "./api";
import { ThemeContext } from "./themeContext";

const { Header, Content, Sider } = Layout;

const items = [
  { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/subscriptions", icon: <CloudDownloadOutlined />, label: "订阅" },
  { key: "/downloads", icon: <DownloadOutlined />, label: "下载" },
  { key: "/files", icon: <FolderOpenOutlined />, label: "文件" },
  { key: "/tmdb-rules", icon: <FilterOutlined />, label: "TMDB 规则" },
  { key: "/records", icon: <UnorderedListOutlined />, label: "记录" },
  { key: "/logs", icon: <FileTextOutlined />, label: "日志" },
  { key: "/plugins", icon: <ApiOutlined />, label: "插件" },
  { key: "/config", icon: <SettingOutlined />, label: "配置" },
];

const TITLES: Record<string, string> = {
  "/": "仪表盘",
  "/subscriptions": "订阅资源",
  "/downloads": "下载任务",
  "/files": "文件管理",
  "/tmdb-rules": "TMDB 规则",
  "/records": "处理记录",
  "/logs": "日志",
  "/plugins": "插件",
  "/config": "配置",
};

export default function App() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { dark, toggle } = useContext(ThemeContext);
  const { token } = antdTheme.useToken();

  // null=校验中，""=未登录，其它=用户名
  const [user, setUser] = useState<string | null>(null);

  useEffect(() => {
    setOnUnauthorized(() => setUser(""));
    if (!getToken()) {
      setUser("");
      return;
    }
    api
      .me()
      .then((r) => setUser(r.username))
      .catch(() => setUser(""));
  }, []);

  async function logout() {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    clearToken();
    setUser("");
    message.success("已退出");
  }

  if (user === null) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin size="large" />
      </div>
    );
  }
  if (user === "") {
    return <Login onSuccess={(u) => setUser(u)} />;
  }

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme={dark ? "dark" : "light"}
      >
        <div className="logo" style={{ color: token.colorText, background: token.colorFillTertiary }}>
          {collapsed ? "🎬" : "🎬 MediaMaid"}
        </div>
        <Menu
          mode="inline"
          theme={dark ? "dark" : "light"}
          selectedKeys={[pathname]}
          items={items}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            paddingInline: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            {TITLES[pathname] ?? "MediaMaid"}
          </Typography.Title>
          <Space size="middle">
            <Button
              type="text"
              icon={<BulbOutlined />}
              onClick={toggle}
              title={dark ? "切换浅色" : "切换深色"}
            >
              {dark ? "浅色" : "深色"}
            </Button>
            <Space size={4}>
              <UserOutlined />
              {user}
            </Space>
            <Button type="text" icon={<LogoutOutlined />} onClick={logout}>
              退出
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <div style={{ maxWidth: 1320, margin: "0 auto" }}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/subscriptions" element={<Subscriptions />} />
              <Route path="/downloads" element={<Downloads />} />
              <Route path="/files" element={<Files />} />
              <Route path="/tmdb-rules" element={<TmdbRules />} />
              <Route path="/records" element={<Records />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/plugins" element={<Plugins />} />
              <Route path="/config" element={<Config />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
