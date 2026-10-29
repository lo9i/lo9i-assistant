// What the import list says about each skill from another coding agent (core/skills/imports/).

import type { Importable, ImportOutcome } from "$lib/api/types";

/** The agent it comes from, and the project's folder name when it's a project's. */
export function whereFrom(item: Importable): string {
  const project = item.project.split("/").filter(Boolean).pop();
  return project ? `${item.agent_name} · ${project}` : item.agent_name;
}

/** Imported and unchanged, or broken: nothing to import. */
export function selectable(item: Importable): boolean {
  return item.state !== "imported" && !item.problems?.length;
}

/** What "Pick new" picks: not imported yet, and not one that works best handed to a coding agent. */
export function pickedByDefault(item: Importable): boolean {
  return item.state === "new" && selectable(item) && !item.needs_agent?.length;
}

export function stateLabel(item: Importable): string {
  if (item.state === "imported") return `imported as ${item.name_here}`;
  if (item.state === "changed") return `changed since imported as ${item.name_here}`;
  return "";
}

export function outcomeLine(outcome: ImportOutcome): string {
  const name = outcome.id.split("/").filter(Boolean).pop() ?? outcome.id;
  if (outcome.action === "failed") return `${name}: ${outcome.note}`;
  const how = outcome.note ? ` (${outcome.note})` : "";
  return `${name}: ${outcome.action} as ${outcome.name}${how}`;
}
