<script lang="ts">
  // Where Google or Microsoft send the browser back after an email sign-in. It hands the code to the
  // daemon with the one-time state, which proves it: it works in a browser that isn't paired, such as
  // one on the assistant's own computer opened from the terminal app. The layout shows it on its own.
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { DaemonClient } from "$lib/api/client";
  import { HttpTransport } from "$lib/api/transport";
  import { describe } from "$lib/notices";

  let message = $state("Finishing the sign-in…");
  let done = $state(false);

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
      const account = await new DaemonClient(new HttpTransport()).email.finishSignIn(state, code);
      message = `Signed in: ${account.sender} can send and read mail. You can close this tab.`;
      done = true;
    } catch (e) {
      message = describe(e);
    }
  }
</script>

<main class="oauth">
  <p class:error-text={!done && !message.startsWith("Finishing")}>{message}</p>
  {#if done}<a class="btn btn--neutral" href={resolve("/settings") + "?tab=integrations"}>Open email settings</a>{/if}
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
