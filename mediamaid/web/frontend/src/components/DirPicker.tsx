import { useEffect, useState } from "react";
import { Modal, Input, Button, List, Space, Typography, message } from "antd";
import { FolderOutlined, ArrowUpOutlined } from "@ant-design/icons";
import { api } from "../api";

const { Text } = Typography;

export default function DirPicker({
  open,
  initial,
  onClose,
  onSelect,
}: {
  open: boolean;
  initial?: string;
  onClose: () => void;
  onSelect: (path: string) => void;
}) {
  const [path, setPath] = useState(initial || "");
  const [parent, setParent] = useState("");
  const [dirs, setDirs] = useState<{ name: string; path: string }[]>([]);
  const [loading, setLoading] = useState(false);

  function browse(p?: string) {
    setLoading(true);
    api
      .fsList(p)
      .then((d) => {
        setPath(d.path);
        setParent(d.parent);
        setDirs(d.dirs);
        if (d.error) message.warning(d.error);
      })
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (open) browse(initial || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Modal
      title="选择目录"
      open={open}
      onCancel={onClose}
      onOk={() => {
        onSelect(path);
        onClose();
      }}
      okText="选择此目录"
      width={560}
    >
      <Space.Compact style={{ width: "100%", marginBottom: 8 }}>
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onPressEnter={() => browse(path)}
        />
        <Button onClick={() => browse(path)}>前往</Button>
      </Space.Compact>
      <Button
        size="small"
        icon={<ArrowUpOutlined />}
        onClick={() => browse(parent)}
        style={{ marginBottom: 8 }}
        disabled={parent === path}
      >
        上级
      </Button>
      <List
        size="small"
        loading={loading}
        bordered
        style={{ maxHeight: 320, overflow: "auto" }}
        dataSource={dirs}
        locale={{ emptyText: "无子目录" }}
        renderItem={(d) => (
          <List.Item
            style={{ cursor: "pointer" }}
            onClick={() => browse(d.path)}
          >
            <Space>
              <FolderOutlined />
              {d.name}
            </Space>
          </List.Item>
        )}
      />
      <Text type="secondary" style={{ fontSize: 12 }}>
        当前：<span className="mono">{path}</span>
      </Text>
    </Modal>
  );
}
