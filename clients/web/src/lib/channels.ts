// Chat channels (Telegram, Slack) are plugins that say what the apps show for setting them up (their
// items), so nothing here knows a particular channel.
import { encode } from "uqr";
import type { ChannelStatus, SetupItem } from "./api/types";
import { t, type Key } from "./i18n.svelte";

const STATES: Record<ReturnType<typeof stateOf>, Key> = {
  Off: "channelSetup.off",
  Connected: "channelSetup.connected",
  "Not connected": "channelSetup.notConnected",
};

/** A channel's state as shown. */
export function stateLabel(state: ReturnType<typeof stateOf>): string {
  return t(STATES[state]);
}

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

/** A QR item's code as one SVG path, a module per unit, with the quiet border scanners need around it. The
 *  channel sends only the text; drawing it here means nothing a channel sends runs in the app. */
export function qrOf(text: string): { size: number; path: string } {
  const { size, data } = encode(text, { border: 4 });
  const runs = data.flatMap((row, y) => darkRuns(row).map(([x, width]) => `M${x} ${y}h${width}v1h-${width}z`));
  return { size, path: runs.join("") };
}

/** Each run of dark modules in a row, as [start, width]. */
function darkRuns(row: boolean[]): Array<[number, number]> {
  const runs: Array<[number, number]> = [];
  row.forEach((dark, x) => {
    if (!dark) return;
    const last = runs.at(-1);
    if (last && last[0] + last[1] === x) last[1] += 1;
    else runs.push([x, 1]);
  });
  return runs;
}

/** Where an email account's new mail can be announced: nowhere, or an installed channel. The one
 *  set stays offered after its channel is removed, so the account still shows it. */
export function alertOptions(channels: string[], current: string): Array<{ value: string; label: string }> {
  const names = current === "" || channels.includes(current) ? channels : [...channels, current];
  return [{ value: "", label: t("channelSetup.dontAnnounce") }, ...names.map((name) => ({ value: name, label: titleOf(name) }))];
}
