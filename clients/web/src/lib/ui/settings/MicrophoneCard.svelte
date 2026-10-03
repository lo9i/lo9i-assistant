<script lang="ts">
  import { onMount } from "svelte";
  import { microphones, preferredMicrophone, setPreferredMicrophone } from "$lib/microphone.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  let devices = $state<MediaDeviceInfo[]>([]);
  let chosen = $state(preferredMicrophone());
  let error = $state("");
  const named = $derived(devices.some((d) => d.label));
  const supported = typeof navigator !== "undefined" && !!navigator.mediaDevices;

  async function load(): Promise<void> {
    try {
      devices = await microphones();
    } catch (e) {
      error = describe(e);
    }
  }

  /** Browsers name microphones only after the page may use one. */
  async function allow(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      error = "";
    } catch (e) {
      error = describe(e);
    }
    await load();
  }

  onMount(() => {
    if (!supported) return;
    void load();
    navigator.mediaDevices.addEventListener("devicechange", load);
    return () => navigator.mediaDevices.removeEventListener("devicechange", load);
  });
</script>

<SettingsCard id="microphone" title="Microphone" sub="For voice messages from the chat box in this browser.">
  {#if !supported}
    <p class="text-meta">This browser can't record here. Recording needs HTTPS or localhost.</p>
  {:else}
    {#if !named}
      <div class="row">
        <button class="btn btn--neutral" onclick={allow}>Allow microphone</button>
        <span class="text-caption">The browser asks once. Then the microphones show by name.</span>
      </div>
    {/if}
    <label class="field">
      <span class="micro-label">Input</span>
      <select class="input" bind:value={chosen} onchange={() => setPreferredMicrophone(chosen)} aria-label="Microphone">
        <option value="">Browser default</option>
        {#each devices.filter((d) => d.deviceId && d.deviceId !== "default") as d, i (d.deviceId)}
          <option value={d.deviceId}>{d.label || `Microphone ${i + 1}`}</option>
        {/each}
      </select>
      <span class="text-caption">Kept in this browser only. Press the microphone in the chat box to record.</span>
    </label>
  {/if}
  {#if error}<p class="error-text">{error}</p>{/if}
</SettingsCard>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
</style>
