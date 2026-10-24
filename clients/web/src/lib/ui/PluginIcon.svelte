<script lang="ts">
  import PanelsTopLeft from "@lucide/svelte/icons/panels-top-left";
  import type { Component } from "svelte";
  import type { PluginIcon } from "$lib/api/types";
  import { lucideIcon, svgUrl } from "$lib/pluginIcons";

  // A plugin's icon: its Lucide icon, loaded when first shown, or its own SVG, only ever as an image or as a mask
  // (one drawn in currentColor, painted in the text colour like the app's icons). Without one, the generic icon.
  let { icon, size = 20 }: { icon?: PluginIcon | null; size?: number } = $props();
  let named = $state<Component | null>(null);

  $effect(() => {
    const name = icon?.name ?? "";
    named = null;
    if (!name) return;
    let current = true;
    void lucideIcon(name).then((found) => current && (named = found));
    return () => (current = false);
  });
</script>

{#if icon?.svg && icon.mono}
  <span class="mask" style:width="{size}px" style:height="{size}px" style:mask-image="url({svgUrl(icon.svg)})" aria-hidden="true"></span>
{:else if icon?.svg}
  <img class="logo" src={svgUrl(icon.svg)} width={size} height={size} alt="" />
{:else if named}
  {@const Named = named}
  <Named {size} />
{:else}
  <PanelsTopLeft {size} />
{/if}

<style>
  .mask {
    display: inline-block;
    flex: none;
    background: currentColor;
    mask-size: contain;
    mask-repeat: no-repeat;
    mask-position: center;
  }
  .logo {
    flex: none;
    object-fit: contain;
  }
</style>
