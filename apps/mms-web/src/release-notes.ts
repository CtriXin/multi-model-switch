/** Release-note helpers shared by the help guide's update history. */

/**
 * The body without its `## 升级须知` section. The guide shows that section as
 * its own callout above the body, so leaving it in the body prints the same
 * paragraphs twice.
 */
export function withoutUpgradeSection(notes: string): string {
  const lines = notes.split("\n");
  const kept: string[] = [];
  let skippingLevel = 0;
  for (const line of lines) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      if (skippingLevel && level <= skippingLevel) skippingLevel = 0;
      if (!skippingLevel && heading[2].trim() === "升级须知") {
        skippingLevel = level;
        continue;
      }
    }
    if (!skippingLevel) kept.push(line);
  }
  return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
