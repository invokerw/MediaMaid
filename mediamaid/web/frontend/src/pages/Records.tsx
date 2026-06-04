import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Segmented, Space, Button, Popconfirm, Dropdown, message } from "antd";
import { DeleteOutlined, TagOutlined } from "@ant-design/icons";
import { api, RecordRow } from "../api";
import RecordsTable from "../components/RecordsTable";

const OPTIONS = [
  { label: "全部", value: "" },
  { label: "已整理", value: "done" },
  { label: "跳过", value: "skipped" },
  { label: "失败", value: "failed" },
];

const STATUS_ITEMS = [
  { key: "done", label: "标为 已整理 (done)" },
  { key: "skipped", label: "标为 跳过 (skipped)" },
  { key: "failed", label: "标为 失败 (failed)" },
];

export default function Records() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<number[]>([]);

  function load() {
    setLoading(true);
    api
      .records(status || undefined)
      .then((d) => setRecords(d.records))
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    setSelected([]);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function doDelete() {
    try {
      const r = await api.deleteRecords(selected);
      message.success(`已删除 ${r.deleted} 条`);
      setSelected([]);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  async function doSetStatus(s: string) {
    try {
      const r = await api.setRecordsStatus(selected, s);
      message.success(`已修改 ${r.updated} 条为 ${s}`);
      setSelected([]);
      load();
    } catch (e) {
      message.error(String(e));
    }
  }

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Segmented
          options={OPTIONS}
          value={status}
          onChange={(v) => setParams(v ? { status: String(v) } : {})}
        />
        <Dropdown
          menu={{ items: STATUS_ITEMS, onClick: ({ key }) => doSetStatus(key) }}
          disabled={!selected.length}
        >
          <Button icon={<TagOutlined />} disabled={!selected.length}>
            改状态
          </Button>
        </Dropdown>
        <Popconfirm
          title={`删除选中的 ${selected.length} 条记录？`}
          description="删除「已整理」记录会解除去重，该源文件下次扫描会被重新整理。"
          onConfirm={doDelete}
          disabled={!selected.length}
        >
          <Button danger icon={<DeleteOutlined />} disabled={!selected.length}>
            删除{selected.length ? ` (${selected.length})` : ""}
          </Button>
        </Popconfirm>
      </Space>
      <RecordsTable
        records={records}
        loading={loading}
        selectedRowKeys={selected}
        onSelectionChange={setSelected}
      />
    </>
  );
}
