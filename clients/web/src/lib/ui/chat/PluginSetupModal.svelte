<script lang="ts">
  import type { FoundServer } from "$lib/api/types";
  import Modal from "../Modal.svelte";
  import PluginSetup from "../plugins/PluginSetup.svelte";

  // An installed plugin's setup in the conversation; the run goes on when it's closed.
  let { server, ondone }: { server: FoundServer; ondone: () => void } = $props();
</script>

<Modal title="Set up {server.name}" description={server.description} width={600} onclose={ondone}>
  <PluginSetup {server} />
  {#snippet footer()}
    <button class="btn btn--primary" onclick={ondone}>Done</button>
  {/snippet}
</Modal>
