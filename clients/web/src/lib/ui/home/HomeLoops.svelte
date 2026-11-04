<script lang="ts">
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import MessageCircle from "@lucide/svelte/icons/message-circle";
  import type { OpenLoop } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { itemWhen } from "$lib/home";
  import { homeLoops } from "$lib/homeLoops";
  import { t } from "$lib/i18n.svelte";
  import { openConversation } from "../openConversation";

  type Props = {
    // YYYY-MM-DD, to say when each one is due.
    today: string;
  };
  let { today }: Props = $props();

  // Home's Open loops card (core/home/loops.py), drawn live from the loops rather than from its result: what's still to
  // do or waiting but bills due, each with its conversation and Done.
  const { client, chats, notices } = useDaemon();
  const proactive = resource((c) => c.proactive.get(), ["proactive"]);
  const shown = $derived(homeLoops(proactive.data?.loops ?? []));
  const timed = $derived(shown.some((l) => l.due));

  // Work started in the inbox has no conversation to open: Chat never shows the inbox.
  function conversation(loop: OpenLoop): string {
    return loop.thread_id && loop.thread_id !== chats.inboxId ? loop.thread_id : "";
  }

  function done(loop: OpenLoop): void {
    client.proactive.closeLoop(loop.id, "done").catch(notices.report);
  }
</script>

{#if proactive.error}
  <p class="error-text">{proactive.error}</p>
{:else if proactive.data === undefined}
  <p class="text-meta">{t("common.loading")}</p>
{:else if shown.length === 0}
  <p class="text-meta">{t("homeLoops.none")}</p>
{:else}
  <ul class:timed>
    {#each shown as loop (loop.id)}
      {@const thread = conversation(loop)}
      <li>
        {#if timed}<span class="when">{loop.due ? itemWhen({ date: loop.due, time: "" }, today) : ""}</span>{/if}
        <span class="what">{loop.text}</span>
        <span class="actions">
          {#if thread}
            <button
              class="btn btn--icon"
              title={t("app.openItsConversation")}
              aria-label={t("app.openItsConversation")}
              onclick={() => openConversation(chats, notices, thread)}><MessageCircle size={16} /></button
            >
          {/if}
          <button class="btn btn--icon" title={t("homeLoops.markDone")} aria-label={t("homeLoops.markDone")} onclick={() => done(loop)}
            ><CircleCheck size={16} /></button
          >
        </span>
      </li>
    {/each}
  </ul>
{/if}

<style>
  /* As a card's items (SectionCard): a column of due days as wide as the longest, none when nothing is due, and the
   buttons at the end of each row. */
  ul {
    list-style: none;
    margin: 0;
    padding: 0 4px 0 0;
    max-height: 18rem;
    overflow-y: auto;
    overscroll-behavior: contain;
    display: grid;
    grid-template-columns: 1fr auto;
    column-gap: 16px;
  }
  ul.timed {
    grid-template-columns: max-content 1fr auto;
  }
  li {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
    align-items: center;
    padding: 6px 0;
    border-top: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  li:first-child {
    border-top: 0;
    padding-top: 0;
  }
  .when {
    white-space: nowrap;
    font-size: var(--font-size-sm);
    font-variant-numeric: tabular-nums;
    color: var(--color-text-muted);
  }
  .what {
    min-width: 0;
    font-weight: 500;
    overflow-wrap: anywhere;
  }
  .actions {
    display: flex;
    gap: 2px;
    --btn-icon-size: 28px;
  }
  p {
    margin: 0;
  }
</style>
