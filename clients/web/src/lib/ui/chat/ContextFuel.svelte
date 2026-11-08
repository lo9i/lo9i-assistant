<script lang="ts">
  import { resource } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import FuelGauge from "./FuelGauge.svelte";

  // In the status bar: how full the conversation's context is. At the limit, older messages are summarized. While
  // the conversation is handed to an agent (/claude), the agent's context as it last said, while it works too
  // (`agent_context`). A dash while it isn't known: no window, or no tokens yet (the agent's first answer).
  let { threadId }: { threadId: string } = $props();

  const stats = resource((c) => c.conversations.stats(threadId), ["run_finished", "handoffs", "agent_context"]);
  const shown = $derived(stats.data && !stats.error && stats.data.thread_id === threadId ? stats.data : null);
</script>

{#if shown}
  <FuelGauge
    tokens={shown.context_tokens}
    limit={shown.context_limit}
    heading={shown.context_agent ? t("fuel.agentContext", { agent: shown.context_agent }) : t("fuel.context")}
    note={shown.context_agent ? t("fuel.agentNote") : t("fuel.note")}
  />
{/if}
