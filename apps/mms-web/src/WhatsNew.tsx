import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { isPreview, request } from "./api";

type Notes = { version?: string; notes?: string; upgradeNotice?: string };

/**
 * What changed in the version now running.
 *
 * The update dialog shows release notes *before* you confirm an upgrade. After
 * it completes the page reloads and, until now, said nothing about what moved.
 * Shown once per version: the stored version is the one already read, so an
 * install that never saw this panel records the current version silently
 * rather than greeting a first-time user with a changelog.
 */
export function WhatsNew({ ready }: { ready: boolean }) {
  const [notes, setNotes] = useState<Notes>();
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!ready || isPreview) return;
    let cancelled = false;
    void (async () => {
      try {
        const [status, prefs] = await Promise.all([
          request<{ whatsNew?: Notes }>("/update"),
          request<{ whatsNewSeenVersion?: string }>("/ui-preferences"),
        ]);
        const current = status.whatsNew?.version;
        if (cancelled || !current || !status.whatsNew?.notes) return;
        const seen = prefs.whatsNewSeenVersion || "";
        if (seen === current) return;
        if (!seen) {
          // First run of a build that records this at all: nothing to catch up on.
          void request("/ui-preferences", { whatsNewSeenVersion: current }).catch(() => {});
          return;
        }
        setNotes(status.whatsNew);
      } catch {
        // A changelog is never worth an error in front of the user.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready]);

  if (!notes?.notes) return null;
  const dismiss = () => {
    setNotes(undefined);
    void request("/ui-preferences", { whatsNewSeenVersion: notes.version }).catch(() => {});
  };
  return (
    <section className="whats-new" aria-label={`${notes.version} 更新内容`}>
      <div className="whats-new-head">
        <h3>已更新到 {notes.version}</h3>
        <button type="button" className="icon-button" onClick={dismiss} aria-label="知道了">
          <X size={15} />
        </button>
      </div>
      {notes.upgradeNotice && (
        <div className="update-warning">
          <h4>升级须知</h4>
          <div className="update-notes-body">
            <Markdown remarkPlugins={[remarkGfm]} skipHtml>
              {notes.upgradeNotice}
            </Markdown>
          </div>
        </div>
      )}
      {/* Collapsed by default: the notes are long enough to push the composer
          off the screen, and what an upgrade costs is already above. */}
      <button
        type="button"
        className="whats-new-toggle"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
      >
        {expanded ? "收起更新内容" : "查看更新内容"}
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {expanded && (
        <div className="update-notes-body whats-new-notes">
          <Markdown remarkPlugins={[remarkGfm]} skipHtml>
            {notes.notes}
          </Markdown>
        </div>
      )}
    </section>
  );
}
