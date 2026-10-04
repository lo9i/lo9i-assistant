<script lang="ts">
  import Download from "@lucide/svelte/icons/download";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import type { UploadedFile } from "$lib/api/types";
  import { useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";

  // A file the user sent: shown when the browser can (images inline; PDFs, plain text, audio and video
  // in a new tab) and saved with Download. It's fetched with the app's credentials, then kept as a local URL.
  let { file }: { file: UploadedFile } = $props();
  const { client } = useDaemon();
  let url = $state("");
  let error = $state("");
  const image = $derived(file.media_type.startsWith("image/"));
  // A tab opens the file as this app's page, so only types that can't run scripts there (not HTML or
  // SVG); images show inline instead, where scripts never run.
  const viewable = $derived(/^(audio|video)\/|^(text\/plain|application\/pdf)$/.test(file.media_type));

  $effect(() => {
    const current = file;
    let local = "";
    url = error = "";
    client.files
      .content(current)
      .then((blob) => (url = local = URL.createObjectURL(blob)))
      .catch((e) => (error = describe(e)));
    return () => local && URL.revokeObjectURL(local);
  });
</script>

{#if error}
  <p class="error-text">{error}</p>
{:else if url}
  {#if image}<img class="preview" src={url} alt={file.name} />{/if}
  <div class="actions">
    {#if viewable && !image}
      <a class="btn btn--neutral btn--sm" href={url} target="_blank" rel="noreferrer"><ExternalLink size={14} />Open</a>
    {/if}
    <a class="btn btn--primary btn--sm" href={url} download={file.name}><Download size={14} />Download</a>
  </div>
{:else}
  <p class="text-meta">Loading…</p>
{/if}

<style>
  .preview {
    max-width: 100%;
    max-height: 320px;
    border-radius: var(--radius-sm);
    object-fit: contain;
  }
  .actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
</style>
