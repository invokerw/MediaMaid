import { Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { RecordRow } from "../api";

const STATUS_COLOR: Record<string, string> = {
  done: "success",
  skipped: "warning",
  failed: "error",
};

const columns: ColumnsType<RecordRow> = [
  { title: "ID", dataIndex: "id", width: 64 },
  {
    title: "状态",
    dataIndex: "status",
    width: 100,
    render: (s: string) => <Tag color={STATUS_COLOR[s] || "default"}>{s}</Tag>,
  },
  { title: "动作", dataIndex: "action", width: 100, render: (a) => a || "-" },
  { title: "源文件", dataIndex: "src_name", ellipsis: true },
  {
    title: "目标",
    dataIndex: "dst_name",
    ellipsis: true,
    render: (d) => d || "-",
  },
];

export default function RecordsTable({
  records,
  loading,
}: {
  records: RecordRow[];
  loading?: boolean;
}) {
  return (
    <Table
      rowKey="id"
      size="middle"
      columns={columns}
      dataSource={records}
      loading={loading}
      pagination={records.length > 20 ? { pageSize: 20 } : false}
    />
  );
}
