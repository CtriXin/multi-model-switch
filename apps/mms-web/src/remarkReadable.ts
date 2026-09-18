import type { ListItem, Nodes, Paragraph, Root } from "mdast";

// Display-only repairs for two observed model-output errors. Work on Markdown
// nodes so fenced/indented code, inline code and HTML are never rewritten.
export function remarkReadable() {
  return (tree: Root, file: { value: unknown }) => {
    const source = String(file.value);
    function visit(node: Nodes) {
      if ("children" in node) node.children.forEach(visit);
      if (node.type === "paragraph") {
        const { start, end } = node.position || {};
        if (start?.line !== end?.line || start?.offset === undefined) return;
        const raw = source.slice(start.offset, end?.offset);
        const match = /^(#{2,6})(?=[\p{L}\p{N}])/u.exec(raw);
        const first = node.children[0];
        if (
          !match ||
          first?.type !== "text" ||
          !first.value.startsWith(match[1])
        )
          return;
        first.value = first.value.slice(match[1].length);
        Object.assign(node, { type: "heading", depth: match[1].length });
      }
      if (node.type !== "list" || !node.ordered) return;
      const items: ListItem[] = [];
      for (const item of node.children) {
        let current = { ...item, children: [] } as ListItem;
        items.push(current);
        for (const block of item.children) {
          if (block.type !== "paragraph") {
            current.children.push(block);
            continue;
          }
          let paragraph: Paragraph = { ...block, children: [] };
          current.children.push(paragraph);
          for (const child of block.children) {
            const previous = paragraph.children.at(-1);
            const next = (node.start ?? 1) + items.length;
            // Require a glued, sequential marker immediately before a bold
            // title. Do not guess at arbitrary numbers, versions or prose.
            const marker = new RegExp(`([^\\s\\d.])${next}\\.[ \\t]+$`);
            if (
              child.type === "strong" &&
              previous?.type === "text" &&
              marker.test(previous.value)
            ) {
              previous.value = previous.value.replace(marker, "$1");
              paragraph = { type: "paragraph", children: [] };
              current = { type: "listItem", children: [paragraph] };
              items.push(current);
            }
            paragraph.children.push(child);
          }
        }
      }
      node.children = items;
    }
    visit(tree);
  };
}
