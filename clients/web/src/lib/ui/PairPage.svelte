<script lang="ts">
  // Shown instead of the app while this browser isn't paired: every request needs a paired device. While no device was
  // ever paired, the first one enters the setup code (on an appliance, printed on its label). After that a browser
  // signs in with a passkey it has for this site, with a link emailed to the owner, or with a pairing code; one that
  // pairs with a code is offered a passkey.
  import KeyRound from "@lucide/svelte/icons/key-round";
  import Mail from "@lucide/svelte/icons/mail";
  import { onMount } from "svelte";
  import type { DaemonClient } from "$lib/api/client";
  import type { SignInWays } from "$lib/api/types";
  import { deviceName } from "$lib/deviceName";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import { addPasskey, passkeysWork, Prepared, signInWithPasskey } from "$lib/passkeys";
  import SignInFrame from "$lib/ui/SignInFrame.svelte";

  let { client }: { client: DaemonClient } = $props();
  const passkeys = passkeysWork();
  const signing = new Prepared(() => client.auth.passkeyOptions());
  const adding = new Prepared(() => client.passkeys.options());
  if (passkeys) signing.prepare();
  let ways = $state<SignInWays | null>(null);
  let code = $state("");
  let name = $state(deviceName(navigator.userAgent));
  let email = $state("");
  let linkAsked = $state(false);
  // The pairing code is one click away where another way is offered.
  let withCode = $state(false);
  let error = $state("");
  let busy = $state(false);
  // Paired with a code: a passkey is offered before the app starts.
  let offering = $state(false);
  const onlyCode = $derived(!passkeys && !ways?.email_link);

  onMount(() => {
    client.auth.ways().then(
      (found) => (ways = found),
      () => (ways = { setup: false, email_link: false }),
    );
  });

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

  async function askForLink(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    await attempt(async () => {
      await client.auth.askForLink(email.trim());
      linkAsked = true;
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

<SignInFrame>
  {#if offering}
    <h1 class="text-heading">{t("pair.paired")}</h1>
    <p class="text-label">{t("pair.offerPasskey")}</p>
    <div class="buttons">
      <button class="btn btn--primary" onclick={add} disabled={busy}><KeyRound size={16} />{t("pair.addPasskey")}</button>
      <button class="btn btn--ghost" onclick={() => location.reload()} disabled={busy}>{t("pair.notNow")}</button>
    </div>
  {:else if ways?.setup}
    <h1 class="text-heading">{t("pair.setupTitle")}</h1>
    <p class="text-label">{t("pair.setupHint")}</p>
    <form onsubmit={pair}>
      {@render codeInput(t("pair.setupCode"))}
      <div><button class="btn btn--primary" type="submit" disabled={busy || !code.trim()}>{t("pair.continue")}</button></div>
    </form>
  {:else if ways}
    <h1 class="text-heading">{onlyCode ? t("pair.title") : t("pair.signIn")}</h1>
    {#if passkeys}
      <div><button class="btn btn--primary" onclick={signIn} disabled={busy}><KeyRound size={16} />{t("pair.passkey")}</button></div>
    {/if}
    {#if ways.email_link && linkAsked}
      <p class="text-label">{t("pair.linkAsked")}</p>
    {:else if ways.email_link}
      <form onsubmit={askForLink}>
        <input
          class="input"
          type="email"
          bind:value={email}
          placeholder={t("pair.emailPlaceholder")}
          aria-label={t("pair.email")}
          autocomplete="email"
          spellcheck="false"
        />
        <div>
          <button class={passkeys ? "btn btn--outline" : "btn btn--primary"} type="submit" disabled={busy || !email.trim()}
            ><Mail size={16} />{t("pair.emailLink")}</button
          >
        </div>
      </form>
    {/if}
    {#if onlyCode || withCode}
      <p class="text-label">
        {t("pair.howBefore")} <code>/devices</code>
        {t("pair.howAfter")}
      </p>
      <form onsubmit={pair}>
        {@render codeInput(t("pair.code"))}
        <input class="input" bind:value={name} placeholder={t("pair.namePlaceholder")} aria-label={t("pair.name")} />
        <div>
          <button class={onlyCode ? "btn btn--primary" : "btn btn--outline"} type="submit" disabled={busy || !code.trim()}
            >{t("pair.pair")}</button
          >
        </div>
      </form>
    {:else}
      <div><button class="btn btn--ghost" onclick={() => (withCode = true)}>{t("pair.withCode")}</button></div>
    {/if}
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SignInFrame>

{#snippet codeInput(label: string)}
  <input
    class="input"
    bind:value={code}
    placeholder={t("pair.codePlaceholder")}
    aria-label={label}
    autocomplete="one-time-code"
    autocapitalize="characters"
    spellcheck="false"
  />
{/snippet}
