import { useState } from "react";
import { Check, Search, BookOpen } from "lucide-react";
import { Dialog } from "./components";
export interface Skill {
  id: string;
  name: string;
  description: string;
  source: string;
  filePath?: string;
  manualOnly?: boolean;
  starter?: boolean;
  title?: string;
  example?: string;
}
export function SkillPicker({ skills, selected, toggle, close, error, example, locked = false }: {
  skills: Skill[];
  selected: string[];
  toggle: (id: string) => void;
  close: () => void;
  error?: string;
  locked?: boolean;
  example: (skill: Skill) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"starter" | "all" | "selected">("starter");
  const shown = skills.filter(s =>
    (query || filter === "all" || (filter === "selected" ? selected.includes(s.id) : s.starter)) &&
    `${s.title || ""} ${s.name} ${s.description}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <Dialog title="任务助手 · Skills" size="wide" close={close}>
      <p className="dialog-intro">Skills 是给 AI 的做事指引。先选你想做的事，再补充要求并发送；下面的内置能力无需安装。</p>
      <div className="explorer-search">
        <label className="picker-search">
          <Search size={17} />
          <input autoFocus aria-label="搜索 skills" placeholder="想做什么？例如保存进度、检查改动…"
            value={query} onChange={e => setQuery(e.target.value)} />
        </label>
      </div>
      <div className="skill-filters" aria-label="Skills 范围">
        {([["starter", "开箱即用"], ["all", "全部能力"], ["selected", `已选 ${selected.length}`]] as const).map(([value, label]) =>
          <button type="button" key={value} className={"filter-button " + (filter === value ? "active" : "")}
            aria-pressed={filter === value} onClick={() => { setFilter(value); setQuery(""); }}>{label}</button>)}
      </div>
      {error && <p role="alert" className="inline-alert">{error}</p>}
      <div className="skill-results">
        {shown.map(s => <div className="skill-result-row" key={s.id}>
          <button type="button" className={"skill-option " + (selected.includes(s.id) ? "selected" : "")}
            onClick={() => toggle(s.id)} aria-pressed={selected.includes(s.id)}
            disabled={locked || (selected.length >= 20 && !selected.includes(s.id))}>
            <span className="skill-icon">{selected.includes(s.id) ? <Check size={18} /> : <BookOpen size={18} />}</span>
            <span><strong>{s.title || s.name}<small>{selected.includes(s.id) ? "已选中" : "可用"} · {s.source}{s.starter ? " · 无需安装" : s.manualOnly ? " · 手动调用" : ""}</small></strong>
              <p>{s.description}</p></span>
          </button>
          {s.example && <button type="button" className="text-button skill-example"
            disabled={locked || (selected.length >= 20 && !selected.includes(s.id))} onClick={() => example(s)}
            aria-label={`试试${s.title || s.name}`}>用示例填入草稿</button>}
        </div>)}
        {!shown.length && <p className="empty-results">{filter === "selected" && !query ? "还没有选择能力，也可以直接对话。" : "没有匹配的能力。可以换个说法，或直接在对话中描述需要的帮助。"}</p>}
      </div>
      <details className="skill-install-help">
        <summary>还想添加自己的 skill？</summary>
        <p>内置能力已随 Pilot 提供。已有的共享和项目 skills 在“全部能力”里，搜索也会一起查找。</p>
        <p>外部 skill 通常是一个包含 SKILL.md 的文件夹。先检查来源和内容，再放到工作文件夹的 .agents/skills 下，刷新页面即可读取。它只对这个项目生效；带有脚本的 skill 可能需要额外工具。</p>
        <p>已经装在本机 Claude、Codex 或 OpenCode 里的 skills，可以在设置的通用设置里打开「合并本机 Skills」，Pilot 会在隔离读取层一并查看，不会改动原目录。</p>
      </details>
      <div className="skill-footer">
        <small>选择后随这条消息提交，实际加载见运行详情 · 最多 20 个</small>
        <button type="button" className="button primary" onClick={close}>返回对话{selected.length ? ` · 已选 ${selected.length} 个` : ""}</button>
      </div>
    </Dialog>
  );
}
