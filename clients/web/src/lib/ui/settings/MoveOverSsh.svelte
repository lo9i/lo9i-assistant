<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import Minus from "@lucide/svelte/icons/minus";
  import X from "@lucide/svelte/icons/x";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SecretInput from "../SecretInput.svelte";

  // Moving lo9i straight to another computer over SSH (src/lo9i/daemon/moves.py): the daemon signs in, installs lo9i
  // there when it's missing, exports with a key made for this move, copies it there, imports it and deletes the
  // copy. Its progress comes as `move` events, shown here step by step.
  const { client } = useDaemon();
  const status = resource((c) => c.system.moveStatus(), ["move"]);
  const saved = resource((c) => c.system.savedHosts(), ["mcp", "plugins"]);
  const ANOTHER = "";

  let picked = $state(ANOTHER);
  let host = $state("");
  let user = $state("");
  let port = $state("");
  let password = $state("");
  let keyPath = $state("");
  let replace = $state(false);
  let error = $state("");

  const s = $derived(status.data);
  const running = $derived(s?.state === "running");
  const pickedHost = $derived(saved.data?.find((h) => key(h.plugin, h.name) === picked));

  function key(plugin: string, name: string): string {
    return `${plugin}/${name}`;
  }

  async function move(): Promise<void> {
    error = "";
    try {
      status.data = await client.system.move(
        pickedHost
          ? { host: pickedHost.name, plugin: pickedHost.plugin, user: "", port: 0, password: "", key_path: "", replace }
          : { host, plugin: "", user, port: Number(port) || 0, password, key_path: keyPath, replace },
      );
      password = "";
    } catch (e) {
      error = describe(e);
    }
  }

  async function cancel(): Promise<void> {
    try {
      status.data = await client.system.cancelMove();
    } catch (e) {
      error = describe(e);
    }
  }
</script>

<form
  class="part"
  onsubmit={(e) => {
    e.preventDefault();
    void move();
  }}
>
  <span class="micro-label">{t("move.overSsh")}</span>
  <select class="input" bind:value={picked} aria-label={t("move.host")} disabled={running}>
    <option value={ANOTHER}>{t("move.anotherHost")}</option>
    {#each saved.data ?? [] as h (key(h.plugin, h.name))}
      <option value={key(h.plugin, h.name)}>{h.address ? `${h.name} (${h.address})` : h.name}</option>
    {/each}
  </select>
  {#if !pickedHost}
    <div class="row">
      <input class="input grow" bind:value={host} placeholder={t("move.address")} aria-label={t("move.address")} disabled={running} />
      <input class="input" bind:value={user} placeholder={t("move.user")} aria-label={t("move.user")} disabled={running} />
      <input class="input port" bind:value={port} inputmode="numeric" placeholder="22" aria-label={t("move.port")} disabled={running} />
    </div>
    <div class="row">
      <SecretInput bind:value={password} label={t("move.sshPassword")} placeholder={t("move.sshPassword")} />
      <input class="input grow" bind:value={keyPath} placeholder={t("move.keyPath")} aria-label={t("move.keyPath")} disabled={running} />
    </div>
  {/if}
  <label class="check"><input type="checkbox" bind:checked={replace} disabled={running} />{t("move.replaceThere")}</label>
  <div class="row">
    <button class="btn btn--primary" type="submit" disabled={running || (!pickedHost && !host.trim())}>{t("move.move")}</button>
    {#if running}<button class="btn" type="button" onclick={cancel}>{t("common.cancel")}</button>{/if}
  </div>
  <span class="text-caption">{t("move.sshHint")}</span>
  {#if error}<p class="error-text">{error}</p>{/if}
  {#if s && s.state}
    <ul class="steps" aria-live="polite">
      {#each s.steps as step (step.key)}
        <li class:waiting={step.state === "waiting"}>
          <span class="mark">
            {#if step.state === "running"}<span class="spinner"></span>
            {:else if step.state === "done"}<Check size={14} />
            {:else if step.state === "skipped"}<Minus size={14} />
            {:else if step.state === "failed"}<X size={14} />{/if}
          </span>
          <span
            >{step.label}{#if step.detail}<span class="text-meta"> · {step.detail}</span>{/if}</span
          >
        </li>
      {/each}
    </ul>
    {#if running && s.progress >= 0}<progress max="1" value={s.progress}></progress>{/if}
    {#if s.state === "failed" || s.state === "cancelled"}<p class="error-text">{s.error}</p>{/if}
    {#if s.state === "done"}
      <p class="text-meta">{t("move.moved", { host: s.host })}</p>
      <span class="micro-label">{t("move.toRedoThere")}</span>
      <ul class="redo">
        {#each s.to_redo as item (item)}<li>{item}</li>{/each}
      </ul>
    {/if}
  {/if}
</form>

<style>
  .part {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .grow {
    flex: 1 1 160px;
    min-width: 0;
  }
  .port {
    width: 80px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--font-size-sm);
    cursor: pointer;
  }
  .text-caption,
  .text-meta {
    margin: 0;
  }
  .steps,
  .redo {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: var(--font-size-sm);
  }
  .steps {
    list-style: none;
    padding: 0;
  }
  .steps li {
    display: flex;
    align-items: center;
    gap: 8px;
    overflow-wrap: anywhere;
  }
  .steps li.waiting {
    opacity: 0.5;
  }
  .mark {
    display: inline-flex;
    width: 16px;
    flex: none;
    justify-content: center;
  }
  .redo {
    padding-left: 20px;
  }
  progress {
    width: 100%;
  }
</style>
