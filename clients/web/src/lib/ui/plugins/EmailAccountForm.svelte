<script lang="ts">
  import Field from "../Field.svelte";
  import SecretInput from "../SecretInput.svelte";
  import OAuthAppFields from "./OAuthAppFields.svelte";
  import type { EmailAccount, EmailProvider, EmailSettings } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t, type Key } from "$lib/i18n.svelte";
  import { markdownLinkingOut } from "$lib/markdown";
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
      const body = { provider: provider.oauth, client_id: clientId, client_secret: clientSecret, redirect_uri: redirectUri() };
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

{#snippet named()}
  <Field label={t("email.nameLabel")}>
    <input class="input" placeholder={t("email.namePlaceholder")} bind:value={label} />
  </Field>
{/snippet}

{#snippet addressed()}
  <Field label={t("email.addressLabel")}>
    <input class="input" type="email" placeholder={t("email.addressPlaceholder")} autocomplete="email" bind:value={address} />
  </Field>
{/snippet}

{#snippet buttons(submit: string, disabled: boolean)}
  <div class="row">
    <button class="btn btn--primary" type="submit" {disabled}>{submit}</button>
    {#if oncancel}<button class="btn btn--ghost" type="button" onclick={oncancel}>{t("common.cancel")}</button>{/if}
  </div>
{/snippet}

<div class="fields">
  {#if providers.length > 1}
    <Field label={t("email.howToConnect")}>
      <select class="input" bind:value={choice}>
        <option value="" disabled>{t("email.chooseHow")}</option>
        {#each providers as p (p.id)}
          <option value={p.id}>{p.name}</option>
        {/each}
      </select>
    </Field>
  {/if}
  {#if provider?.password_help}
    <div class="prose text-label help">{@html markdownLinkingOut(provider.password_help)}</div>
  {/if}
  {#if provider?.password_url}
    <p class="text-label"><a href={provider.password_url} target="_blank" rel="noreferrer">{t("email.createHere")}</a></p>
  {/if}
  {#if provider?.oauth}
    <form class="fields" onsubmit={signIn}>
      {@render named()}
      {@render addressed()}
      <OAuthAppFields bind:clientId bind:clientSecret keep={again} />
      {@render buttons(
        saving ? t("email.opening") : t("email.signInWith", { provider: providerName }),
        saving || !address.includes("@") || (!clientId.trim() && !again),
      )}
    </form>
  {:else if provider?.supported}
    <form class="fields" onsubmit={save}>
      {@render named()}
      {#if !byHand}
        {@render addressed()}
        <Field label={t("email.appPassword")}>
          <SecretInput label={t("email.appPassword")} placeholder={account ? t("email.keepSaved") : ""} bind:value={form.password} />
        </Field>
      {:else}
        {#each FIELDS as f (f.key)}
          <Field label={t(f.label)}>
            {#if f.type === "password"}
              <SecretInput label={t(f.label)} placeholder={account ? t("email.keepSaved") : ""} bind:value={form[f.key]} />
            {:else}
              <input class="input" bind:value={form[f.key]} />
            {/if}
          </Field>
        {/each}
        <Field label={t("email.port")}>
          <input class="input" type="number" placeholder={t("email.portPlaceholder")} bind:value={form.port} />
        </Field>
      {/if}
      {@render buttons(saving ? t("webSearch.checking") : t("email.connect"), saving)}
    </form>
  {/if}
  {#if message}<p class="error-text">{message}</p>{/if}
</div>

<style>
  .fields {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  p {
    margin: 0;
  }
  /* A provider's steps: a numbered list, a link where each is done. */
  .help :global(ol) {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
</style>
