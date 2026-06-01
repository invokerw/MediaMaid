import { Tooltip } from "antd";
import type { ReactNode } from "react";

// 列上配 `ellipsis: ELLIPSIS` 关闭原生 title，再用本组件 render，
// 即可：单行省略号保持整洁 + 鼠标悬浮显示全文（antd Tooltip）。
export const ELLIPSIS = { showTitle: false as const };

export function ellipsisCell(value: unknown, node?: ReactNode) {
  const text = value == null || value === "" ? "-" : String(value);
  return (
    <Tooltip title={text} placement="topLeft">
      <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {node ?? text}
      </span>
    </Tooltip>
  );
}
