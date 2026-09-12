/** What to do with the release notes for the version now running. */
export type WhatsNewAction = "show" | "record" | "skip";

/**
 * `show` opens the panel, `record` marks the version read without showing it,
 * `skip` does nothing.
 *
 * An install that has never been used is stamped by the server on its first
 * read, so an empty recorded version here means a real upgrade into the first
 * build that records one: the user is owed the notes. Deciding that in the
 * browser would race the guided tour, which writes the same file on first run.
 */
export function decideWhatsNew(input: {
  version?: string;
  notes?: string;
  seenVersion?: string;
}): WhatsNewAction {
  const version = (input.version || "").trim();
  if (!version || !(input.notes || "").trim()) return "skip";
  return (input.seenVersion || "").trim() === version ? "skip" : "show";
}
