<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import Minus from "@lucide/svelte/icons/minus";
  import X from "@lucide/svelte/icons/x";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import SecretInput from "../SecretInput.svelte";
  import MovePart from "./MovePart.svelte";

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
  const ready = $derived(!running && (!!pickedHost || !!host.trim()));

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

<MovePart title={t("move.overSsh")} caption={t("move.sshHint")} onsubmit={() => void move()}>
  <div class="fields">
    <select class="input" bind:value={picked} aria-label={t("move.host")} disabled={running}>
      <option value={ANOTHER}>{t("move.anotherHost")}</option>
      {#each saved.data ?? [] as h (key(h.plugin, h.name))}
        <option value={key(h.plugin, h.name)}>{h.address ? `${h.name} (${h.address})` : h.name}</option>
      {/each}
    </select>
    {#if !pickedHost}
      <div class="fields where">
        <input class="input address" bind:value={host} placeholder={t("move.address")} aria-label={t("move.address")} disabled={running} />
        <input class="input" bind:value={user} placeholder={t("move.user")} aria-label={t("move.user")} disabled={running} />
        <input class="input" bind:value={port} inputmode="numeric" placeholder="22" aria-label={t("move.port")} disabled={running} />
      </div>
      <div class="fields pair">
        <SecretInput bind:value={password} label={t("move.sshPassword")} placeholder={t("move.sshPassword")} />
        <input
          class="input"
          bind:value={keyPath}
          placeholder={t("move.keyPath")}
          title={t("move.keyPathHint")}
          aria-label={t("move.keyPathHint")}
          disabled={running}
        />
      </div>
    {/if}
  </div>
  <div class="actions">
    <label class="check" title={t("move.replaceKept")}>
      <input type="checkbox" bind:checked={replace} disabled={running} />{t("move.replaceThere")}
    </label>
    {#if running}<button class="btn btn--ghost" type="button" onclick={cancel}>{t("common.cancel")}</button>{/if}
    <button class="btn" class:btn--primary={ready} class:btn--neutral={!ready} type="submit" disabled={!ready}>{t("move.move")}</button>
  </div>
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
</MovePart>

<style>
  /* Address, user and a narrow port on one line; the password and key file on the next. */
  .where {
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) 5.5rem;
  }
  .pair {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
  @container (max-width: 420px) {
    .where {
      grid-template-columns: minmax(0, 1fr) 5.5rem;
    }
    .address {
      grid-column: 1 / -1;
    }
    .pair {
      grid-template-columns: minmax(0, 1fr);
    }
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
