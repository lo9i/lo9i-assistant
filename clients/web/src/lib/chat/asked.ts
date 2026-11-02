// What a run waits for, in a line: the title of the dialog that asks it (ui/chat/ApprovalModal.svelte), which the card
// of one the user hid shows too (ui/chat/PendingAsk.svelte).
import type { ApprovalRequest } from "$lib/api/types";
import { t } from "$lib/i18n.svelte";
import { pluginLabel } from "$lib/plugins";

export function askTitle(request: ApprovalRequest): string {
  const name = pluginLabel(request.name ?? request.server?.name ?? request.skill?.name ?? "");
  switch (request.kind) {
    case "question":
      return request.question ?? t("chat.pickOne");
    case "form":
      return t("form.asks", { server: request.asked_by ?? "" });
    case "plugin":
      return t("install.title", { name });
    case "plugin_setup":
      return t("chat.setUp", { name });
    default:
      return approvalTitle(request);
  }
}

/** An approval's: an MCP tool's call by its tool and server (core/mcp/described.py), else the tool asking. */
export function approvalTitle(request: ApprovalRequest): string {
  if (request.call) return t("chat.approveCall", { tool: request.call.tool, server: request.call.server });
  return request.tool ? t("chat.approveTool", { tool: String(request.tool) }) : t("chat.approveAction");
}
