<script lang="ts">
  // Where the provider sends the browser back after a sign-in: an email account (Google, Microsoft) or a
  // remote MCP server. It hands the code to the daemon with the one-time state, which proves it: it works
  // in a browser that isn't paired, such as one on the assistant's own computer opened from the terminal
  // app. The layout shows it on its own.
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { DaemonClient } from "$lib/api/client";
  import { HttpTransport } from "$lib/api/transport";
  import type { SignedIn } from "$lib/api/types";
  import { describe } from "$lib/notices";

  let message = $state("Finishing the sign-in…");
  let signedIn = $state<SignedIn | null>(null);

  onMount(() => void finish());

  async function finish(): Promise<void> {
    const params = page.url.searchParams;
    const refused = params.get("error_description") ?? params.get("error");
    const state = params.get("state");
    const code = params.get("code");
    if (refused || !state || !code) {
      message = `The sign-in didn't finish: ${refused ?? "the provider sent no code back"}. Start it again from the app.`;
      return;
    }
    try {
      signedIn = await new DaemonClient(new HttpTransport()).oauth.finish(state, code);
      message =
        signedIn.kind === "email"
          ? `Signed in: ${signedIn.name} can send and read mail. You can close this tab.`
          : `Signed in to ${signedIn.name}: the assistant gets its tools from your next message. You can close this tab.`;
    } catch (e) {
      message = describe(e);
    }
  }
</script>

<main class="oauth">
  <p class:error-text={!signedIn && !message.startsWith("Finishing")}>{message}</p>
  {#if signedIn?.kind === "email"}
    <a class="btn btn--neutral" href={resolve("/plugins")}>Open Plugins</a>
  {:else if signedIn}
    <a class="btn btn--neutral" href={resolve("/mcp") + `?s=${encodeURIComponent(signedIn.id)}`}>Open MCP servers</a>
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
