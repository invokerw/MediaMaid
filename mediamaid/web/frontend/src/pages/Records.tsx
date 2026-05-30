import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, RecordRow } from "../api";
import RecordsTable from "../components/RecordsTable";

const FILTERS: [string, string][] = [
  ["", "全部"],
  ["done", "已整理"],
  ["skipped", "跳过"],
  ["failed", "失败"],
];

export default function Records() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const [records, setRecords] = useState<RecordRow[]>([]);

  useEffect(() => {
    api.records(status || undefined).then((d) => setRecords(d.records));
  }, [status]);

  return (
    <>
      <h1>处理记录</h1>
      <section className="filters">
        {FILTERS.map(([val, label]) => (
          <a
            key={val}
            className={status === val ? "on" : ""}
            onClick={() => setParams(val ? { status: val } : {})}
          >
            {label}
          </a>
        ))}
      </section>
      <RecordsTable records={records} />
    </>
  );
}
