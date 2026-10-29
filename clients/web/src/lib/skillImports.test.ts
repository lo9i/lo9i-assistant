import { describe, expect, it } from "vitest";
import type { Importable } from "$lib/api/types";
import { outcomeLine, pickedByDefault, selectable, stateLabel, whereFrom } from "./skillImports";

function item(over: Partial<Importable> = {}): Importable {
  return {
    id: "/home/me/.claude/skills/pdf",
    agent: "claude",
    agent_name: "Claude Code",
    kind: "skills",
    project: "",
    name: "pdf",
    description: "Fill PDF forms",
    files: [],
    state: "new",
    name_here: "pdf",
    renamed: "",
    ...over,
  };
}

describe("skill imports", () => {
  it("says where a skill comes from", () => {
    expect(whereFrom(item())).toBe("Claude Code");
    expect(whereFrom(item({ project: "/home/me/shop/" }))).toBe("Claude Code · shop");
  });

  it("offers only what there is to import, and picks new ones that need no coding agent", () => {
    expect(selectable(item({ state: "imported" }))).toBe(false);
    expect(selectable(item({ problems: ["broken"] }))).toBe(false);
    expect(selectable(item({ state: "changed" }))).toBe(true);
    expect(pickedByDefault(item())).toBe(true);
    expect(pickedByDefault(item({ needs_agent: ["It uses a coding agent's tools: Edit."] }))).toBe(false);
    expect(pickedByDefault(item({ state: "changed" }))).toBe(false);
  });

  it("names the state and the outcome", () => {
    expect(stateLabel(item({ state: "changed", name_here: "pdf-claude" }))).toBe("changed since imported as pdf-claude");
    expect(outcomeLine({ id: "/a/pdf", action: "imported", name: "pdf-claude", note: "named pdf-claude" })).toBe(
      "pdf: imported as pdf-claude (named pdf-claude)",
    );
    expect(outcomeLine({ id: "/a/pdf", action: "failed", name: "", note: "gone" })).toBe("pdf: gone");
  });
});
