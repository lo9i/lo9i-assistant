<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import { approvalTitle } from "$lib/chat/asked";
  import { t } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";
  import PluginOfferModal from "./PluginOfferModal.svelte";
  import PluginSetupModal from "./PluginSetupModal.svelte";
  import FormModal from "./FormModal.svelte";
  import QuestionModal from "./QuestionModal.svelte";

  // What the run waits for: an approval, a question with options, a plugin to install or to set up, or a server's form.
  // Only its buttons answer it. Esc, the scrim and × hide it (`onhide`), and the run goes on waiting: hidden, it stays
  // as it was, with what was typed in it, until it's shown again.
  type Props = { approval: ApprovalRequired; onanswer: (d: Decision) => void; onhide: () => void; hidden?: boolean };
  let { approval, onanswer, onhide, hidden = false }: Props = $props();
  let reason = $state("");
  const request = $derived(approval.request);
  // An MCP tool's call comes in words (core/mcp/described.py): its title and why it asks, then what it does.
  const call = $derived(request.call);
  const title = $derived(approvalTitle(request));
  const why = $derived(
    call
      ? t(call.why === "asks_first" ? "chat.asksFirstCall" : "chat.untrustedCall", { server: call.server })
      : request.reason
        ? String(request.reason)
        : undefined,
  );
  const reject = () => onanswer({ approved: false, reason: reason.trim() || null });
</script>

{#if request.kind === "question"}
  <QuestionModal question={approval} {onanswer} {onhide} {hidden} />
{:else if request.kind === "form"}
  <FormModal form={approval} {onanswer} {onhide} {hidden} />
{:else if request.kind === "plugin"}
  <PluginOfferModal offer={approval} {onanswer} {onhide} {hidden} />
{:else if request.kind === "plugin_setup" && request.server}
  <PluginSetupModal server={request.server} settings ondone={() => onanswer({ done: true })} {onhide} {hidden} />
{:else}
  <Modal {title} description={why} onclose={onhide} closeLabel={t("pending.hide")} {hidden}>
    {#if call}
      {#if call.does}<p>{call.does}</p>{/if}
      {#if call.arguments.length}
        <dl>
          {#each call.arguments as argument (argument.name)}
            <dt>
              <code>{argument.name}</code>
              {#if argument.about}<span class="text-caption">{argument.about}</span>{/if}
            </dt>
            <dd>{argument.value}</dd>
          {/each}
        </dl>
      {:else}
        <p class="text-caption">{t("chat.noArguments")}</p>
      {/if}
      <details>
        <summary class="text-caption">{t("chat.exactCall")}</summary>
        <pre>{request.command}</pre>
      </details>
    {:else}
      <pre>{request.command ?? JSON.stringify(request, null, 2)}</pre>
    {/if}
    <input class="input" placeholder={t("chat.rejectReason")} bind:value={reason} onkeydown={(e) => e.key === "Enter" && reject()} />
    {#snippet footer()}
      <button class="btn btn--danger" onclick={reject}>{t("chat.reject")}</button>
      <!-- svelte-ignore a11y_autofocus -->
      <button class="btn btn--primary" onclick={() => onanswer({ approved: true, reason: null })} autofocus>{t("chat.approve")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  p {
    margin: 0;
  }
  dl {
    display: grid;
    gap: 10px;
    margin: 0;
  }
  dt {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 2px 8px;
  }
  dd {
    margin: 2px 0 0;
    white-space: pre-wrap;
    word-break: break-word;
  }
  summary {
    cursor: pointer;
  }
  details pre {
    margin-top: 6px;
  }
</style>
