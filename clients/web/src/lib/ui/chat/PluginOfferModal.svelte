<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import { hasSetup } from "$lib/plugins";
  import InstallDialog from "../repositories/InstallDialog.svelte";
  import PluginSetupModal from "./PluginSetupModal.svelte";

  // A plugin the agent offers (offer_plugin): the same install as on the Plugins page, its tokens
  // typed here and sent to the daemon, never to the chat. A plugin with a setup (email accounts, a
  // channel's pairing) goes on to it; the run goes on once that's done, or the install is closed.
  let { offer, onanswer }: { offer: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
  let installed = $state(false);
  const server = $derived(offer.request.server);
</script>

{#if installed && server}
  <PluginSetupModal {server} ondone={() => onanswer({ installed: true })} />
{:else}
  <InstallDialog
    {server}
    skill={offer.request.skill}
    onclose={(names) => {
      if (names?.length && server && hasSetup(server)) installed = true;
      else onanswer({ installed: Boolean(names?.length) });
    }}
  />
{/if}
