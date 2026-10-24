<script lang="ts">
  import type { StartupStatus } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { describe } from "$lib/notices";
  import SettingsCard from "../Card.svelte";

  const { client } = useDaemon();
  const loaded = resource((c) => c.system.startup(), []);
  let message = $state("");
  const s = $derived(loaded.data);

  const NOTES: Record<string, string[]> = {
    macos: [
      "macOS asks for your administrator password once. It runs as your user, without anyone logging in.",
      "A sleeping or powered-off Mac runs nothing; missed jobs catch up within 6 hours, and Notifications says when one ran late or was missed.",
      "With FileVault on, after a restart nothing runs until someone logs in once.",
    ],
    linux: [
      "It runs as a systemd user service (lo9i-assistant), as your user. Its log is in Settings → Logs; output from before it starts logging is in journalctl --user -u lo9i-assistant.",
      "A powered-off or suspended computer runs nothing; missed jobs catch up within 6 hours, and Notifications says when one ran late or was missed.",
      "Ollama isn't included: its Linux installer runs it as a service of its own.",
    ],
  };
  const computer = $derived(s?.platform === "macos" ? "the Mac" : "the computer");

  async function change(enable: boolean): Promise<void> {
    message = s?.platform === "macos" ? "Waiting for the macOS password dialog…" : "Working…";
    try {
      message = done(enable, await (enable ? client.system.enableStartup() : client.system.disableStartup()));
    } catch (e) {
      message = describe(e);
    }
    loaded.reload();
  }

  function done(enabled: boolean, s: StartupStatus): string {
    if (!enabled) return `Turned off. The daemon keeps running until you restart ${computer} or stop it.`;
    const system = s.platform === "macos" ? "macOS" : "systemd";
    return s.managed ? "Turned on." : `Turned on. The assistant restarts under ${system} in a few seconds.`;
  }
</script>

<SettingsCard
  id="startup"
  title="Start at boot"
  sub="Run the assistant from the moment {computer} starts, so jobs and Telegram keep working."
>
  {#snippet status()}
    {#if s}
      <span class="pill" class:pill--accent={s.enabled}>{s.enabled ? `On${s.includes_ollama ? " · with Ollama" : ""}` : "Off"}</span>
    {/if}
  {/snippet}
  {#if s === undefined}
    <p class="text-meta">{loaded.error ?? "Loading…"}</p>
  {:else if s.platform === "unsupported"}
    <p class="text-meta">Start at boot works on macOS and on Linux with systemd. This system has neither.</p>
  {:else}
    <ul class="callout text-caption">
      {#each NOTES[s.platform] ?? [] as note (note)}<li>{note}</li>{/each}
    </ul>
    {#if s.platform === "linux" && !s.starts_without_login}
      <p class="text-meta">
        <strong>Without lingering, it runs only while you're logged in.</strong> To start it at boot without logging in, an administrator
        runs this once on the computer: <code>sudo loginctl enable-linger $USER</code>
      </p>
    {/if}
    <div>
      {#if s.enabled}
        <button class="btn btn--danger" onclick={() => change(false)}>Turn off</button>
      {:else}
        <button class="btn btn--primary" onclick={() => change(true)}>Turn on</button>
      {/if}
    </div>
    {#if message}<p class="text-meta">{message}</p>{/if}
  {/if}
</SettingsCard>

<style>
  .callout {
    margin: 0;
    padding: 16px 16px 16px 32px;
    border-radius: var(--radius-sm);
    border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
    background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  p {
    margin: 0;
  }
</style>
