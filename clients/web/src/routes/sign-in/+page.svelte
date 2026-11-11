<script lang="ts">
  // Where an emailed sign-in link opens (core/sign_in_links.py), its token after #, so it never reaches a server's
  // log. The browser pairs only once the user presses Sign in: a mail scanner that opens the link uses nothing up.
  // The layout shows it on its own; an already paired browser goes on to the app.
  import { onMount } from "svelte";
  import { replaceState } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { DaemonClient } from "$lib/api/client";
  import { HttpTransport } from "$lib/api/transport";
  import { deviceName } from "$lib/deviceName";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SignInFrame from "$lib/ui/SignInFrame.svelte";

  const client = new DaemonClient(new HttpTransport());
  const token = location.hash.slice(1);
  let ready = $state(false);
  let error = $state(token ? "" : t("signInLink.incomplete"));
  let busy = $state(false);

  onMount(() => {
    replaceState(location.pathname, {});
    client.auth.me().then(openApp, () => (ready = true));
  });

  async function signIn(): Promise<void> {
    busy = true;
    error = "";
    try {
      await client.auth.signInWithLink(token, deviceName(navigator.userAgent));
      openApp();
    } catch (e) {
      error = describe(e);
      busy = false;
    }
  }

  function openApp(): void {
    location.replace(resolve("/"));
  }
</script>

{#if ready}
  <SignInFrame>
    <h1 class="text-heading">{t("signInLink.title")}</h1>
    {#if token}
      <p class="text-label">{t("signInLink.hint")}</p>
      <div><button class="btn btn--primary" onclick={signIn} disabled={busy}>{t("signInLink.signIn")}</button></div>
    {/if}
    {#if error}
      <p class="error-text">{error}</p>
      <div><a class="btn btn--ghost" href={resolve("/")}>{t("signInLink.back")}</a></div>
    {/if}
  </SignInFrame>
{/if}
