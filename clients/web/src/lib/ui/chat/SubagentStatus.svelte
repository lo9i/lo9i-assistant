<script lang="ts">
  import type { SubagentStatus } from "$lib/api/types";
  import { clock } from "$lib/clock.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";
  import FuelGauge from "./FuelGauge.svelte";
  import StatusBar from "./StatusBar.svelte";

  // A subagent's status line, as the conversation's under its message box: how full its context is, its model calls
  // (of the step limit inside a delegate call; one in the background has none) and, unless `elapsed` is off (where its
  // time shows already), how long it's been at it, or was until it ended.
  type Props = { status: SubagentStatus; elapsed?: boolean };
  let { status, elapsed = true }: Props = $props();
  const time = clock();
  const calls = $derived(
    status.max_steps
      ? t("subagents.callsOf", { count: status.steps, max: status.max_steps })
      : t("subagents.calls", { count: status.steps }),
  );
  const callsHint = $derived(status.max_steps ? t("subagents.callsHint", { max: status.max_steps }) : t("subagents.callsHintBackground"));
</script>

<StatusBar compact>
  <FuelGauge
    tokens={status.context_tokens}
    limit={status.context_limit}
    heading={t("subagents.context")}
    note={t("subagents.contextNote")}
  />
  <span class="calls" title={callsHint}>{calls}</span>
  {#if elapsed && status.started_at}
    <span class="elapsed" title={t("subagents.elapsedHint")}>{duration(status.started_at, status.ended_at || time.now)}</span>
  {/if}
</StatusBar>

<style>
  .calls,
  .elapsed {
    font-variant-numeric: tabular-nums;
    cursor: default;
  }
</style>
