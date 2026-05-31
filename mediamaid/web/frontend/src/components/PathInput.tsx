import { useState } from "react";
import { Input, Button, Space } from "antd";
import { FolderOpenOutlined } from "@ant-design/icons";
import DirPicker from "./DirPicker";

// 受控组件，可直接用于 antd Form.Item（接收 value/onChange）。
export default function PathInput({
  value,
  onChange,
  placeholder,
}: {
  value?: string;
  onChange?: (v: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Space.Compact style={{ width: "100%" }}>
        <Input
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange?.(e.target.value)}
        />
        <Button icon={<FolderOpenOutlined />} onClick={() => setOpen(true)}>
          浏览
        </Button>
      </Space.Compact>
      <DirPicker
        open={open}
        initial={value}
        onClose={() => setOpen(false)}
        onSelect={(p) => onChange?.(p)}
      />
    </>
  );
}
