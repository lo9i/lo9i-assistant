import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import PluginIcon from "./PluginIcon.svelte";

const svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>';

describe("PluginIcon", () => {
  it("shows a logo as an image and one drawn in currentColor as a mask, never inline", () => {
    const logo = render(PluginIcon, { props: { icon: { name: "", svg, mono: false } } }).body;
    expect(logo).toContain('<img class="logo');
    expect(logo).toContain('src="data:image/svg+xml;base64,');
    const mono = render(PluginIcon, { props: { icon: { name: "", svg, mono: true }, size: 16 } }).body;
    expect(mono).toContain('class="mask');
    expect(mono).toContain("mask-image: url(data:image/svg+xml;base64,");
    expect(logo + mono).not.toContain("<path");
  });

  it("shows the generic icon until a Lucide icon has loaded, and without one", () => {
    expect(render(PluginIcon, { props: { icon: { name: "tv", svg: "", mono: false } } }).body).toContain("lucide-panels-top-left");
    expect(render(PluginIcon, { props: { icon: null } }).body).toContain("lucide-panels-top-left");
  });
});
