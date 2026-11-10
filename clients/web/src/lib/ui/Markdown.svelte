<script lang="ts">
  // A reply's Markdown, its interactive apps (```html-app blocks) each in a sandboxed frame. Each part renders on its
  // own, so a reply still streaming after an app leaves the app's frame as it is.
  import { markdownParts } from "$lib/markdown";
  import HtmlApp from "./HtmlApp.svelte";

  let { text }: { text: string } = $props();

  const parts = $derived(markdownParts(text));
</script>

{#each parts as part, i (i)}
  {#if part.kind === "app"}<HtmlApp source={part.source} />{:else}{@html part.html}{/if}
{/each}
