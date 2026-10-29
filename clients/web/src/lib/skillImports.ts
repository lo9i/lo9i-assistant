// What the import list says about each skill from another coding agent (core/skills/imports/).

import type { Importable, ImportOutcome } from "$lib/api/types";
import { t } from "$lib/i18n.svelte";

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
  if (item.state === "imported") return t("skillImports.stateImported", { name: item.name_here });
  if (item.state === "changed") return t("skillImports.stateChanged", { name: item.name_here });
  return "";
}

/** How an import went. Its note comes from the daemon and shows as it comes. */
export function outcomeLine(outcome: ImportOutcome): string {
  const source = outcome.id.split("/").filter(Boolean).pop() ?? outcome.id;
  if (outcome.action === "failed") return t("skillImports.outcomeFailed", { source, note: outcome.note });
  const action = t(outcome.action === "updated" ? "skillImports.actionUpdated" : "skillImports.actionImported");
  const values = { source, action, name: outcome.name, note: outcome.note };
  return t(outcome.note ? "skillImports.outcomeNote" : "skillImports.outcome", values);
}
