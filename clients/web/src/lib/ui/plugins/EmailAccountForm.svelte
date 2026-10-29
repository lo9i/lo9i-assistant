<script lang="ts">
  import SecretInput from "../SecretInput.svelte";
  import type { EmailAccount, EmailProvider, EmailSettings } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { redirectUri } from "$lib/oauth";

  const FIELDS: Array<{ key: Exclude<keyof EmailSettings, "port" | "imap_port" | "label">; label: Key; type?: string }> = [
    { key: "host", label: "email.smtpHost" },
    { key: "username", label: "email.username" },
    { key: "password", label: "email.password", type: "password" },
    { key: "sender", label: "email.sender" },
    { key: "imap_host", label: "email.imapHost" },
  ];

  type Props = {
    /** The email plugin whose providers it offers. */
    plugin: string;
    /** The account whose sign-in changes; a new account when absent. */
    account?: EmailAccount;
    onsaved: (account: EmailAccount) => void;
    oncancel?: () => void;
  };
  let { plugin, account, onsaved, oncancel }: Props = $props();

  const { client } = useDaemon();
  const loaded = resource((c) => c.email.providers(), []);
  const providers = $derived((loaded.data ?? []).filter((p) => p.plugin === plugin));
  let choice = $state("");
  // A plugin with one provider starts on it; an account that signed in with OAuth on its provider, to sign in again.
  $effect(() => {
    const signedIn = account?.auth === "oauth" ? providers.find((p) => p.oauth === account.oauth_provider) : undefined;
    const only = providers.length === 1 ? providers[0] : undefined;
    if (!choice && (signedIn ?? only)) choice = (signedIn ?? only)!.id;
  });
  const provider = $derived<EmailProvider | undefined>(providers.find((p) => p.id === choice));
  // A custom provider has no servers: they're entered here.
  const byHand = $derived(provider?.custom ?? false);
  // svelte-ignore state_referenced_locally
  let label = $state(account?.label ?? "");
  // svelte-ignore state_referenced_locally
  let address = $state(account?.sender ?? "");
  let form = $state<EmailSettings>({
    label: "",
    host: "",
    port: 587,
    username: "",
    password: "",
    sender: "",
    imap_host: "",
    imap_port: 993,
    plugin: "",
  });
  let message = $state("");
  let saving = $state(false);
  // Signing in (OAuth): the user's own OAuth app. The secret is typed here and goes to the daemon.
  let clientId = $state("");
  let clientSecret = $state("");
  // Where Google or Microsoft send the browser back; the user registers this with their OAuth app.
  const redirect = redirectUri();
  const providerName = $derived(provider?.oauth === "microsoft" ? "Microsoft" : "Google");
  // Signing an existing account in again reuses the app it signed in with.
  const again = $derived(account?.auth === "oauth" && account.oauth_provider === provider?.oauth);

  /** A provider's user name and sender are the address; a custom one takes the servers entered. */
  function settings(): EmailSettings {
    if (!provider || byHand) return { ...form, label, plugin };
    const { host, port, imap_host } = provider;
    return { label, host, port, imap_host, imap_port: 993, username: address, password: form.password, sender: address, plugin };
  }

  /** Opens the provider's sign-in page; the /oauth page finishes it and the account shows up here. */
  async function signIn(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    if (!provider) return;
    saving = true;
    try {
      const body = { provider: provider.oauth, client_id: clientId, client_secret: clientSecret, redirect_uri: redirect };
      const url = await client.email.startSignIn({ ...body, address, label, account_id: account?.id ?? "", plugin });
      window.open(url, "_blank", "noopener");
      message = t("email.finishSignIn", { provider: providerName });
    } catch (err) {
      message = describe(err);
    } finally {
      saving = false;
    }
  }

  async function save(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    saving = true;
    try {
      onsaved(await (account ? client.email.update(account.id, settings()) : client.email.add(settings())));
    } catch (err) {
      message = describe(err);
    } finally {
      saving = false;
    }
  }
</script>

<div class="fields">
  {#if providers.length > 1}
    <select class="input" bind:value={choice} aria-label={t("email.howToConnect")}>
      <option value="" disabled>{t("email.chooseHow")}</option>
      {#each providers as p (p.id)}
        <option value={p.id}>{p.name}</option>
      {/each}
    </select>
  {/if}
  {#if provider}
    <p class="text-label">
      {provider.password_help}
      {#if provider.password_url}<a href={provider.password_url} target="_blank" rel="noreferrer">{t("email.createHere")}</a>.{/if}
    </p>
  {/if}
  {#if provider?.oauth}
    <form class="fields" onsubmit={signIn}>
      <input class="input" placeholder={t("email.accountNamePlaceholder")} aria-label={t("email.accountName")} bind:value={label} />
      <input class="input" type="email" placeholder={t("email.address")} aria-label={t("email.address")} bind:value={address} />
      <div class="fields">
        <span class="text-caption">{t("email.redirect")}</span>
        <code class="uri">{redirect}</code>
      </div>
      <input
        class="input"
        placeholder={again ? t("email.clientIdKeep") : t("email.clientId")}
        aria-label={t("email.clientId")}
        bind:value={clientId}
      />
      <SecretInput
        label={t("email.clientSecret")}
        placeholder={again ? t("email.clientSecretKeep") : t("email.clientSecret")}
        bind:value={clientSecret}
      />
      <div class="row">
        <button class="btn btn--primary" type="submit" disabled={saving || !address.includes("@") || (!clientId.trim() && !again)}
          >{saving ? t("email.opening") : t("email.signInWith", { provider: providerName })}</button
        >
        {#if oncancel}<button class="btn btn--ghost" type="button" onclick={oncancel}>{t("common.cancel")}</button>{/if}
      </div>
    </form>
  {:else if provider?.supported}
    <form class="fields" onsubmit={save}>
      <input class="input" placeholder={t("email.accountNamePlaceholder")} aria-label={t("email.accountName")} bind:value={label} />
      {#if !byHand}
        <input class="input" type="email" placeholder={t("email.address")} aria-label={t("email.address")} bind:value={address} />
        <SecretInput label={t("email.appPassword")} placeholder={t("email.appPassword")} bind:value={form.password} />
      {:else}
        {#each FIELDS as f (f.key)}
          {#if f.type === "password"}
            <SecretInput label={t(f.label)} placeholder={t(f.label)} bind:value={form[f.key]} />
          {:else}
            <input class="input" placeholder={t(f.label)} aria-label={t(f.label)} bind:value={form[f.key]} />
          {/if}
        {/each}
        <input class="input" type="number" placeholder={t("email.portPlaceholder")} aria-label={t("email.port")} bind:value={form.port} />
      {/if}
      {#if account}<p class="text-caption">{t("email.keepPassword")}</p>{/if}
      <div class="row">
        <button class="btn btn--primary" type="submit" disabled={saving}>{saving ? t("webSearch.checking") : t("email.connect")}</button>
        {#if oncancel}<button class="btn btn--ghost" type="button" onclick={oncancel}>{t("common.cancel")}</button>{/if}
      </div>
    </form>
  {/if}
  {#if message}<p class="error-text">{message}</p>{/if}
</div>

<style>
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  p {
    margin: 0;
  }
  .uri {
    overflow-wrap: anywhere;
    user-select: all;
  }
</style>
