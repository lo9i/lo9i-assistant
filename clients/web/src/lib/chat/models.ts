// The models a conversation can answer with, as its model menu lists them (ui/chat/ModelPicker.svelte).
import type { ConversationModels } from "../api/types";

/** A line of the menu: `id` "" is the main model (Settings → Model), which the conversation follows when it changes. */
export type ModelChoice = { id: string; name: string };

/** The main model first, by the name its provider lists it with, then the others; the main one isn't listed twice. */
export function modelChoices(offered: ConversationModels): ModelChoice[] {
  const main = offered.models.find((m) => m.id === offered.main);
  const others = offered.models.filter((m) => m.id !== offered.main);
  return [{ id: "", name: main?.name ?? offered.main }, ...others.map((m) => ({ id: m.id, name: m.name }))];
}
