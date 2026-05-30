import { useEffect, useState } from "react";
import { api, PluginCategory } from "../api";

export default function Plugins() {
  const [categories, setCategories] = useState<PluginCategory[]>([]);

  useEffect(() => {
    api.plugins().then((d) => setCategories(d.categories));
  }, []);

  return (
    <>
      <h1>插件</h1>
      <p className="hint">
        绿色为配置中已启用。新增插件只需在{" "}
        <code>mediamaid/plugins/&lt;类别&gt;/</code> 放一个文件并 <code>@register</code>。
      </p>
      {categories.map((cat) => (
        <div key={cat.category}>
          <h2>{cat.category}</h2>
          <div className="pills">
            {cat.entries.length === 0 ? (
              <span className="empty">（无）</span>
            ) : (
              cat.entries.map((e) => (
                <span key={e.name} className={`pill ${e.enabled ? "on" : ""}`}>
                  {e.name}
                </span>
              ))
            )}
          </div>
        </div>
      ))}
    </>
  );
}
