<script lang="ts">
  // A reply's interactive app, run sandboxed with no network (src/lib/htmlApp.ts). Its frame loads the static page
  // that shows the document it's sent and passes on its height, taken only from that frame and kept within bounds.
  import { asset } from "$app/paths";
  import { APP_FRAME, APP_SANDBOX, DEFAULT_HEIGHT, appDocument, appHeight } from "$lib/htmlApp";
  import { t } from "$lib/i18n.svelte";
  import { theme } from "$lib/theme.svelte";

  let { source }: { source: string } = $props();

  // A new theme shows the app again, so its colours follow the reply around it.
  const shown = $derived(appDocument(source, theme.resolved));
  let frame = $state<HTMLIFrameElement>();
  let height = $state(DEFAULT_HEIGHT);

  function loaded(): void {
    // Its origin is opaque, so no origin names it; the static page takes only the first document it's sent.
    frame?.contentWindow?.postMessage(shown, "*");
  }

  function onmessage(event: MessageEvent): void {
    if (!frame || event.source !== frame.contentWindow) return;
    height = appHeight(event.data) ?? height;
  }
</script>

<svelte:window {onmessage} />

{#key shown}
  <iframe
    bind:this={frame}
    class="html-app"
    title={t("thread.app")}
    sandbox={APP_SANDBOX}
    src={asset(APP_FRAME)}
    style:height="{height}px"
    onload={loaded}
  ></iframe>
{/key}

<style>
  .html-app {
    display: block;
    width: 100%;
    margin: 0 0 10px;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-md);
    background: transparent;
  }
</style>
