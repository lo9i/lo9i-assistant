<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import InstallDialog from "../repositories/InstallDialog.svelte";

  // A plugin the agent offers (offer_plugin): the same install as on the Plugins page, its tokens
  // typed here and sent to the daemon, never to the chat. The run goes on once it's installed or closed.
  let { offer, onanswer }: { offer: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
</script>

<InstallDialog
  server={offer.request.server}
  skill={offer.request.skill}
  onclose={(installed) => onanswer({ installed: Boolean(installed?.length) })}
/>
