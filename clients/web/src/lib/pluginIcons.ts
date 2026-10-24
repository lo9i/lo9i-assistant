// Plugins' icons (src/assistant/core/repositories/icons.py): a Lucide icon by name, or the plugin's own SVG.
import type { Component } from "svelte";
import type { McpServerStatus, PluginIcon } from "./api/types";

// Every Lucide icon, each its own small file, loaded the first time a plugin's icon names it, so naming any
// of them costs the app nothing until it's shown.
const ICONS = "/node_modules/@lucide/svelte/dist/icons/";
const lucide = import.meta.glob<{ default: Component }>("/node_modules/@lucide/svelte/dist/icons/*.svelte");

/** The Lucide icon with this name, or null for a name it doesn't have. */
export async function lucideIcon(name: string): Promise<Component | null> {
  const load = lucide[`${ICONS}${name}.svelte`];
  return load ? (await load()).default : null;
}

/** The names of the Lucide icons the app has, as the daemon checks plugins' icons against them. */
export function lucideNames(): string[] {
  return Object.keys(lucide)
    .map((path) => path.slice(ICONS.length, -".svelte".length))
    .sort();
}

/** The icon of the installed plugin with this name; null for one that isn't installed, or has none. */
export function installedIcon(servers: McpServerStatus[] | undefined, name: string): PluginIcon | null {
  const icon = servers?.find((s) => s.name === name)?.icon;
  return icon && (icon.name || icon.svg) ? icon : null;
}

/** A plugin's SVG as a data URL: shown only as an image or a mask, where a browser runs nothing in it. */
export function svgUrl(svg: string): string {
  let binary = "";
  for (const byte of new TextEncoder().encode(svg)) binary += String.fromCharCode(byte);
  return `data:image/svg+xml;base64,${btoa(binary)}`;
}
