<script lang="ts">
  import { besideChoices } from "$lib/chat/beside";
  import { resource } from "$lib/daemon.svelte";
  import { formatDate, t } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";
  import SearchField from "../SearchField.svelte";

  // "Open beside" on the conversation page: the conversation to show next to the one shown (`title`), picked from the
  // others, newest first, searched by title. Null when closed without one.
  type Props = { title: string; shown: string[]; onpick: (threadId: string | null) => void };
  let { title, shown, onpick }: Props = $props();
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  let query = $state("");
  const choices = $derived(besideChoices(conversations.data ?? [], shown, query));
</script>

<Modal title={t("board.openBeside")} description={t("board.openBesideOf", { title })} width={520} onclose={() => onpick(null)}>
  <SearchField bind:value={query} label={t("conversations.search")} />
  {#if conversations.error}
    <p class="error-text">{conversations.error}</p>
  {:else if conversations.data === undefined}
    <p class="text-meta">{t("common.loading")}</p>
  {:else if choices.length === 0}
    <p class="text-meta">{query ? t("common.noMatches") : t("board.noneBeside")}</p>
  {:else}
    <ul>
      {#each choices as c (c.thread_id)}
        <li>
          <button onclick={() => onpick(c.thread_id)}>
            <span class="title">{c.title || t("common.untitled")}</span>
            <span class="text-caption">{formatDate(c.updated_at, { dateStyle: "medium", timeStyle: "short" })}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</Modal>

<style>
  ul {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    max-height: min(50vh, 420px);
    overflow-y: auto;
  }
  button {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    padding: 9px 10px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  button:hover,
  button:focus-visible {
    background: var(--color-bg-hover-ghost);
  }
  .title {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }
  .text-caption {
    flex: none;
  }
  p {
    margin: 12px 0 0;
  }
</style>
