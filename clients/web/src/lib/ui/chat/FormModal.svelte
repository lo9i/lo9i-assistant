<script lang="ts">
  import type { ApprovalRequired, Decision } from "$lib/api/types";
  import { formContent, startValue, type FieldValue } from "$lib/forms";
  import { t } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";

  // An MCP server's form (core/mcp/elicitation.py): its fields to fill in, or a link it asks the user to open. It
  // names the server that asks, so its words aren't taken for the assistant's. Closing it cancels.
  let { form, onanswer }: { form: ApprovalRequired; onanswer: (d: Decision) => void } = $props();
  const request = $derived(form.request);
  const fields = $derived(request.fields ?? []);
  let values = $state<Record<string, FieldValue>>({});
  let missing = $state<string[]>([]);

  $effect(() => {
    values = Object.fromEntries(fields.map((f) => [f.key, startValue(f)]));
  });

  function send(): void {
    if (request.url) return onanswer({ action: "accept" });
    const filled = formContent(fields, values);
    missing = filled.missing;
    if (!missing.length) onanswer({ action: "accept", content: filled.content });
  }

  function toggle(key: string, value: string, on: boolean): void {
    const picked = (values[key] as string[]) ?? [];
    values[key] = on ? [...picked, value] : picked.filter((v) => v !== value);
  }

  const cancel = () => onanswer({ action: "cancel" });
</script>

<Modal title={t("form.asks", { server: request.asked_by ?? "" })} description={request.message} onclose={cancel} width={560}>
  {#if request.url}
    <p class="text-meta">{t("form.openLink")}</p>
    <a class="link" href={request.url} target="_blank" rel="noreferrer noopener">{request.url}</a>
  {:else}
    <div class="form">
      {#each fields as f (f.key)}
        {#if f.type === "boolean"}
          <label class="check">
            <input type="checkbox" checked={values[f.key] === true} onchange={(e) => (values[f.key] = e.currentTarget.checked)} />
            {f.title}
          </label>
        {:else}
          <div class="field">
            <span class="field-label"
              >{f.title}{#if f.required}<span class="required"> *</span>{/if}</span
            >
            {#if f.type === "choice"}
              <select class="input" value={values[f.key]} onchange={(e) => (values[f.key] = e.currentTarget.value)}>
                <option value="">{t("form.pick")}</option>
                {#each f.options ?? [] as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
              </select>
            {:else if f.type === "choices"}
              {#each f.options ?? [] as option (option.value)}
                <label class="check">
                  <input
                    type="checkbox"
                    checked={(values[f.key] as string[] | undefined)?.includes(option.value)}
                    onchange={(e) => toggle(f.key, option.value, e.currentTarget.checked)}
                  />
                  {option.label}
                </label>
              {/each}
            {:else}
              <input
                class="input"
                type={f.type === "number" || f.type === "integer"
                  ? "number"
                  : f.format === "email"
                    ? "email"
                    : f.format === "date"
                      ? "date"
                      : "text"}
                step={f.type === "integer" ? 1 : "any"}
                value={values[f.key]}
                oninput={(e) => (values[f.key] = e.currentTarget.value)}
                autocomplete="off"
              />
            {/if}
          </div>
        {/if}
        {#if f.description}<span class="text-caption">{f.description}</span>{/if}
      {/each}
    </div>
    {#if missing.length}<p class="error-text">{t("form.missing", { fields: missing.join(", ") })}</p>{/if}
  {/if}
  {#snippet footer()}
    <button class="btn btn--ghost" onclick={() => onanswer({ action: "decline" })}>{t("form.decline")}</button>
    <button class="btn btn--primary" onclick={send}>{request.url ? t("form.opened") : t("form.send")}</button>
  {/snippet}
</Modal>

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .field-label {
    font-weight: 600;
  }
  .required {
    color: var(--color-danger);
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--font-size-sm);
    cursor: pointer;
  }
  .link {
    word-break: break-all;
  }
</style>
