<script lang="ts">
  import Field from "../Field.svelte";
  import SecretInput from "../SecretInput.svelte";
  import { t } from "$lib/i18n.svelte";
  import { redirectUri } from "$lib/oauth";

  // The user's own OAuth app, for signing in (an email account, a plugin): the redirect URI to register with it,
  // then its client ID and secret, typed here and sent to the daemon. `keep`: empty ones keep the saved app.
  // `secretOptional`: a public client has none (an app registered for Mobile and desktop).
  type Props = { clientId: string; clientSecret: string; keep: boolean; secretOptional?: boolean };
  let { clientId = $bindable(), clientSecret = $bindable(), keep, secretOptional = false }: Props = $props();
  // Where Google or Microsoft send the browser back.
  const redirect = redirectUri();
</script>

<div class="redirect">
  <span class="field-label">{t("email.redirect")}</span>
  <code class="uri">{redirect}</code>
</div>
<Field label={t("email.clientId")}>
  <input class="input" placeholder={keep ? t("email.keepSaved") : ""} autocomplete="off" bind:value={clientId} />
</Field>
<Field label={secretOptional ? t("email.clientSecretOptional") : t("email.clientSecret")}>
  <SecretInput label={t("email.clientSecret")} placeholder={keep ? t("email.keepSaved") : ""} bind:value={clientSecret} />
</Field>

<style>
  .redirect {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .field-label {
    font-size: var(--font-size-sm);
    font-weight: 600;
  }
  .uri {
    overflow-wrap: anywhere;
    user-select: all;
  }
</style>
