import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import { ThemeContext } from "./themeContext";
import "./styles.css";

function Root() {
  const [dark, setDark] = useState(() => localStorage.getItem("mm_theme") !== "light");
  const toggle = () =>
    setDark((d) => {
      const next = !d;
      localStorage.setItem("mm_theme", next ? "dark" : "light");
      return next;
    });

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: { colorPrimary: "#4ea1ff", borderRadius: 8 },
      }}
    >
      <ThemeContext.Provider value={{ dark, toggle }}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ThemeContext.Provider>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
