import { useState } from "react";
import { Plus, Info } from "lucide-react";
import type { Bootstrap } from "./types";
import { ModelExplorer } from "./ModelExplorer";
import { ChannelModels } from "./ChannelModels";
import { ConnectionDialog } from "./ConnectionDialog";

export function Models({
  connectionCompleted,
  data,
  favorites,
  toggleFavorite,
  refresh,
  value,
  change,
  workspaceId,
  effortChanged,
  editStateChanged,
}: {
  connectionCompleted: () => void;
  data: Bootstrap;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  refresh: () => void;
  value: string;
  change: (id: string) => void;
  workspaceId: string;
  effortChanged: (id: string) => void;
  editStateChanged: (state: {dirty: boolean; busy: boolean}) => void;
}) {
  const [manage, setManage] = useState(false);
  const [add, setAdd] = useState(false);
  const [firstConnection, setFirstConnection] = useState(false);
  const [selected, setSelected] = useState(
    value || data.presets.find((p) => p.available)?.id || "",
  );
  const active = data.presets.find((p) => p.id === value);
  function select(id: string) {
    setSelected(id);
    // Unavailable models can still be inspected, but cannot replace a usable
    // new-task selection. Saved new connections may arrive before catalog refresh.
    if (data.presets.find((p) => p.id === id)?.available !== false) change(id);
  }
  if (manage)
    return (
      <div className="settings-page">
        <ChannelModels
          initialProvider={active?.providerId || ""}
          back={() => setManage(false)}
          saved={refresh}
          editStateChanged={editStateChanged}
          onCreateChannel={() => { setManage(false); setFirstConnection(false); setAdd(true); }}
        />
      </div>
    );
  return (
    <div className="settings-page model-library">
      <div className="page-heading">
        <div>
          <h2>模型与通道</h2>
          <p>选择可用通道即用于新会话。已有会话仍使用原通道。</p>
        </div>
        <div className="model-library-actions">
          {data.capabilities.modelSettings && (
            <button className="button" onClick={() => setManage(true)}>
              管理通道模型
            </button>
          )}
          <button data-guide="connect" className="button" onClick={() => { setFirstConnection(!data.presets.some(p => p.available)); setAdd(true); }}>
            {data.capabilities.configure ? (
              <Plus size={16} />
            ) : (
              <Info size={16} />
            )}
            {data.capabilities.configure ? "连接服务" : "配置来源"}
          </button>
        </div>
      </div>
      <p className="model-library-count" role="status">
        {data.services.length} 个模型服务
        {active && (
          <>
            {" "}
            · 新会话使用：{active.name} / {active.channel || active.providerId}
          </>
        )}
      </p>
      {data.presets.length ? (
        <ModelExplorer
          presets={data.presets}
          models={data.models}
          workspaceId={workspaceId}
          value={selected}
          change={select}
          effortChanged={effortChanged}
          favorites={favorites}
          toggleFavorite={toggleFavorite}
        />
      ) : (
        <div className="model-library-empty">
          <h3>
            {data.services.length ? "还没有可启动的模型" : "连接第一个模型服务"}
          </h3>
          <p>
            {data.services.length
              ? "通道已存在，请检查模型目录是否已更新，以及所需的连接信息是否完整。"
              : "填入 API 地址和 Key，选择常用模型，就可以开始对话。"}
          </p>
        </div>
      )}
      {add && (
        <ConnectionDialog
          data={data}
          onboarding={firstConnection}
          complete={firstConnection ? connectionCompleted : undefined}
          select={select}
          close={() => setAdd(false)}
          refresh={refresh}
        />
      )}
    </div>
  );
}
