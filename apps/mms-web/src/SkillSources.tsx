import { useEffect, useState } from "react";
import { request } from "./api";

export const SKILL_PREFERENCES_EVENT = "mms-skill-preferences-changed";

interface SkillPreferences { mergeExternal: boolean }

export function SkillSourcesSetting() {
  const [prefs, setPrefs] = useState<SkillPreferences | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    request<SkillPreferences>("/skill-preferences")
      .then(p => { if (!cancelled) setPrefs(p); })
      .catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);
  async function change(mergeExternal: boolean) {
    const previous = prefs;
    setPrefs({ mergeExternal });
    setError("");
    try {
      const saved = await request<SkillPreferences>("/skill-preferences", { mergeExternal });
      setPrefs(saved);
      window.dispatchEvent(new Event(SKILL_PREFERENCES_EVENT));
    } catch (e) {
      setPrefs(previous);
      setError((e as Error).message);
    }
  }
  return (
    <label className="preference-row">
      <div>
        <h2>合并本机 Claude / Codex / OpenCode Skills</h2>
        <p>打开后，Pilot 读取 skills 时会一并查看 ~/.claude/skills、~/.codex/skills 和 ~/.config/opencode/skills。只在 Pilot 的隔离读取层合并，不复制、删除或改写原目录；同名时项目和共享 skills 优先。</p>
        {error && <p role="alert" className="inline-alert">{error}</p>}
      </div>
      <input type="checkbox" role="switch" aria-label="合并本机 Claude / Codex / OpenCode Skills"
        checked={prefs?.mergeExternal === true} disabled={!prefs} onChange={e => change(e.target.checked)} />
    </label>
  );
}
