<script lang="ts">
  import type { TaskSession } from "$lib/api/types";
  import { clock } from "$lib/clock.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";
  import FuelGauge from "../FuelGauge.svelte";
  import StatusBar from "../StatusBar.svelte";

  // A coding session's status line under its message box, as a subagent's (SubagentStatus): how full its agent's
  // context is and the model it runs on, when its worker says, and how long it's been at it, or was until it `ended`.
  // What its worker doesn't say isn't shown; how it's doing is its row's in the panel above.
  type Props = { session: TaskSession; ended: string };
  let { session, ended }: Props = $props();
  const time = clock();
  const measured = $derived(session.context_limit > 0 && session.context_tokens > 0);
</script>

<StatusBar compact>
  {#if session.model}
    <span class="model" title={t("tasks.modelHint", { agent: session.name })}>{session.model}</span>
  {/if}
  <span class="elapsed" title={t("tasks.elapsedHint")}>{duration(session.started_at, ended || time.now)}</span>
  {#if measured}
    <span class="fuel-end"
      ><FuelGauge
        tokens={session.context_tokens}
        limit={session.context_limit}
        heading={t("fuel.agentContext", { agent: session.name })}
        note={t("fuel.agentNote")}
      /></span
    >
  {/if}
</StatusBar>

<style>
  .model,
  .elapsed {
    cursor: default;
  }
  .model {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: var(--font-mono);
  }
  /* A box of its own, centred in the line, as the conversation's (ChatPanel): inline, the ring (no text, so no
   baseline) would sit on the line's baseline, below the others. */
  .fuel-end {
    display: flex;
    align-items: center;
    flex: none;
    margin-left: auto;
  }
  .elapsed {
    font-variant-numeric: tabular-nums;
  }
</style>
