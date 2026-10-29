<script lang="ts">
  import Play from "@lucide/svelte/icons/play";
  import { agentDone, allowPopups, chime, popupsAllowed, systemNotice } from "$lib/agentDone.svelte";
  import { useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import SettingsCard from "../Card.svelte";
  import Toggle from "../Toggle.svelte";

  // Being told when the agent a conversation is handed to (/claude) is done with the job: once, when it waits
  // for the user, not at each step. Kept per browser.
  const { notices } = useDaemon();
  const preference = $derived(agentDone.preference);
  let blocked = $state(false);

  /** A pop-up while the page is behind is the browser's own notification, which it asks to allow first. */
  async function changePopup(on: boolean): Promise<void> {
    agentDone.set({ popup: on });
    blocked = on && !(await allowPopups());
  }

  function tryIt(): void {
    if (preference.sound) chime();
    if (!preference.popup) return;
    const title = t("agentDone.finished", { agent: "Claude Code" });
    if (!systemNotice(title, t("agentDoneCard.sample"), () => {})) notices.notify(`${title}: ${t("agentDoneCard.sample")}`, "info");
  }
</script>

<SettingsCard id="agent-done" title={t("agentDoneCard.title")} sub={t("agentDoneCard.sub")}>
  <div class="switch">
    <span class="text-label">{t("agentDoneCard.sound")}</span>
    <Toggle checked={preference.sound} label={t("agentDoneCard.soundLabel")} onchange={(on) => agentDone.set({ sound: on })} />
  </div>
  <div class="switch">
    <span class="text-label">{t("agentDoneCard.popup")}</span>
    <Toggle checked={preference.popup} label={t("agentDoneCard.popupLabel")} onchange={changePopup} />
  </div>
  {#if preference.popup && (blocked || !popupsAllowed())}
    <span class="text-caption">
      {t("agentDoneCard.blocked")}
    </span>
  {/if}
  <div>
    <button class="btn btn--neutral btn--sm" disabled={!preference.sound && !preference.popup} onclick={tryIt}>
      <Play size={14} />{t("agentDoneCard.try")}
    </button>
  </div>
</SettingsCard>

<style>
  .switch {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
</style>
