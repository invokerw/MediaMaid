import { useEffect, useState } from "react";
import { api } from "../api";

export default function Config() {
  const [data, setData] = useState<{ path: string; text: string } | null>(null);

  useEffect(() => {
    api.config().then(setData);
  }, []);

  return (
    <>
      <h1>
        配置 <span className="hint mono">{data?.path}</span>
      </h1>
      <p className="hint">只读视图。修改请编辑该文件后重启。</p>
      <pre className="result mono">{data?.text ?? "加载中…"}</pre>
    </>
  );
}
