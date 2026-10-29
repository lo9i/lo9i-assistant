<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import { type Plugin, keyOf, kindOf } from "$lib/plugins";
  import type { UpdateStep } from "$lib/pluginUpdates";
  import { t } from "$lib/i18n.svelte";

  // Installed plugins with a newer version in the extras: update the ones picked, or all of them. `steps` is
  // each row's progress while they update (updateEach), shown in a column of its own.
  type Props = {
    plugins: Plugin[];
    busy: boolean;
    steps: Record<string, UpdateStep>;
    onupdate: (picked: Plugin[]) => Promise<void>;
  };
  let { plugins, busy, steps, onupdate }: Props = $props();
  const progress = $derived(plugins.some((p) => steps[keyOf(p)]));
  // Every plugin starts picked; unpicking one leaves it at its version.
  let skipped = $state(new Set<string>());
  const picked = $derived(plugins.filter((p) => !skipped.has(keyOf(p))));
  const all = $derived(picked.length === plugins.length);

  function toggle(p: Plugin, on: boolean): void {
    const next = new Set(skipped);
    if (on) next.delete(keyOf(p));
    else next.add(keyOf(p));
    skipped = next;
  }

  function toggleAll(on: boolean): void {
    skipped = on ? new Set() : new Set(plugins.map(keyOf));
  }

  function versions(p: Plugin): [string, string] {
    const found = p.kind === "server" ? p.server : p.skill;
    return [found.installed_version || "–", found.version ?? ""];
  }
</script>

<section class="table-card surface--glass updates">
  <header class="toolbar">
    <div>
      <h2 class="text-heading">{t("host.updates")}</h2>
      <p class="text-meta">{t("pluginUpdates.hint")}</p>
    </div>
    <div class="tools">
      <span class="pill">{plugins.length}</span>
      <button class="btn btn--neutral btn--sm" disabled={busy || !picked.length || all} onclick={() => onupdate(picked)}
        >{t("pluginUpdates.selected", { count: picked.length })}</button
      >
      <button class="btn btn--primary btn--sm" disabled={busy} onclick={() => onupdate(plugins)}
        ><RefreshCw size={14} />{t("pluginUpdates.all")}</button
      >
    </div>
  </header>
  <table class="data-table">
    <thead>
      <tr>
        <th class="check"
          ><input
            type="checkbox"
            aria-label={t("pluginUpdates.pickAll")}
            checked={all}
            onchange={(e) => toggleAll(e.currentTarget.checked)}
          /></th
        >
        <th>{t("pluginUpdates.plugin")}</th>
        <th class="hide-narrow">{t("pluginUpdates.kind")}</th>
        <th>{t("pluginUpdates.installed")}</th>
        <th>{t("pluginUpdates.new")}</th>
        {#if progress}<th class="step">{t("common.update")}</th>{/if}
      </tr>
    </thead>
    <tbody>
      {#each plugins as p (keyOf(p))}
        {@const [installed, available] = versions(p)}
        <tr>
          <td class="check"
            ><input
              type="checkbox"
              aria-label={t("pluginUpdates.update", { name: p.name })}
              checked={!skipped.has(keyOf(p))}
              onchange={(e) => toggle(p, e.currentTarget.checked)}
            /></td
          >
          <td>{p.name}</td>
          <td class="hide-narrow">{kindOf(p)}</td>
          <td>{installed}</td>
          <td><strong>{available}</strong></td>
          {#if progress}
            {@const step = steps[keyOf(p)]}
            <td class="step">
              {#if step === "updating"}
                <span class="bar" role="progressbar" aria-label={t("pluginUpdates.updating", { name: p.name })}></span>
              {:else if step === "waiting"}
                <span class="text-meta">{t("pluginUpdates.waiting")}</span>
              {:else if step === "updated"}
                <span class="done"><Check size={14} aria-hidden="true" />{t("pluginUpdates.updated")}</span>
              {:else if step === "failed"}
                <span class="failed">{t("pluginUpdates.failed")}</span>
              {/if}
            </td>
          {/if}
        </tr>
      {/each}
    </tbody>
  </table>
</section>

<style>
  .updates {
    flex: none;
    overflow: hidden;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
    padding: 16px 24px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .tools {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .check {
    width: 36px;
  }
  .check input {
    cursor: pointer;
  }
  .step {
    width: 120px;
  }
  /* Indeterminate: an update says nothing of how far it is, so a segment slides along the track. */
  .bar {
    position: relative;
    display: block;
    width: 96px;
    height: 4px;
    border-radius: 2px;
    overflow: hidden;
    background: color-mix(in srgb, var(--color-text-primary) 14%, transparent);
  }
  .bar::after {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 40%;
    border-radius: inherit;
    background: var(--color-brand);
    animation: slide 1.1s ease-in-out infinite;
  }
  @keyframes slide {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(250%);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .bar::after {
      width: 100%;
      animation: none;
      opacity: 0.6;
    }
  }
  .done {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--color-success);
  }
  .failed {
    color: var(--color-danger);
  }
</style>
