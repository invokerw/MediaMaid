import { useEffect, useState } from "react";
import { Card, Typography, message } from "antd";
import { api } from "../api";

const { Paragraph } = Typography;

export default function Config() {
  const [data, setData] = useState<{ path: string; text: string } | null>(null);

  useEffect(() => {
    api
      .config()
      .then(setData)
      .catch((e) => message.error(String(e)));
  }, []);

  return (
    <>
      <Paragraph type="secondary" className="mono">
        {data?.path} · 只读视图，修改请编辑该文件后重启
      </Paragraph>
      <Card size="small">
        <Paragraph className="result mono" style={{ marginBottom: 0 }}>
          {data?.text ?? "加载中…"}
        </Paragraph>
      </Card>
    </>
  );
}
