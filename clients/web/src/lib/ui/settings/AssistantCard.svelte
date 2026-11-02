<script lang="ts">
  import { Power, RotateCcw } from "@lucide/svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { confirmation, type Coming, type Ending } from "$lib/shutdown";
  import Confirm from "../Confirm.svelte";
  import SettingsCard from "../Card.svelte";
  import AssistantUpdates from "./AssistantUpdates.svelte";
  import EndingDialog from "./EndingDialog.svelte";
  import SettingRow from "./SettingRow.svelte";

  const { client, notices } = useDaemon();
  const current = resource((c) => c.identity.name(), ["settings"]);
  let name = $state("");
  let message = $state("");

  $effect(() => {
    name = current.data ?? "";
  });

  async function save(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    try {
      message = t("assistant.saved", { name: await client.identity.rename(name) });
    } catch (err) {
      message = describe(err);
    }
  }

  // Whether stopping can work, or asks for the administrator's password first; read when the page opens.
  const host = resource((c) => c.system.host(), []);
  let confirming = $state<Ending | null>(null);
  let ending = $state<Coming | null>(null);
  let dialog = $state<EndingDialog>();
  // A stop that asks for the administrator's password first (`stop_note`) waits for the macOS dialog.
  let askingPassword = $state(false);

  async function end(kind: Ending): Promise<void> {
    askingPassword = kind === "stop" && !!host.data?.stop_note;
    try {
      const status = await (kind === "restart" ? client.system.restart() : client.system.stop());
      ending = { ending: kind, waiting: status.waiting_for_runs, update: false, canTakeBack: true, neededBy: "" };
      void dialog?.pending();
    } catch (e) {
      notices.report(e);
    } finally {
      askingPassword = false;
    }
  }

  // Takes the kind as an argument: `{@const kind}` is derived from `confirming`, so read after clearing it, it's
  // null and the restart would become a stop.
  function answer(kind: Ending, yes: boolean): void {
    confirming = null;
    if (yes) void end(kind);
  }
</script>

<SettingsCard id="assistant" title={t("assistant.title")} sub={t("assistant.sub")}>
  <form onsubmit={save}>
    <SettingRow label={t("assistant.name")}>
      {#snippet hint()}{t("assistant.nameHint")}{/snippet}
      <input class="input name" bind:value={name} placeholder={t("assistant.name")} aria-label={t("assistant.name")} />
      <button class="btn btn--primary btn--sm" type="submit" disabled={!name.trim() || name.trim() === current.data}
        >{t("common.save")}</button
      >
    </SettingRow>
  </form>
  {#if message}<p class="text-meta saved">{message}</p>{/if}
  <AssistantUpdates />
  <SettingRow label={t("assistant.ending")}>
    {#snippet hint()}
      {#if host.data?.stop_refusal}{host.data.stop_refusal}
      {:else if askingPassword}{t("startup.waitingPassword")}
      {:else if host.data?.stop_note}{host.data.stop_note}
      {:else}{t("assistant.endingHint")}{/if}
    {/snippet}
    <button class="btn btn--sm" onclick={() => (confirming = "restart")}><RotateCcw size={14} /> {t("shutdown.restart")}</button>
    <button
      class="btn btn--sm btn--danger"
      onclick={() => (confirming = "stop")}
      disabled={!!host.data?.stop_refusal || askingPassword}
      title={host.data?.stop_refusal || undefined}><Power size={14} /> {t("shutdown.stop")}</button
    >
  </SettingRow>
</SettingsCard>

{#if confirming}
  {@const kind = confirming}
  <Confirm {...confirmation(kind)} onanswer={(yes) => answer(kind, yes)} />
{/if}

<EndingDialog bind:this={dialog} bind:ending />

<style>
  .name {
    width: 200px;
  }
  .saved {
    margin: -12px 0 0;
  }
</style>
