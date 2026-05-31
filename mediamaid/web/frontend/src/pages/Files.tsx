import { useEffect, useState } from "react";
import {
  Table,
  Button,
  Space,
  Select,
  Modal,
  Input,
  Popconfirm,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  FolderFilled,
  FileOutlined,
  ArrowUpOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { api } from "../api";

const { Text } = Typography;

interface Entry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: number;
}

function fmtSize(n: number, isDir: boolean): string {
  if (isDir) return "-";
  if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(2) + " GB";
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}

export default function Files() {
  const [roots, setRoots] = useState<{ label: string; path: string }[]>([]);
  const [root, setRoot] = useState<string>("");
  const [path, setPath] = useState<string>("");
  const [parent, setParent] = useState<string>("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(false);
  const [rename, setRename] = useState<{ entry: Entry; name: string } | null>(null);

  useEffect(() => {
    api.filesRoots().then((d) => {
      setRoots(d.roots);
      if (d.roots[0]) {
        setRoot(d.roots[0].path);
        browse(d.roots[0].path);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function browse(p: string) {
    setLoading(true);
    api
      .filesList(p)
      .then((d) => {
        setPath(d.path);
        setParent(d.parent);
        setEntries(d.entries);
      })
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }

  // 不允许越过当前根的上级
  const canUp = path !== root && path.startsWith(root);

  async function doDelete(e: Entry) {
    try {
      await api.filesDelete(e.path);
      message.success(`已删除 ${e.name}`);
      browse(path);
    } catch (err) {
      message.error(String(err));
    }
  }

  async function doRename() {
    if (!rename) return;
    try {
      await api.filesRename(rename.entry.path, rename.name);
      message.success("已重命名");
      setRename(null);
      browse(path);
    } catch (err) {
      message.error(String(err));
    }
  }

  const columns: ColumnsType<Entry> = [
    {
      title: "名称",
      dataIndex: "name",
      render: (name, e) =>
        e.is_dir ? (
          <a onClick={() => browse(e.path)}>
            <Space>
              <FolderFilled style={{ color: "#e0b341" }} />
              {name}
            </Space>
          </a>
        ) : (
          <Space>
            <FileOutlined />
            {name}
          </Space>
        ),
    },
    {
      title: "类型",
      dataIndex: "is_dir",
      width: 80,
      render: (d) => (d ? <Tag>目录</Tag> : <Tag color="blue">文件</Tag>),
    },
    { title: "大小", dataIndex: "size", width: 110, render: (n, e) => fmtSize(n, e.is_dir) },
    {
      title: "修改时间",
      dataIndex: "mtime",
      width: 180,
      render: (t: number) => new Date(t * 1000).toLocaleString(),
    },
    {
      title: "操作",
      width: 150,
      render: (_, e) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => setRename({ entry: e, name: e.name })}
          >
            重命名
          </Button>
          <Popconfirm
            title={`删除「${e.name}」？${e.is_dir ? "（含其中全部内容）" : ""}`}
            onConfirm={() => doDelete(e)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          style={{ minWidth: 280 }}
          value={root}
          options={roots.map((r) => ({ value: r.path, label: r.label }))}
          onChange={(v) => {
            setRoot(v);
            browse(v);
          }}
        />
        <Button
          icon={<ArrowUpOutlined />}
          disabled={!canUp}
          onClick={() => browse(parent)}
        >
          上级
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => browse(path)}>
          刷新
        </Button>
      </Space>
      <div style={{ marginBottom: 8 }}>
        <Text type="secondary" className="mono">
          {path}
        </Text>
      </div>

      <Table
        rowKey="path"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={entries}
        pagination={entries.length > 50 ? { pageSize: 50 } : false}
      />

      <Modal
        title="重命名"
        open={!!rename}
        onOk={doRename}
        onCancel={() => setRename(null)}
        destroyOnClose
      >
        <Input
          value={rename?.name}
          onChange={(e) => rename && setRename({ ...rename, name: e.target.value })}
          onPressEnter={doRename}
        />
      </Modal>
    </>
  );
}
