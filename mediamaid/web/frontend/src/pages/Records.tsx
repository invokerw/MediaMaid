import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Segmented, Typography, message } from "antd";
import { api, RecordRow } from "../api";
import RecordsTable from "../components/RecordsTable";

const { Title } = Typography;

const OPTIONS = [
  { label: "全部", value: "" },
  { label: "已整理", value: "done" },
  { label: "跳过", value: "skipped" },
  { label: "失败", value: "failed" },
];

export default function Records() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .records(status || undefined)
      .then((d) => setRecords(d.records))
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }, [status]);

  return (
    <>
      <Title level={3}>处理记录</Title>
      <Segmented
        options={OPTIONS}
        value={status}
        onChange={(v) => setParams(v ? { status: String(v) } : {})}
        style={{ marginBottom: 16 }}
      />
      <RecordsTable records={records} loading={loading} />
    </>
  );
}
