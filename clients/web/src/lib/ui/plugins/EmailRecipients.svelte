<script lang="ts">
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";

  // Who the assistant emails without asking, from any account (Settings → General → Email).
  const { client } = useDaemon();
  const allowed = resource((c) => c.email.recipients(), ["integrations"]);
  let recipients = $state("");
  let saved = $state("");

  $effect(() => {
    recipients = allowed.data?.join(", ") ?? "";
  });

  async function save(): Promise<void> {
    try {
      await client.email.setRecipients(recipients.split(","));
      saved = t("email.saved");
    } catch (e) {
      saved = describe(e);
    }
  }
</script>

<section class="recipients" aria-label={t("email.allowed")}>
  <h3 class="micro-label">{t("email.allowed")}</h3>
  <label class="fields">
    <span class="text-label">{t("email.allowedHint")}</span>
    <div class="row">
      <input class="input" bind:value={recipients} placeholder={t("email.addresses")} aria-label={t("email.allowed")} />
      <button class="btn btn--neutral btn--sm" onclick={save}>{t("common.save")}</button>
    </div>
    {#if saved}<span class="text-meta">{saved}</span>{/if}
  </label>
</section>

<style>
  .recipients,
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .recipients {
    gap: 12px;
  }
  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  h3 {
    margin: 0;
  }
</style>
