<script lang="ts">
  // Where the provider sends the browser back after a sign-in: an email account (Google, Microsoft), a
  // remote MCP server, or a plugin that signs in with the user's own OAuth app. It hands the code to the daemon with the one-time state, which proves it: it works
  // in a browser that isn't paired, such as one on the assistant's own computer opened from the terminal
  // app. The layout shows it on its own.
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { DaemonClient } from "$lib/api/client";
  import { HttpTransport } from "$lib/api/transport";
  import type { SignedIn } from "$lib/api/types";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";

  let message = $state(t("oauth.finishing"));
  let finished = $state(false);
  let signedIn = $state<SignedIn | null>(null);

  onMount(() => void finish());

  async function finish(): Promise<void> {
    const params = page.url.searchParams;
    const refused = params.get("error_description") ?? params.get("error");
    const state = params.get("state");
    const code = params.get("code");
    if (refused || !state || !code) {
      finished = true;
      message = t("oauth.didntFinish", { reason: refused ?? t("oauth.noCode") });
      return;
    }
    try {
      signedIn = await new DaemonClient(new HttpTransport()).oauth.finish(state, code);
      const texts = { email: "oauth.email", mcp: "oauth.server", plugin: "oauth.plugin" } as const;
      message = t(texts[signedIn.kind], { name: signedIn.name });
    } catch (e) {
      message = describe(e);
    }
    finished = true;
  }
</script>

<main class="oauth">
  <p class:error-text={!signedIn && finished}>{message}</p>
  {#if signedIn?.kind === "email" || signedIn?.kind === "plugin"}
    <a class="btn btn--neutral" href={resolve("/plugins")}>{t("home.openPlugins")}</a>
  {:else if signedIn}
    <a class="btn btn--neutral" href={resolve("/mcp") + `?s=${encodeURIComponent(signedIn.id)}`}>{t("oauth.openMcp")}</a>
  {/if}
</main>

<style>
  .oauth {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 16px;
    min-height: 100vh;
    padding: 16px;
    text-align: center;
    color: var(--color-text-primary);
    background: var(--color-bg-page, transparent);
  }
  p {
    max-width: 480px;
    margin: 0;
  }
</style>
