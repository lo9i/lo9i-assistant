<script lang="ts">
  import { arcs, shade } from "$lib/contextParts";
  import { resource } from "$lib/daemon.svelte";
  import ContextItemsCard from "./ContextItemsCard.svelte";
  import ContextPartsCard from "./ContextPartsCard.svelte";

  // What a new conversation's context is made of, measured as the health check measures it, so the user sees what
  // takes the room and can trim it: the ring of its parts, and beside it what the part picked lists, the largest
  // part until one is picked. It changes with memory, skills, plugins, accounts and the prompt's texts, so those
  // events measure it again.
  const context = resource((c) => c.doctor.context(), ["memory", "skills", "mcp", "plugins", "integrations", "prompts", "settings"]);
  const shown = $derived(context.data ? arcs(context.data.parts) : []);
  let picked = $state<string | null>(null);
  // A part picked that's gone after a change gives way to the largest again.
  const selected = $derived(shown.find((a) => a.name === picked)?.name ?? shown[0]?.name ?? "");
  const rank = $derived(shown.findIndex((a) => a.name === selected));
</script>

<div class="breakdown">
  <ContextPartsCard context={context.data} error={context.error ?? undefined} {selected} onselect={(name) => (picked = name)} />
  <ContextItemsCard context={context.data} {selected} color={rank < 0 ? "var(--ring-strong)" : shade(rank, shown.length)} />
</div>

<style>
  .breakdown {
    /* The brand's teal-gray, the largest part strongest, fading to the smallest. */
    --ring-strong: #9fd3d1;
    --ring-weak: #3f5859;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    align-items: start;
  }
  :global(:root[data-theme="light"]) .breakdown {
    --ring-strong: #364445;
    --ring-weak: #c3dbd9;
  }
  @media (max-width: 1100px) {
    .breakdown {
      grid-template-columns: 1fr;
    }
  }
  .breakdown > :global(*) {
    min-width: 0;
  }
</style>
