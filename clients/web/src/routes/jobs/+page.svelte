<script lang="ts">
  import CalendarClock from "@lucide/svelte/icons/calendar-clock";
  import History from "@lucide/svelte/icons/history";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type { Job } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { every, local, state as jobState, timing } from "$lib/jobs";
  import { markdown } from "$lib/markdown";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import Toggle from "$lib/ui/Toggle.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { client, notices } = useDaemon();
  const jobs = resource((c) => c.jobs.list(), ["jobs"]);
  let picked = $state<string | null>(null);
  let query = $state("");
  // By name or task.
  const shown = $derived(
    (jobs.data ?? []).filter((j) => `${j.name} ${j.task}`.toLowerCase().includes(query.trim().toLowerCase())),
  );
  let confirming = $state(false);
  const job = $derived(jobs.data?.find((j) => j.name === picked) ?? jobs.data?.[0]);
  const runs = $derived([...(job?.runs ?? [])].reverse());

  const TONES: Record<string, string> = {
    ok: "var(--color-success)",
    failed: "var(--color-danger)",
    "needs attention": "var(--color-warn)",
  };

  function last(j: Job): string {
    const run = j.runs?.at(-1);
    return run ? run.status : "not run yet";
  }

  function change(action: () => Promise<unknown>): void {
    action().catch(notices.report);
  }
</script>

<TopBar title="Jobs" />

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Scheduled jobs</h2>
        <p class="text-meta">Click one to see its runs on the right.</p>
      </div>
      <SearchField bind:value={query} label="Search jobs" />
    </header>
    <div class="scroll">
      {#if jobs.error}
        <p class="error-text pad">{jobs.error}</p>
      {:else if jobs.data?.length === 0}
        <EmptyState icon={CalendarClock} title="No jobs yet" text="Ask the assistant to schedule one, like a morning news summary." />
      {:else if jobs.data && job}
        <table class="data-table">
          <thead><tr><th>Job</th><th class="hide-narrow">Schedule</th><th>State</th><th class="hide-narrow">Last run</th></tr></thead>
          <tbody>
            {#each shown as j (j.name)}
              <tr class:selected={j.name === job.name} onclick={() => (picked = j.name)}>
                <td><button class="row-button" onclick={() => (picked = j.name)}>{j.name}</button></td>
                <td class="hide-narrow">{every(j)}</td>
                <td>
                  <span class="state">
                    <span class="status-dot" style:--tone={j.enabled ? "var(--color-success)" : undefined}></span>{jobState(j)}
                  </span>
                </td>
                <td class="hide-narrow">
                  <span class="state">
                    <span class="status-dot" style:--tone={TONES[last(j)]}></span>{last(j)}
                  </span>
                </td>
              </tr>
            {:else}
              <tr><td colspan="4" class="text-meta">No matches.</td></tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <div class="column">
    {#if job}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading">{job.name}</h2>
          <Toggle
            checked={job.enabled}
            label={job.enabled ? "Pause" : "Resume"}
            onchange={(on) => change(() => client.jobs.setEnabled(job.name, on))}
          />
        </header>
        <div class="prose task">{@html markdown(job.task)}</div>
        <dl>
          <dt class="micro-label">Schedule</dt>
          <dd>{every(job)}<span class="text-caption">{timing(job)}</span></dd>
          <dt class="micro-label">State</dt>
          <dd>{jobState(job)}</dd>
          <dt class="micro-label">Last run</dt>
          <dd>{last(job)}</dd>
        </dl>
        <button class="btn btn--danger btn--sm delete" onclick={() => (confirming = true)}><Trash2 size={14} />Delete job</button>
      </section>
      <section class="runs-card surface--glass">
        <h3 class="micro-label">Recent runs</h3>
        <div class="runs-scroll">
          {#if runs.length === 0}
            <EmptyState icon={History} title="Not run yet" text="Runs show up here after the job's first run." />
          {:else}
            <ul class="runs">
              {#each runs as run (run.at)}
                <li>
                  <span class="status-dot" style:--tone={TONES[run.status]}></span>
                  <div>
                    <span>{local(run.at, job.timezone)} · <strong>{run.status}</strong></span>
                    {#if run.summary}<p class="text-meta">{run.summary}</p>{/if}
                  </div>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </section>
    {:else}
      <section class="placeholder surface--glass">
        <EmptyState icon={CalendarClock} title="No job selected" text="Pick one from the table to see its runs here." />
      </section>
    {/if}
  </div>
</div>

{#if confirming && job}
  <Confirm
    title="Delete {job.name}?"
    text="The job stops running and its history is removed."
    action="Delete"
    onanswer={(yes) => {
      confirming = false;
      if (yes) change(() => client.jobs.delete(job.name));
    }}
  />
{/if}

<style>
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
  }
  /* The table takes three quarters of the width, the job the rest. */
  .table-card {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .column {
    flex: 1 1 0;
    align-self: stretch;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .scroll {
    overflow-y: auto;
    min-height: 0;
  }
  .data-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .pad {
    padding: 24px;
  }
  tr {
    cursor: pointer;
  }
  tr.selected {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  tr.selected td:first-child {
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    cursor: pointer;
  }
  .state {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .details {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  .details header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .task {
    max-height: 30vh;
    overflow-y: auto;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 0;
    align-items: baseline;
  }
  dd {
    margin: 0;
    text-align: right;
  }
  dd .text-caption {
    display: block;
  }
  .delete {
    align-self: flex-start;
  }
  .runs-card {
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  h3 {
    margin: 0;
    padding: 16px 16px 0;
  }
  .runs-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }
  .runs {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .runs li {
    display: flex;
    gap: 10px;
    align-items: baseline;
  }
  .runs p {
    margin: 2px 0 0;
  }
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .table-card,
    .column {
      flex: none;
    }
    .runs-card {
      min-height: 240px;
    }
  }
</style>
