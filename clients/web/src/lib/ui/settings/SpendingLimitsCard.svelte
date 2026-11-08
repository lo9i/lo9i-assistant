<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { formatNumber, t, type Key } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { LIMITS, fieldsOf, limitsOf, type Limit, type LimitFields } from "$lib/spending";
  import SettingsCard from "../Card.svelte";

  // What model calls may spend (core/usage/limits.py): per run of a scheduled job, per job a day, per conversation and
  // overall a day, in US dollars as the usage report prices them; each off while empty. A run that reaches one stops
  // there, saying which; at 80% the chat channels hear it once.
  const { client } = useDaemon();
  const loaded = resource((c) => c.usage.spending(), ["settings"]);
  const LABELS: Record<Limit, Key> = {
    job_run: "spending.jobRun",
    job_day: "spending.jobDay",
    conversation: "spending.conversation",
    day: "spending.day",
  };
  let fields = $state<LimitFields | null>(null);
  let error = $state("");
  let saving = $state(false);

  // Filled from the daemon's once, and again after each save.
  $effect(() => {
    if (fields === null && loaded.data) fields = fieldsOf(loaded.data.limits);
  });

  function dollars(amount: number): string {
    return formatNumber(amount, { style: "currency", currency: "USD" });
  }

  async function save(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const limits = fields && limitsOf(fields);
    if (!limits) {
      error = t("spending.notAmount");
      return;
    }
    saving = true;
    try {
      fields = fieldsOf((await client.usage.setLimits(limits)).limits);
      error = "";
    } catch (e) {
      error = describe(e);
    }
    saving = false;
    loaded.reload();
  }
</script>

<SettingsCard id="spending" title={t("spending.title")} sub={t("spending.sub")}>
  {#if fields === null}
    <p class="text-meta">{loaded.error ?? t("common.loading")}</p>
  {:else}
    <form onsubmit={save}>
      {#each LIMITS as limit (limit)}
        <label class="row">
          <span class="text-label">{t(LABELS[limit])}</span>
          <span class="amount">
            <span class="text-meta">US$</span>
            <input class="input" type="text" inputmode="decimal" placeholder={t("spending.none")} bind:value={fields[limit]} />
          </span>
        </label>
      {/each}
      <div class="actions">
        {#if loaded.data}<span class="text-meta">{t("spending.today", { spent: dollars(loaded.data.spent_today) })}</span>{/if}
        <button class="btn btn--primary btn--sm" type="submit" disabled={saving}>{t("common.save")}</button>
      </div>
    </form>
    <p class="text-meta">{t("spending.hint")}</p>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .amount {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .amount input {
    width: 9ch;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 4px;
  }
  .text-meta {
    margin: 0;
  }
</style>
