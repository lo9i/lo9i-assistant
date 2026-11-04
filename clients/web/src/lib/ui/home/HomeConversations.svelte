<script lang="ts">
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { homeConversations } from "$lib/homeConversations";
  import { t } from "$lib/i18n.svelte";
  import { openConversation } from "../openConversation";
  import ConversationRow from "./ConversationRow.svelte";

  // Home's Conversations card (core/home/conversations.py), drawn live from the conversations rather than from its
  // result: the most recent ones.
  const { chats, notices } = useDaemon();
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const runs = resource((c) => c.runs.inProgress(), ["run", "run_finished"]);
  const tasks = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  const name = resource((c) => c.identity.name(), ["settings"]);
  const open = external(chats.subscribe, chats.getSnapshot);
  const working = $derived(new Set([...(runs.data ?? []), ...(tasks.data ?? [])].map((r) => r.thread_id)));
  const live = $derived(new Map(open.current.chats.map((c) => [c.state.threadId, c.state])));
  const shown = $derived(homeConversations(conversations.data ?? []));
</script>

{#if conversations.error}
  <p class="error-text">{conversations.error}</p>
{:else if conversations.data === undefined}
  <p class="text-meta">{t("common.loading")}</p>
{:else if shown.length === 0}
  <p class="text-meta">{t("homeConversations.none")}</p>
{:else}
  <ul>
    {#each shown as conversation (conversation.thread_id)}
      <ConversationRow
        {conversation}
        live={live.get(conversation.thread_id) ?? null}
        working={working.has(conversation.thread_id)}
        name={name.data || t("chat.theAssistant")}
        onopen={() => openConversation(chats, notices, conversation.thread_id)}
      />
    {/each}
  </ul>
{/if}

<style>
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 22rem;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  p {
    margin: 0;
  }
</style>
