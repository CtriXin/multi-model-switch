import { useState } from "react";
import { Sun, Moon, SlidersHorizontal, Palette, ArrowLeft } from "lucide-react";
import type { Bootstrap } from "./types";
import { Models } from "./Models";

export function SettingsPage({
  data,
  favorites,
  toggleFavorite,
  refresh,
  theme,
  setTheme,
  accent,
  setAccent,
  back,
  presetId,
  selectPreset,
  workspaceId,
  effortChanged,
  autoCollapseProcess, setAutoCollapseProcess,
  fontFamily, setFontFamily,
  cjkFont, setCjkFont,
  fontSize, setFontSize,
  boldText, setBoldText,
  selectToCopy, setSelectToCopy,
  requestNavigation, editStateChanged,
}: {
  data: Bootstrap;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  refresh: () => void;
  theme: "light" | "dark";
  setTheme: (value: "light" | "dark") => void;
  accent: string;
  setAccent: (value: string) => void;
  back: () => void;
  presetId: string;
  selectPreset: (id: string) => void;
  workspaceId: string;
  effortChanged: (id: string) => void;
  requestNavigation: (action: () => void) => void;
  editStateChanged: (state: {dirty: boolean; busy: boolean}) => void;
  autoCollapseProcess: boolean;
  setAutoCollapseProcess: (on: boolean) => void;
  fontFamily: string;
  setFontFamily: (value: string) => void;
  cjkFont: string;
  setCjkFont: (value: string) => void;
  fontSize: number;
  setFontSize: (value: number) => void;
  boldText: boolean;
  setBoldText: (on: boolean) => void;
  selectToCopy: boolean;
  setSelectToCopy: (on: boolean) => void;
}) {
  const [tab, setTab] = useState("models");
  return (
    <div className="settings-shell">
      <header className="settings-heading">
        <button
          className="icon-button"
          aria-label="返回工作空间"
          onClick={back}
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1>设置</h1>
          <p>常用偏好，放在一起。</p>
        </div>
      </header>
      <nav className="settings-tabs" aria-label="设置分类">
        <button
          className={tab === "models" ? "active" : ""}
          onClick={() => requestNavigation(() => setTab("models"))}
        >
          <SlidersHorizontal size={16} />
          模型与通道
        </button>
        <button
          className={tab === "general" ? "active" : ""}
          onClick={() => requestNavigation(() => setTab("general"))}
        >
          <Palette size={16} />
          外观与使用
        </button>
      </nav>
      {tab === "models" ? (
        <Models
          data={data}
          favorites={favorites}
          toggleFavorite={toggleFavorite}
          refresh={refresh}
          value={presetId}
          change={selectPreset}
          workspaceId={workspaceId}
          effortChanged={effortChanged}
          editStateChanged={editStateChanged}
        />
      ) : (
        <section className="general-settings">
          <label className="preference-row">
            <div><h2>完成后自动收起过程</h2><p>保留最终回答，收起 thinking、工具记录与中间说明。每轮都可以手动展开。</p></div>
            <input type="checkbox" role="switch" aria-label="完成后自动收起过程" checked={autoCollapseProcess} onChange={e => setAutoCollapseProcess(e.target.checked)} />
          </label>
          <div className="preference-row">
            <div>
              <h2>外观</h2>
              <p>保存在当前浏览器，随时可以更换。</p>
            </div>
            <div className="appearance-options">
              <button
                aria-pressed={theme === "light"}
                onClick={() => setTheme("light")}
              >
                <Sun size={16} />
                浅色
              </button>
              <button
                aria-pressed={theme === "dark"}
                onClick={() => setTheme("dark")}
              >
                <Moon size={16} />
                深色
              </button>
            </div>
          </div>
          <label className="preference-row">
            <div>
              <h2>选择即复制</h2>
              <p>选中对话里的文字后自动复制。会覆盖剪贴板里原有的内容；输入框中的选择不受影响。默认关闭。</p>
            </div>
            <input
              type="checkbox"
              role="switch"
              aria-label="选择即复制"
              checked={selectToCopy}
              onChange={(e) => setSelectToCopy(e.target.checked)}
            />
          </label>
          <div className="preference-row">
            <div>
              <h2>字体</h2>
              <p>影响整个页面，保存在当前浏览器。</p>
            </div>
            <div className="font-options">
              <label>
                <span>字体</span>
                <select
                  aria-label="界面字体"
                  value={fontFamily}
                  onChange={(e) => setFontFamily(e.target.value)}
                >
                  <option value="system">跟随系统</option>
                  <option value="sans">无衬线</option>
                  <option value="serif">衬线</option>
                  <option value="mono">等宽</option>
                </select>
              </label>
              <label>
                <span>中文字体兜底</span>
                <select
                  aria-label="中文字体兜底"
                  value={cjkFont}
                  onChange={(e) => setCjkFont(e.target.value)}
                >
                  <option value="system">跟随系统</option>
                  <option value="pingfang">苹方</option>
                  <option value="noto">思源黑体</option>
                  <option value="yahei">微软雅黑</option>
                </select>
              </label>
              <label>
                <span>字体大小</span>
                <input
                  type="range"
                  min={12}
                  max={20}
                  step={1}
                  aria-label="字体大小"
                  value={fontSize}
                  onChange={(e) => setFontSize(Number(e.target.value))}
                />
                <output>{fontSize} px</output>
              </label>
              <label>
                <span>加粗正文</span>
                <input
                  type="checkbox"
                  role="switch"
                  aria-label="加粗正文"
                  checked={boldText}
                  onChange={(e) => setBoldText(e.target.checked)}
                />
              </label>
            </div>
          </div>
          <div className="preference-row">
            <div>
              <h2>强调色</h2>
              <p>用于选中、按钮和运行提示，页面底色保持安静。</p>
            </div>
            <div className="accent-options" role="group" aria-label="强调色">
              {[
                ["indigo", "靛蓝"],
                ["blue", "海蓝"],
                ["rose", "玫瑰"],
                ["orange", "琥珀"],
              ].map(([id, name]) => (
                <button
                  key={id}
                  data-accent={id}
                  aria-pressed={accent === id}
                  onClick={() => setAccent(id)}
                >
                  <i aria-hidden="true" />
                  {name}
                </button>
              ))}
            </div>
          </div>
          <div className="preference-row">
            <div>
              <h2>输入与快捷操作</h2>
              <p>Enter 发送，Shift + Enter 换行。截图可粘贴；本地文件可粘贴完整路径。</p>
              <p>输入 / 选择命令，@ 引用文件，⌘ K 搜索会话。</p>
              <p>
                未发送草稿在此浏览器保留 7
                天，成功发送后清除。本地文件引用保留原路径，截图保存在本机服务中。
              </p>
            </div>
          </div>
          <div className="preference-row">
            <div>
              <h2>工作文件夹</h2>
              <p>会话在选定文件夹中读写资料，位置在输入框上方显示。</p>
            </div>
          </div>
          <div className="preference-row">
            <div>
              <h2>配置来源</h2>
              <p>
                {data.capabilities.configure
                  ? "当前使用 Web 独立配置，可在模型与通道中连接服务。"
                  : "当前读取已有 MMF 配置。收藏、通道备注与 Web 默认值保存于此浏览器。"}
              </p>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
