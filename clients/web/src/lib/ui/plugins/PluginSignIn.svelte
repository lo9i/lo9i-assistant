<script lang="ts">
  import OAuthAppFields from "./OAuthAppFields.svelte";
  import type { SignInRefused } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { pluginLabel } from "$lib/plugins";
  import { describe } from "$lib/notices";
  import { redirectUri } from "$lib/oauth";

  // A plugin that signs in with the user's own OAuth app (`oauth:` in its server.yaml; the daemon's
  // core/mcp/plugin_oauth.py): whether it's signed in and as whom, signing in and out. The client ID and secret are
  // typed here and go to the daemon; the /oauth page finishes the sign-in, and it shows here once it's done, or why
  // the plugin's check refused it.
  let { plugin, provider }: { plugin: string; provider: string } = $props();

  const NAMES: Record<string, string> = { google: "Google" };
  // Where the user creates their OAuth app.
  const CONSOLES: Record<string, string> = { google: "https://console.cloud.google.com/apis/credentials" };

  const { client, hub } = useDaemon();
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  // The /oauth page finished it, but the plugin's check refused the account: the sign-in wasn't kept.
  $effect(() =>
    hub.on(["sign_in_refused"], (data) => {
      const refused = data as SignInRefused;
      if (refused.name !== plugin) return;
      message = refused.error;
      failed = true;
    }),
  );
  const status = $derived(servers.data?.find((s) => s.name === plugin));
  const signedIn = $derived(status?.signed_in_as ?? "");
  const providerName = $derived(NAMES[provider] ?? provider);
  let clientId = $state("");
  let clientSecret = $state("");
  // Signed in, the form shows only to sign in again.
  let again = $state(false);
  let message = $state("");
  let failed = $state(false);
  let busy = $state(false);

  /** Opens the provider's sign-in page. Signing in again with no client ID reuses the app it signed in with. */
  async function signIn(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    busy = true;
    try {
      const body = { client_id: clientId, client_secret: clientSecret, redirect_uri: redirectUri() };
      window.open(await client.mcp.startPluginSignIn(plugin, body), "_blank", "noopener");
      message = t("pluginSignIn.finish", { provider: providerName });
      failed = again = false;
    } catch (err) {
      message = describe(err);
      failed = true;
    } finally {
      busy = false;
    }
  }

  async function signOut(): Promise<void> {
    busy = true;
    try {
      await client.mcp.signOutPlugin(plugin);
      message = "";
      servers.reload();
    } catch (err) {
      message = describe(err);
      failed = true;
    } finally {
      busy = false;
    }
  }
</script>

<section class="sign-in" aria-label={t("pluginSignIn.title", { provider: providerName })}>
  <h3 class="micro-label">{t("pluginSignIn.title", { provider: providerName })}</h3>
  {#if servers.data === undefined}
    <p class="text-meta">{servers.error ?? t("common.loading")}</p>
  {:else}
    {#if signedIn}
      <p>{t("pluginSignIn.signedInAs", { provider: providerName, account: signedIn })}</p>
      {#if !again}
        <div class="row">
          <button class="btn btn--neutral btn--sm" onclick={() => (again = true)}>{t("pluginSignIn.signInAgain")}</button>
          <button class="btn btn--ghost btn--sm" disabled={busy} onclick={signOut}>{t("pluginSignIn.signOut")}</button>
        </div>
      {/if}
    {:else}
      <p class="text-meta">{t("pluginSignIn.notSignedIn", { name: pluginLabel(plugin), provider: providerName })}</p>
    {/if}
    {#if !signedIn || again}
      <form class="fields" onsubmit={signIn}>
        <div class="text-label">
          <p>{t("pluginSignIn.help")}</p>
          <ol class="steps">
            <li>
              {t("pluginSignIn.createClient")}
              {#if CONSOLES[provider]}<a href={CONSOLES[provider]} target="_blank" rel="noreferrer">{t("pluginSignIn.openConsole")}</a>{/if}
            </li>
            <li>{t("pluginSignIn.addRedirect")}</li>
            <li>{t("pluginSignIn.pasteClient")}</li>
          </ol>
        </div>
        <OAuthAppFields bind:clientId bind:clientSecret keep={!!signedIn} />
        <div class="row">
          <button class="btn btn--primary" type="submit" disabled={busy || (!clientId.trim() && !signedIn)}
            >{busy ? t("email.opening") : t("email.signInWith", { provider: providerName })}</button
          >
          {#if again}<button class="btn btn--ghost" type="button" onclick={() => (again = false)}>{t("common.cancel")}</button>{/if}
        </div>
      </form>
    {/if}
    {#if message}<p class={failed ? "error-text" : "text-meta"}>{message}</p>{/if}
  {/if}
</section>

<style>
  .sign-in {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-top: 16px;
    border-top: 1px solid var(--color-border);
  }
  /* Nothing above it to set it apart from (a dialog showing only this). */
  .sign-in:first-child {
    padding-top: 0;
    border-top: none;
  }
  .fields {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  h3,
  p {
    margin: 0;
  }
  .steps {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 6px 0 0;
    padding-left: 20px;
  }
</style>
