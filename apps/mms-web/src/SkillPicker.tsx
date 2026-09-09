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
}
export function SkillPicker({
  skills,
  selected,
  toggle,
  close,
  error,
  locked = false,
}: {
  skills: Skill[];
  selected: string[];
  toggle: (id: string) => void;
  close: () => void;
  error?: string;
  locked?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [onlySelected, setOnlySelected] = useState(false);
  const shown = skills.filter(
    (s) =>
      (!onlySelected || selected.includes(s.id)) &&
      `${s.name} ${s.description}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <Dialog title="为这次任务添加 skills" close={close}>
      <p className="dialog-intro">
        按需选择，发送时带入指引。其他已安装 skills 仍可由模型按任务发现。
      </p>
      <div className="explorer-search">
        <label className="picker-search">
          <Search size={17} />
          <input
            autoFocus
            aria-label="搜索 skills"
            placeholder="搜索名字或用途，例如：设计、审查…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button
          type="button"
          className={"filter-button " + (onlySelected ? "active" : "")}
          onClick={() => setOnlySelected(!onlySelected)}
        >
          已选 {selected.length}
        </button>
      </div>
      {error && (
        <p role="alert" className="inline-alert">
          {error}
        </p>
      )}
      <div className="skill-results">
        {shown.map((s) => (
          <button
            type="button"
            key={s.id}
            className={
              "skill-option " + (selected.includes(s.id) ? "selected" : "")
            }
            onClick={() => toggle(s.id)}
            aria-pressed={selected.includes(s.id)}
            disabled={locked || (selected.length >= 20 && !selected.includes(s.id))}
          >
            <span className="skill-icon">
              {selected.includes(s.id) ? (
                <Check size={18} />
              ) : (
                <BookOpen size={18} />
              )}
            </span>
            <span>
              <strong>
                {s.name}
                <small>
                  {s.source}
                  {s.manualOnly ? " · 手动调用" : ""}
                </small>
              </strong>
              <p>{s.description}</p>
            </span>
          </button>
        ))}
        {!shown.length && (
          <p className="empty-results">
            {skills.length
              ? "没有匹配的 skills。"
              : "当前 workspace 暂无可用 skills。"}
          </p>
        )}
      </div>
      <div className="skill-footer">
        <small>{skills.length} 个可用 · 每次最多选择 20 个</small>
        <button type="button" className="button primary" onClick={close}>
          完成{selected.length ? ` · ${selected.length} 个` : ""}
        </button>
      </div>
    </Dialog>
  );
}
