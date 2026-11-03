<script lang="ts">
  import X from "@lucide/svelte/icons/x";
  import type { ProactiveSettings } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { formatDate, t } from "$lib/i18n.svelte";
  import SettingsCard from "../Card.svelte";
  import Toggle from "../Toggle.svelte";
  import SettingRow from "./SettingRow.svelte";

  // What the assistant does on its own (core/proactive/): the morning briefing, the nightly and weekly reviews, urgent
  // reminders, and the kinds of suggestion muted. On by default; kept by the daemon, so it holds for every device. On
  // the Briefing page and in Settings → General.
  const { client, notices } = useDaemon();
  const proactive = resource((c) => c.proactive.get(), ["proactive"]);
  const chosen = $derived(proactive.data?.settings);
  // 0 Monday to 6 Sunday, as the daemon counts them; 2026-11-02 was a Monday.
  const DAYS = [0, 1, 2, 3, 4, 5, 6].map((d) => ({ d, name: formatDate(new Date(2026, 10, 2 + d), { weekday: "long" }) }));

  async function change(update: Partial<ProactiveSettings>): Promise<void> {
    if (!chosen) return;
    try {
      await client.proactive.saveSettings({ ...chosen, ...update });
    } catch (e) {
      notices.report(e);
    }
    proactive.reload();
  }

  async function unmute(kind: string): Promise<void> {
    try {
      await client.proactive.mute(kind, false);
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<SettingsCard id="briefing" title={t("proactiveCard.title")} sub={t("proactiveCard.sub")}>
  {#if proactive.error}
    <p class="error-text">{proactive.error}</p>
  {:else if chosen}
    <SettingRow label={t("proactiveCard.briefing")}>
      {#snippet hint()}{t("proactiveCard.briefingHint")}{/snippet}
      <input
        class="input time"
        type="time"
        value={chosen.briefing_time}
        aria-label={`${t("proactiveCard.briefing")}: ${t("proactiveCard.time")}`}
        onchange={(e) => e.currentTarget.value && change({ briefing_time: e.currentTarget.value })}
      />
      <Toggle checked={chosen.briefing ?? true} label={t("proactiveCard.briefing")} onchange={(on) => change({ briefing: on })} />
    </SettingRow>
    <SettingRow label={t("proactiveCard.nightly")}>
      {#snippet hint()}{t("proactiveCard.nightlyHint")}{/snippet}
      <input
        class="input time"
        type="time"
        value={chosen.nightly_time}
        aria-label={`${t("proactiveCard.nightly")}: ${t("proactiveCard.time")}`}
        onchange={(e) => e.currentTarget.value && change({ nightly_time: e.currentTarget.value })}
      />
      <Toggle checked={chosen.nightly ?? true} label={t("proactiveCard.nightly")} onchange={(on) => change({ nightly: on })} />
    </SettingRow>
    <SettingRow label={t("proactiveCard.weekly")}>
      {#snippet hint()}{t("proactiveCard.weeklyHint")}{/snippet}
      <select
        class="input"
        value={chosen.weekly_day ?? 6}
        aria-label={`${t("proactiveCard.weekly")}: ${t("proactiveCard.day")}`}
        onchange={(e) => change({ weekly_day: Number(e.currentTarget.value) })}
      >
        {#each DAYS as day (day.d)}<option value={day.d}>{day.name}</option>{/each}
      </select>
      <Toggle checked={chosen.weekly ?? true} label={t("proactiveCard.weekly")} onchange={(on) => change({ weekly: on })} />
    </SettingRow>
    <SettingRow label={t("proactiveCard.reminders")}>
      {#snippet hint()}{t("proactiveCard.remindersHint")}{/snippet}
      <Toggle checked={chosen.reminders ?? true} label={t("proactiveCard.reminders")} onchange={(on) => change({ reminders: on })} />
    </SettingRow>
    <div class="muted">
      <span class="text-label">{t("proactiveCard.muted")}</span>
      <span class="text-caption">{t("proactiveCard.mutedHint")}</span>
      {#if chosen.muted?.length}
        <ul>
          {#each chosen.muted as kind (kind)}
            <li class="pill">
              {kind}
              <button
                class="unmute"
                aria-label={t("proactiveCard.unmute", { kind })}
                title={t("proactiveCard.unmute", { kind })}
                onclick={() => unmute(kind)}><X size={12} /></button
              >
            </li>
          {/each}
        </ul>
      {:else}
        <span class="text-meta">{t("proactiveCard.noneMuted")}</span>
      {/if}
    </div>
  {/if}
</SettingsCard>

<style>
  .time {
    width: 7.5em;
  }
  .muted {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  ul {
    list-style: none;
    margin: 4px 0 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  li {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .unmute {
    display: inline-flex;
    border: 0;
    background: none;
    padding: 0;
    color: inherit;
    cursor: pointer;
  }
</style>
