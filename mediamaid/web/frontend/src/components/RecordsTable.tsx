import { RecordRow } from "../api";

export default function RecordsTable({ records }: { records: RecordRow[] }) {
  return (
    <table className="grid">
      <thead>
        <tr>
          <th>ID</th>
          <th>状态</th>
          <th>动作</th>
          <th>源文件</th>
          <th>目标</th>
        </tr>
      </thead>
      <tbody>
        {records.length === 0 ? (
          <tr>
            <td colSpan={5} className="empty">
              暂无记录
            </td>
          </tr>
        ) : (
          records.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>
                <span className={`badge ${r.status}`}>{r.status}</span>
              </td>
              <td>{r.action || "-"}</td>
              <td className="mono">{r.src_name}</td>
              <td className="mono">{r.dst_name || "-"}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
