<script lang="ts">
  import Play from "@lucide/svelte/icons/play";
  import { agentDone, allowPopups, chime, popupsAllowed, systemNotice } from "$lib/agentDone.svelte";
  import { useDaemon } from "$lib/daemon.svelte";
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
    if (!systemNotice("Claude Code finished", "This is how it looks.", () => {}))
      notices.notify("Claude Code finished: this is how it looks.", "info");
  }
</script>

<SettingsCard
  id="agent-done"
  title="When an agent finishes"
  sub="Once Claude Code is done with what you asked and waits for you, on this browser."
>
  <div class="switch">
    <span class="text-label">Play a sound</span>
    <Toggle checked={preference.sound} label="Play a sound when an agent finishes" onchange={(on) => agentDone.set({ sound: on })} />
  </div>
  <div class="switch">
    <span class="text-label">Show a pop-up</span>
    <Toggle checked={preference.popup} label="Show a pop-up when an agent finishes" onchange={changePopup} />
  </div>
  {#if preference.popup && (blocked || !popupsAllowed())}
    <span class="text-caption">
      The browser doesn't show this page's notifications, so it shows here only while the page is open in front.
    </span>
  {/if}
  <div>
    <button class="btn btn--neutral btn--sm" disabled={!preference.sound && !preference.popup} onclick={tryIt}>
      <Play size={14} />Try
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
