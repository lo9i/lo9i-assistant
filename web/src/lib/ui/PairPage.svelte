<script lang="ts">
  // Shown instead of the app while this browser isn't paired: every request needs a paired device.
  import type { DaemonClient } from "$lib/api/client";
  import { deviceName } from "$lib/deviceName";
  import { describe } from "$lib/notices";

  let { client }: { client: DaemonClient } = $props();
  let code = $state("");
  let name = $state(deviceName(navigator.userAgent));
  let error = $state("");
  let busy = $state(false);

  async function pair(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    busy = true;
    try {
      await client.auth.pair(code, name);
      // The token cookie is set now; start the app with it.
      location.reload();
    } catch (err) {
      error = describe(err);
      busy = false;
    }
  }
</script>

<main class="pair">
  <h1 class="text-heading">Pair this browser</h1>
  <p class="text-label">
    On a device that already uses the assistant, create a code: <code>/devices</code> in the terminal app, or Settings → Devices in a
    paired browser. Then enter it here.
  </p>
  <form onsubmit={pair}>
    <input
      class="input"
      bind:value={code}
      placeholder="Code, like K7QM-2XPD"
      aria-label="Pairing code"
      autocomplete="one-time-code"
      autocapitalize="characters"
      spellcheck="false"
    />
    <input class="input" bind:value={name} placeholder="Name for this device" aria-label="Device name" />
    <div><button class="btn btn--primary" type="submit" disabled={busy || !code.trim()}>Pair</button></div>
  </form>
  {#if error}<p class="error-text">{error}</p>{/if}
</main>

<style>
  .pair {
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 420px;
    margin: 0 auto;
    padding: 18vh 16px 40px;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  h1,
  p {
    margin: 0;
  }
</style>
