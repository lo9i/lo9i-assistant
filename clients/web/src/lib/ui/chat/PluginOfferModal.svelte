<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import { hasSetup } from "$lib/plugins";
  import InstallDialog from "../repositories/InstallDialog.svelte";
  import PluginSetupModal from "./PluginSetupModal.svelte";

  // A plugin the agent offers (offer_plugin): the same install as on the Plugins page, its tokens
  // typed here and sent to the daemon, never to the chat. A plugin with a setup (email accounts, a
  // channel's pairing) goes on to it; the run goes on once that's done, or the install is declined.
  // Esc, the scrim and × only hide either (`onhide`, `hidden`).
  type Props = { offer: ApprovalRequired; onanswer: (d: Decision) => void; onhide: () => void; hidden: boolean };
  let { offer, onanswer, onhide, hidden }: Props = $props();
  let installed = $state(false);
  const server = $derived(offer.request.server);
</script>

{#if installed && server}
  <PluginSetupModal {server} ondone={() => onanswer({ installed: true })} {onhide} {hidden} />
{:else}
  <InstallDialog
    {server}
    skill={offer.request.skill}
    {onhide}
    {hidden}
    onclose={(names) => {
      if (names?.length && server && hasSetup(server)) installed = true;
      else onanswer({ installed: Boolean(names?.length) });
    }}
  />
{/if}
