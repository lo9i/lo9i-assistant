<script lang="ts">
  // Shown instead of the app while this browser isn't paired: every request needs a paired device. A browser that
  // has a passkey for this site signs in with it instead of a code; one that pairs with a code is offered one.
  import KeyRound from "@lucide/svelte/icons/key-round";
  import type { DaemonClient } from "$lib/api/client";
  import { deviceName } from "$lib/deviceName";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { addPasskey, passkeysWork, Prepared, signInWithPasskey } from "$lib/passkeys";

  let { client }: { client: DaemonClient } = $props();
  const passkeys = passkeysWork();
  const signing = new Prepared(() => client.auth.passkeyOptions());
  const adding = new Prepared(() => client.passkeys.options());
  if (passkeys) signing.prepare();
  let code = $state("");
  let name = $state(deviceName(navigator.userAgent));
  let error = $state("");
  let busy = $state(false);
  // Paired with a code: a passkey is offered before the app starts.
  let offering = $state(false);

  async function pair(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    await attempt(async () => {
      await client.auth.pair(code, name);
      // The token cookie is set now; start the app with it, or offer a passkey first.
      if (!passkeys) return location.reload();
      adding.prepare();
      offering = true;
    });
  }

  async function signIn(): Promise<void> {
    await attempt(async () => {
      if (await signInWithPasskey(client.auth, signing)) location.reload();
    });
  }

  async function add(): Promise<void> {
    await attempt(async () => {
      if (await addPasskey(client.passkeys, adding)) location.reload();
    });
  }

  async function attempt(action: () => Promise<void>): Promise<void> {
    busy = true;
    error = "";
    try {
      await action();
    } catch (err) {
      error = describe(err);
    }
    busy = false;
  }
</script>

<main class="pair">
  {#if offering}
    <h1 class="text-heading">{t("pair.paired")}</h1>
    <p class="text-label">{t("pair.offerPasskey")}</p>
    <div class="buttons">
      <button class="btn btn--primary" onclick={add} disabled={busy}><KeyRound size={16} />{t("pair.addPasskey")}</button>
      <button class="btn btn--ghost" onclick={() => location.reload()} disabled={busy}>{t("pair.notNow")}</button>
    </div>
  {:else}
    <h1 class="text-heading">{t("pair.title")}</h1>
    {#if passkeys}
      <p class="text-label">{t("pair.passkeyHint")}</p>
      <div><button class="btn btn--primary" onclick={signIn} disabled={busy}><KeyRound size={16} />{t("pair.passkey")}</button></div>
      <h2 class="micro-label">{t("pair.orCode")}</h2>
    {/if}
    <p class="text-label">
      {t("pair.howBefore")} <code>/devices</code>
      {t("pair.howAfter")}
    </p>
    <form onsubmit={pair}>
      <input
        class="input"
        bind:value={code}
        placeholder={t("pair.codePlaceholder")}
        aria-label={t("pair.code")}
        autocomplete="one-time-code"
        autocapitalize="characters"
        spellcheck="false"
      />
      <input class="input" bind:value={name} placeholder={t("pair.namePlaceholder")} aria-label={t("pair.name")} />
      <div>
        <button class={passkeys ? "btn btn--outline" : "btn btn--primary"} type="submit" disabled={busy || !code.trim()}
          >{t("pair.pair")}</button
        >
      </div>
    </form>
  {/if}
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
  .buttons {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  h1,
  h2,
  p {
    margin: 0;
  }
  h2 {
    margin-top: 8px;
  }
</style>
