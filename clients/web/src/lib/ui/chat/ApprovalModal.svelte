<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import { t } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";
  import PluginOfferModal from "./PluginOfferModal.svelte";
  import PluginSetupModal from "./PluginSetupModal.svelte";
  import QuestionModal from "./QuestionModal.svelte";

  // What the run waits for: an approval, a question with options, or a plugin to install or to set up.
  let { approval, onanswer }: { approval: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
  let reason = $state("");
  const request = $derived(approval.request);
  const reject = () => onanswer({ approved: false, reason: reason.trim() || null });
</script>

{#if request.kind === "question"}
  <QuestionModal question={approval} {onanswer} />
{:else if request.kind === "plugin"}
  <PluginOfferModal offer={approval} {onanswer} />
{:else if request.kind === "plugin_setup" && request.server}
  <PluginSetupModal server={request.server} ondone={() => onanswer({ done: true })} />
{:else}
  <Modal
    title={request.tool ? t("chat.approveTool", { tool: String(request.tool) }) : t("chat.approveAction")}
    description={request.reason ? String(request.reason) : undefined}
  >
    <pre>{request.command ?? JSON.stringify(request, null, 2)}</pre>
    <input class="input" placeholder={t("chat.rejectReason")} bind:value={reason} onkeydown={(e) => e.key === "Enter" && reject()} />
    {#snippet footer()}
      <button class="btn btn--danger" onclick={reject}>{t("chat.reject")}</button>
      <!-- svelte-ignore a11y_autofocus -->
      <button class="btn btn--primary" onclick={() => onanswer({ approved: true, reason: null })} autofocus>{t("chat.approve")}</button>
    {/snippet}
  </Modal>
{/if}
