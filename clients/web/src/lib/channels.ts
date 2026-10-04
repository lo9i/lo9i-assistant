// Chat channels (Telegram, Slack) are plugins that say what the apps show for setting them up (their
// items), so nothing here knows a particular channel.
import type { ChannelStatus, SetupItem } from "./api/types";

/** "Off" when turned off in the MCP servers page, else whether its process is connected. */
export function stateOf(channel: ChannelStatus): "Off" | "Connected" | "Not connected" {
  if (!channel.enabled) return "Off";
  return channel.connected ? "Connected" : "Not connected";
}

/** A channel's name as a title: "telegram" → "Telegram". */
export function titleOf(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** A text item as one line: "label: value", or the value alone. */
export function lineOf(item: SetupItem): string {
  return item.label ? `${item.label}: ${item.value}` : item.value;
}

/** Where an email account's new mail can be announced: nowhere, or an installed channel. The one
 *  set stays offered after its channel is removed, so the account still shows it. */
export function alertOptions(channels: string[], current: string): Array<{ value: string; label: string }> {
  const names = current === "" || channels.includes(current) ? channels : [...channels, current];
  return [{ value: "", label: "Don't announce" }, ...names.map((name) => ({ value: name, label: titleOf(name) }))];
}
