<script lang="ts">
  import Brain from "@lucide/svelte/icons/brain";
  import Check from "@lucide/svelte/icons/check";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import Copy from "@lucide/svelte/icons/copy";
  import Forward from "@lucide/svelte/icons/forward";
  import Inbox from "@lucide/svelte/icons/inbox";
  import Paperclip from "@lucide/svelte/icons/paperclip";
  import Sparkle from "@lucide/svelte/icons/sparkle";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
  import Wrench from "@lucide/svelte/icons/wrench";
  import type { Snippet } from "svelte";
  import { inlineArg, type ChatItem } from "$lib/chat/transcript";
  import { markdown } from "$lib/markdown";

  type Props = {
    items: ChatItem[];
    thinking: boolean;
    name: string;
    onsuggest: (text: string) => void;
    /** Moves a message the inbox sent on (its record's `dispatchId`) to another conversation; only in the inbox. */
    onmove?: (dispatchId: string) => void;
    /** Shown after the last message. */
    end?: Snippet;
    /** Keep the newest message in view as content arrives (the live chat). A preview reads from the top. */
    follow?: boolean;
  };
  let { items, thinking, name, onsuggest, onmove, end, follow = true }: Props = $props();

  const SUGGESTIONS = [
    "What do you remember about me?",
    "Every weekday at 8:00, send me a short summary of the news",
    "Search the web for this week's top AI announcements",
  ];

  let scroller = $state<HTMLElement>();
  let atBottom = true;
  let copied = $state<number | null>(null);

  // Follow new content only when the reader is already at the bottom.
  $effect.pre(() => {
    void items;
    void thinking;
    const el = scroller;
    if (el) atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  });
  $effect(() => {
    void items;
    void thinking;
    if (follow && scroller && atBottom) scroller.scrollTop = scroller.scrollHeight;
  });

  async function copy(id: number, text: string): Promise<void> {
    await navigator.clipboard.writeText(text);
    copied = id;
    setTimeout(() => (copied = copied === id ? null : copied), 1500);
  }
</script>

<div class="thread" bind:this={scroller}>
  {#if items.length === 0 && !thinking}
    <div class="empty">
      <span class="empty-icon"><Sparkles size={28} /></span>
      <h2>How can {name} help?</h2>
      <p class="text-label">Ask anything, attach a file or a screenshot, or type / for commands.</p>
      <div class="suggestions">
        {#each SUGGESTIONS as suggestion (suggestion)}
          <button onclick={() => onsuggest(suggestion)}>{suggestion}</button>
        {/each}
      </div>
    </div>
  {/if}
  {#each items as item (item.id)}
    {#if item.kind === "user"}
      <div class="row user">
        <div class="bubble user-bubble">
          {#if item.channel}<span class="micro-label">{item.channel}</span>{/if}
          <p>{item.text}</p>
          {#each item.files as file (file)}
            <span class="file"><Paperclip size={12} />{file}</span>
          {/each}
        </div>
      </div>
    {:else if item.kind === "assistant"}
      <div class="row assistant">
        <div class="bubble assistant-bubble">
          <span class="badge"><Sparkle size={14} fill="currentColor" /></span>
          <div class="prose">{@html markdown(item.text)}</div>
        </div>
        <div class="message-footer">
          <button class="round" aria-label="Copy" title="Copy" onclick={() => copy(item.id, item.text)}>
            {#if copied === item.id}<Check size={14} />{:else}<Copy size={14} />{/if}
          </button>
          {#if item.dispatchId && onmove}
            {@const dispatchId = item.dispatchId}
            <button class="round" aria-label="Move" title="Move to another conversation" onclick={() => onmove(dispatchId)}>
              <Forward size={14} />
            </button>
          {/if}
        </div>
      </div>
    {:else if item.kind === "thinking"}
      <details class="tool thought">
        <summary>
          <Brain size={12} />
          <span>Thinking</span>
          <!-- Open, the whole text shows below, so the preview would repeat its first line. -->
          <span class="detail preview">{item.text.split("\n")[0]}</span>
          <span class="chevron"><ChevronRight size={12} /></span>
        </summary>
        <p class="thought-text">{item.text}</p>
      </details>
    {:else if item.kind === "carried"}
      <details class="tool thought">
        <summary>
          <Inbox size={12} />
          <span>From the inbox</span>
          <span class="chevron"><ChevronRight size={12} /></span>
        </summary>
        <div class="prose carried">{@html markdown(item.text)}</div>
      </details>
    {:else if item.kind === "tool"}
      {@const arg = inlineArg(item.args)}
      <details class="tool {item.state}">
        <summary>
          <Wrench size={12} />
          <span>{item.name}</span>
          {#if arg}<span class="detail" title={arg}>{arg}</span>{/if}
          {#if item.state === "running"}<span class="dots"><i></i><i></i><i></i></span>{/if}
          {#if item.state === "cancelled"}<span class="stopped">stopped</span>{/if}
          {#if item.steps?.length}<span class="steps-count">{item.steps.length} {item.steps.length === 1 ? "step" : "steps"}</span>{/if}
          {#if item.args || item.output || item.steps?.length}<span class="chevron"><ChevronRight size={12} /></span>{/if}
        </summary>
        {#if item.args && Object.keys(item.args).length && !arg}<pre>{JSON.stringify(item.args, null, 2)}</pre>{/if}
        {#if arg}<pre class="command">{arg}</pre>{/if}
        {#if item.steps?.length}
          <div class="steps">
            {#each item.steps as step, i (i)}
              {@const stepArg = inlineArg(step.args)}
              <details class="tool step {step.state}">
                <summary>
                  <Wrench size={12} />
                  <span>{step.name}</span>
                  {#if stepArg}<span class="detail" title={stepArg}>{stepArg}</span>{/if}
                  {#if step.state === "running"}<span class="dots"><i></i><i></i><i></i></span>{/if}
                  {#if step.state === "cancelled"}<span class="stopped">stopped</span>{/if}
                  <span class="chevron"><ChevronRight size={12} /></span>
                </summary>
                <!-- A note a handed-off agent reports is a line of text, with no arguments. -->
                {#if step.args && Object.keys(step.args).length && !stepArg}<pre>{JSON.stringify(step.args, null, 2)}</pre>{/if}
                {#if stepArg}<pre class="command">{stepArg}</pre>{/if}
                {#if step.output}<pre>{step.output}</pre>{/if}
              </details>
            {/each}
          </div>
        {/if}
        {#if item.output}<pre>{item.output}</pre>{/if}
      </details>
    {:else if item.kind === "notice"}
      <p class="text-caption notice"><Inbox size={12} />{item.text}</p>
    {:else if item.kind === "transcript"}
      <p class="text-caption">Heard ({item.language}): {item.text}</p>
    {:else if item.kind === "error"}
      <div class="notice-warn">
        <TriangleAlert size={16} />
        <div>
          <strong>Something went wrong</strong>
          <p class="text-meta">{item.message}</p>
        </div>
      </div>
    {:else if item.kind === "stopped"}
      <p class="text-caption">Stopped.</p>
    {/if}
  {/each}
  {#if thinking}
    <div class="thinking">Thinking <span class="dots"><i></i><i></i><i></i></span></div>
  {/if}
  {#if end}{@render end()}{/if}
</div>

<style>
  .thread {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 16px 16px 8px;
  }
  .row {
    display: flex;
    flex-direction: column;
    max-width: min(800px, 100%);
  }
  .row.user {
    align-self: flex-end;
    align-items: flex-end;
    max-width: 85%;
  }
  .bubble {
    position: relative;
    padding: 14px 18px;
    border-radius: 16px;
    font-size: 0.92rem;
    line-height: 1.55;
    backdrop-filter: var(--surface-glass-blur);
    overflow-wrap: anywhere;
  }
  .user-bubble {
    background: color-mix(in srgb, var(--color-action-primary) 12%, transparent);
    border-bottom-right-radius: 8px;
  }
  .user-bubble p {
    margin: 0;
    white-space: pre-wrap;
  }
  .file {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
    margin-top: 6px;
  }
  .assistant-bubble {
    background: var(--color-bg-hover-ghost);
    border: 1px solid var(--color-border);
    border-bottom-left-radius: 8px;
    padding-right: 36px;
  }
  .badge {
    position: absolute;
    top: 10px;
    right: 12px;
    color: var(--color-brand);
  }
  .message-footer {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }
  .round {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    border: 1px solid var(--color-border);
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .round:hover {
    color: var(--color-text-primary);
  }
  .tool,
  .thinking {
    align-self: flex-start;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
  }
  .tool summary,
  .thinking {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: var(--radius-full);
    border: 1px solid var(--color-border);
    background: var(--color-bg-hover-ghost);
    list-style: none;
    cursor: pointer;
  }
  .tool summary::-webkit-details-marker {
    display: none;
  }
  .tool[open] .chevron {
    transform: rotate(90deg);
  }
  .chevron {
    display: inline-flex;
    transition: transform 0.12s ease;
  }
  .tool pre {
    margin-top: 8px;
    max-width: min(800px, 80vw);
  }
  .tool pre.command {
    opacity: 0.85;
  }
  .tool[open] > summary > .detail {
    display: none;
  }
  .detail {
    max-width: min(480px, 60vw);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
    opacity: 0.8;
  }
  .thought .detail {
    font-family: inherit;
    font-style: italic;
  }
  .thought[open] .preview {
    display: none;
  }
  .notice {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .carried {
    margin-top: 8px;
    max-width: min(800px, 80vw);
  }
  .thought-text {
    margin-top: 8px;
    max-width: min(800px, 80vw);
    white-space: pre-wrap;
    font-style: italic;
  }
  .stopped {
    color: var(--color-danger);
  }
  .steps-count {
    color: var(--color-text-muted);
  }
  .steps {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 8px;
    padding-left: 12px;
    border-left: 1px solid var(--color-border);
  }
  .dots {
    display: inline-flex;
    gap: 3px;
  }
  .dots i {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 1.1s ease-in-out infinite;
  }
  .dots i:nth-child(2) {
    animation-delay: 0.18s;
  }
  .dots i:nth-child(3) {
    animation-delay: 0.36s;
  }
  @keyframes pulse {
    0%,
    100% {
      opacity: 0.35;
      transform: scale(0.85);
    }
    50% {
      opacity: 1;
      transform: scale(1.15);
    }
  }
  .notice-warn {
    display: flex;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--radius-md);
    border: 1px solid color-mix(in srgb, var(--color-warn) 40%, var(--color-border));
    background: color-mix(in srgb, var(--color-warn) 10%, transparent);
    color: var(--color-warn);
    max-width: min(800px, 100%);
  }
  .notice-warn strong {
    color: var(--color-text-primary);
  }
  .notice-warn p {
    margin: 2px 0 0;
  }
  .empty {
    margin: auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    text-align: center;
  }
  .empty-icon {
    display: grid;
    place-items: center;
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--color-brand) 18%, transparent);
    color: var(--color-brand);
  }
  .empty h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }
  .empty .text-label {
    max-width: 320px;
  }
  .suggestions {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: min(460px, 100%);
    margin-top: 8px;
  }
  .suggestions button {
    padding: 11px 14px;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-bg-hover-ghost);
    text-align: left;
    cursor: pointer;
    transition:
      background 0.12s ease,
      border-color 0.12s ease;
  }
  .suggestions button:hover {
    background: var(--color-bg-card-hover);
    border-color: var(--color-divider);
  }
</style>
