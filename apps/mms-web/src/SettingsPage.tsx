import { useState } from "react";
import { Sun, Moon, Monitor, Minus, Plus, SlidersHorizontal, Palette } from "lucide-react";
import type { Bootstrap } from "./types";
import { Models } from "./Models";
import { FONT_FAMILIES } from "./App";
import { Dialog } from "./components";

export function SettingsPage({
  data,
  favorites,
  toggleFavorite,
  refresh,
  themeChoice,
  setThemeChoice,
  accent,
  setAccent,
  back,
  presetId,
  selectPreset,
  workspaceId,
  effortChanged,
  autoCollapseProcess, setAutoCollapseProcess,
  fontFamily, setFontFamily,
  monoFont, setMonoFont,
  cjkFont, setCjkFont,
  installedFonts,
  fontSize, setFontSize,
  boldText, setBoldText,
  selectToCopy, setSelectToCopy,
  requestNavigation, editStateChanged,
}: {
  data: Bootstrap;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  refresh: () => void;
  themeChoice: "light" | "dark" | "system";
  setThemeChoice: (value: "light" | "dark" | "system") => void;
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
  monoFont: string;
  setMonoFont: (value: string) => void;
  cjkFont: string;
  setCjkFont: (value: string) => void;
  installedFonts: Record<string, boolean>;
  fontSize: number;
  setFontSize: (value: number) => void;
  boldText: boolean;
  setBoldText: (on: boolean) => void;
  selectToCopy: boolean;
  setSelectToCopy: (on: boolean) => void;
}) {
  const [tab, setTab] = useState("models");
  return (
    <Dialog title="设置" size="sheet" close={() => requestNavigation(back)}>
    <div className="settings-shell">
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
              {(
                [
                  ["system", "跟随系统", Monitor],
                  ["light", "浅色", Sun],
                  ["dark", "深色", Moon],
                ] as const
              ).map(([id, label, Icon]) => (
                <button
                  key={id}
                  aria-pressed={themeChoice === id}
                  onClick={() => setThemeChoice(id)}
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
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
              <h2>界面字体</h2>
              <p>影响整个页面。只列出这台电脑装了的字体。</p>
            </div>
            <select
              aria-label="界面字体"
              value={fontFamily}
              onChange={(e) => setFontFamily(e.target.value)}
            >
              <option value="system">跟随系统</option>
              <option value="system_ui">System UI</option>
              {Object.entries(FONT_FAMILIES)
                .filter(([key, f]) => !f.cjk && installedFonts[key])
                .map(([key, f]) => (
                  <option key={key} value={key}>
                    {f.label}
                  </option>
                ))}
            </select>
          </div>
          <div className="preference-row">
            <div>
              <h2>等宽字体</h2>
              <p>代码块与运行详情使用。</p>
            </div>
            <select
              aria-label="等宽字体"
              value={monoFont}
              onChange={(e) => setMonoFont(e.target.value)}
            >
              <option value="system">SF Mono</option>
              {Object.entries(FONT_FAMILIES)
                .filter(([key, f]) => f.mono && installedFonts[key])
                .map(([key, f]) => (
                  <option key={key} value={key}>
                    {f.label}
                  </option>
                ))}
            </select>
          </div>
          <div className="preference-row">
            <div>
              <h2>中文字体兜底</h2>
              <p>主字体缺中日韩字形时使用。</p>
            </div>
            <select
              aria-label="中文字体兜底"
              value={cjkFont}
              onChange={(e) => setCjkFont(e.target.value)}
            >
              <option value="system">跟随系统</option>
              {Object.entries(FONT_FAMILIES)
                .filter(([key, f]) => f.cjk && installedFonts[key])
                .map(([key, f]) => (
                  <option key={key} value={key}>
                    {f.label}
                  </option>
                ))}
            </select>
          </div>
          <div className="preference-row font-size-row">
            <div>
              <h2>字号</h2>
              <p>{fontSize} px，改动立即生效。</p>
            </div>
            <span className="stepper">
              <button
                type="button"
                aria-label="减小字号"
                disabled={fontSize <= 12}
                onClick={() => setFontSize(fontSize - 1)}
              >
                <Minus size={13} />
              </button>
              <output aria-live="polite">{fontSize}</output>
              <button
                type="button"
                aria-label="增大字号"
                disabled={fontSize >= 20}
                onClick={() => setFontSize(fontSize + 1)}
              >
                <Plus size={13} />
              </button>
            </span>
          </div>
          <label className="preference-row">
            <div>
              <h2>加粗正文</h2>
              <p>所有正文用字体的加粗切片渲染。</p>
            </div>
            <input
              type="checkbox"
              role="switch"
              aria-label="加粗正文"
              checked={boldText}
              onChange={(e) => setBoldText(e.target.checked)}
            />
          </label>
          <div className="preference-row">
            <div>
              <h2>强调色</h2>
              <p>用于选中、按钮和运行提示，页面底色保持安静。</p>
            </div>
            <div className="accent-options" role="group" aria-label="强调色">
              {[
                ["indigo", "靛蓝"],
                ["cyan", "青蓝"],
                ["pink", "品红"],
                ["orange", "琥珀"],
                ["green", "翠绿"],
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
    </Dialog>
  );
}
