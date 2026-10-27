<script lang="ts">
  import Brain from "@lucide/svelte/icons/brain";
  import Check from "@lucide/svelte/icons/check";
  import ClipboardList from "@lucide/svelte/icons/clipboard-list";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import Copy from "@lucide/svelte/icons/copy";
  import Forward from "@lucide/svelte/icons/forward";
  import Inbox from "@lucide/svelte/icons/inbox";
  import Paperclip from "@lucide/svelte/icons/paperclip";
  import Sparkles from "@lucide/svelte/icons/sparkles";
  import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
  import Wrench from "@lucide/svelte/icons/wrench";
  import type { Snippet } from "svelte";
  import type { ShownCall } from "$lib/api/types";
  import { inlineArg, pinnable, withWhole, withWholeStep, type ChatItem } from "$lib/chat/transcript";
  import { WholeCalls } from "$lib/chat/wholeCalls.svelte";
  import { markdown } from "$lib/markdown";

  type Props = {
    items: ChatItem[];
    thinking: boolean;
    name: string;
    onsuggest: (text: string) => void;
    /** Moves a message the inbox sent on (its record's `dispatchId`) to another conversation; only in the inbox. */
    onmove?: (dispatchId: string) => void;
    /** Loads a tool call from history in full when it's opened; its card shows only its start until then. */
    loadCall?: (callId: string) => Promise<ShownCall>;
    /** Loads a step inside a call from history (a delegate call's, a handed-off agent's) in full when it's opened. */
    loadStep?: (callId: string, index: number) => Promise<ShownCall>;
    /** Shown after the last message. */
    end?: Snippet;
    /** Keep the newest message in view as content arrives, and the user's message the content at the top answers
     * pinned there (the live chat). A preview reads from the top. */
    follow?: boolean;
  };
  let { items, thinking, name, onsuggest, onmove, loadCall, loadStep, end, follow = true }: Props = $props();
  const wholes = new WholeCalls();

  const SUGGESTIONS = [
    "What do you remember about me?",
    "Every weekday at 8:00, send me a short summary of the news",
    "Search the web for this week's top AI announcements",
  ];

  let scroller = $state<HTMLElement>();
  let height = $state(0);
  let atBottom = true;
  // Scrolled up from the newest message, far enough that the live chat offers to go back down.
  let away = $state(false);
  let copied = $state<number | null>(null);
  // Where the copy of the user's message sits, from the thread's top (`.asked`'s top).
  const PINNED_TOP = 8;
  // The last user message whose start has scrolled up past where its copy sits: what's at the top answers it, so
  // its copy shows there, as an editor's sticky scroll shows the function being read. Only what the user wrote (a
  // `.row.user`); a task the assistant wrote for its agent never is.
  let askedId = $state<number | null>(null);
  const asked = $derived(items.filter(pinnable).find((item) => item.id === askedId));

  function below(el: HTMLElement): number {
    return el.scrollHeight - el.scrollTop - el.clientHeight;
  }

  // Follow new content only when the reader is already at the bottom.
  $effect.pre(() => {
    void items;
    void thinking;
    const el = scroller;
    if (el) atBottom = below(el) < 80;
  });
  $effect(() => {
    void items;
    void thinking;
    void height;
    if (follow && scroller && atBottom) scroller.scrollTop = scroller.scrollHeight;
    measure();
  });

  function measure(): void {
    if (scroller) away = below(scroller) > 100;
    askedId = follow && scroller ? scrolledPast(scroller) : null;
  }

  function scrolledPast(el: HTMLElement): number | null {
    const line = el.getBoundingClientRect().top + PINNED_TOP;
    const rows = el.querySelectorAll<HTMLElement>(".row.user");
    for (let i = rows.length - 1; i >= 0; i--) {
      if (rows[i].getBoundingClientRect().top < line) return Number(rows[i].dataset.id);
    }
    return null;
  }

  // To the message's start, just under its copy, so the copy covers it and the rest reads on below.
  function toAsked(): void {
    const row = scroller?.querySelector(`.row.user[data-id="${askedId}"]`);
    if (!scroller || !row) return;
    const offset = row.getBoundingClientRect().top - scroller.getBoundingClientRect().top - PINNED_TOP + 1;
    scroller.scrollBy({ top: offset, behavior: "smooth" });
  }

  function toBottom(): void {
    scroller?.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
  }

  async function copy(id: number, text: string): Promise<void> {
    await navigator.clipboard.writeText(text);
    copied = id;
    setTimeout(() => (copied = copied === id ? null : copied), 1500);
  }
</script>

<div class="frame">
  <div class="thread" bind:this={scroller} bind:clientHeight={height} onscroll={measure}>
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
        <div class="row user" data-id={item.id}>
          <div class="bubble user-bubble">
            {#if item.channel}<span class="micro-label">{item.channel}</span>{/if}
            {#if item.text}<p>{item.text}</p>{/if}
            {#each item.files as file (file)}
              <span class="file"><Paperclip size={12} color="var(--color-accent)" />{file}</span>
            {/each}
          </div>
        </div>
      {:else if item.kind === "assistant"}
        <div class="row assistant">
          <div class="bubble assistant-bubble">
            <span class="badge"><Sparkles size={14} /></span>
            <!-- In the badge's corner, shown while the pointer is on the reply. -->
            <button class="copy" class:done={copied === item.id} aria-label="Copy" title="Copy" onclick={() => copy(item.id, item.text)}>
              {#if copied === item.id}<Check size={14} />{:else}<Copy size={14} />{/if}
            </button>
            <div class="prose">{@html markdown(item.text)}</div>
          </div>
          {#if item.dispatchId && onmove}
            {@const dispatchId = item.dispatchId}
            <div class="message-footer">
              <button class="round" aria-label="Move" title="Move to another conversation" onclick={() => onmove(dispatchId)}>
                <Forward size={14} />
              </button>
            </div>
          {/if}
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
      {:else if item.kind === "brief"}
        <!-- The assistant wrote it, not the user: collapsed, apart from the user's bubbles, and never pinned. -->
        <details class="tool brief">
          <summary>
            <ClipboardList size={12} />
            <span>Task for {item.agent}</span>
            <span class="detail preview">{item.text.split("\n")[0]}</span>
            <span class="chevron"><ChevronRight size={12} /></span>
          </summary>
          <div class="prose brief-text">{@html markdown(item.text)}</div>
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
        {@const whole = wholes.get(item.callId)}
        {@const call = whole?.state === "loaded" ? withWhole(item, whole.call) : item}
        {@const arg = inlineArg(call.args)}
        <details class="tool {call.state}" ontoggle={(e) => e.currentTarget.open && loadCall && wholes.open(item, loadCall)}>
          <summary>
            <Wrench size={12} />
            <span>{call.name}</span>
            {#if arg}<span class="detail" title={arg}>{arg}</span>{/if}
            {#if call.state === "running"}<span class="dots"><i></i><i></i><i></i></span>{/if}
            {#if call.state === "cancelled"}<span class="stopped">stopped</span>{/if}
            {#if call.steps?.length}<span class="steps-count">{call.steps.length} {call.steps.length === 1 ? "step" : "steps"}</span>{/if}
            {#if call.args || call.output || call.steps?.length}<span class="chevron"><ChevronRight size={12} /></span>{/if}
          </summary>
          {#if call.args && Object.keys(call.args).length && !arg}<pre>{JSON.stringify(call.args, null, 2)}</pre>{/if}
          {#if arg}<pre class="command">{arg}</pre>{/if}
          {#if call.steps?.length}
            <div class="steps">
              {#each call.steps as shownStep, i (i)}
                {@const wholeStep = wholes.getStep(item.callId, i)}
                {@const step = wholeStep?.state === "loaded" ? withWholeStep(shownStep, wholeStep.call) : shownStep}
                {@const stepArg = inlineArg(step.args)}
                <details
                  class="tool step {step.state}"
                  ontoggle={(e) => e.currentTarget.open && loadStep && wholes.openStep(item, i, shownStep, loadStep)}
                >
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
                  {#if wholeStep?.state === "loading"}<p class="text-caption whole-note">Loading the whole step…</p>{/if}
                  {#if wholeStep?.state === "failed"}<p class="text-caption whole-note">Couldn't load the whole step.</p>{/if}
                </details>
              {/each}
            </div>
          {/if}
          {#if call.output}<pre>{call.output}</pre>{/if}
          {#if whole?.state === "loading"}<p class="text-caption whole-note">Loading the whole call…</p>{/if}
          {#if whole?.state === "failed"}<p class="text-caption whole-note">Couldn't load the whole call.</p>{/if}
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
  <!-- Over the thread's top, like an editor's sticky scroll: what the reply below answers. Its own row stays as it
       is, so following the newest content never moves. -->
  {#if asked}
    <button class="asked" title="Go to your message" onclick={toAsked}>
      <span class="asked-text">{asked.text || asked.files.join(", ")}</span>
    </button>
  {/if}
  <!-- Over the thread's foot, just above the composer, so showing it never moves the messages. -->
  {#if follow && away}
    <button class="to-bottom" onclick={toBottom}>↓ Go to bottom</button>
  {/if}
</div>

<style>
  .frame {
    position: relative;
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .to-bottom {
    position: absolute;
    bottom: 6px;
    left: 50%;
    transform: translateX(-50%);
    padding: 2px 10px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--surface-glass-bg);
    backdrop-filter: var(--surface-glass-blur);
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
    cursor: pointer;
  }
  .asked {
    position: absolute;
    top: 8px;
    right: 16px;
    z-index: 1;
    max-width: 85%;
    padding: 8px 12px;
    border: 1px solid var(--color-border);
    /* The user's bubble, where it was. */
    border-radius: 16px;
    border-bottom-right-radius: 8px;
    /* Solid, so the reply scrolling under it doesn't show through; tinted like the user's bubbles. */
    background: color-mix(in srgb, var(--color-action-primary) 12%, var(--color-bg-page));
    box-shadow: var(--shadow-popover);
    color: var(--color-text-primary);
    font: inherit;
    font-size: 0.92rem;
    line-height: 1.55;
    text-align: left;
    cursor: pointer;
  }
  .asked-text {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    overflow: hidden;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .to-bottom:hover {
    color: var(--color-text-primary);
    text-decoration: underline;
  }
  .thread {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
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
    padding: 8px 12px;
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
    width: fit-content;
    padding: 1px 4px;
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-sm, 6px);
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
  .copy {
    position: absolute;
    top: 6px;
    right: 6px;
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.12s ease;
  }
  .copy:hover {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .assistant-bubble:hover .copy,
  .copy:focus-visible,
  .copy.done {
    opacity: 1;
  }
  .assistant-bubble:hover .badge,
  .assistant-bubble:has(.copy:focus-visible) .badge,
  .assistant-bubble:has(.copy.done) .badge {
    opacity: 0;
  }
  /* No hover on a touch screen: it stays. */
  @media (hover: none) {
    .copy {
      opacity: 1;
    }
    .badge {
      display: none;
    }
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
  /* Open, a call is one card: its name on top, then what it was about and what it gave back, each a section. */
  .tool[open] {
    width: min(800px, 100%);
    /* overflow: hidden takes away a flex item's minimum height: without this, the thread, a column that
       scrolls, shrinks the open card to its borders once it's longer than the screen. */
    flex-shrink: 0;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg-hover-ghost);
    overflow: hidden;
  }
  .tool[open] > summary {
    display: flex;
    border: 0;
    border-radius: 0;
    background: none;
  }
  .tool[open] > :not(summary) {
    margin: 0;
    max-width: none;
    border-top: 1px solid var(--color-border);
  }
  .tool[open] > pre {
    border-width: 1px 0 0;
    border-radius: 0;
    background: none;
  }
  .tool[open] > .steps {
    padding: 8px 12px 8px 24px;
    border-left: 0;
  }
  .tool[open] > .thought-text,
  .tool[open] > .carried,
  .tool[open] > .brief-text {
    padding: 10px 12px;
  }
  .tool[open] > .whole-note {
    padding: 6px 12px;
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
  .brief .detail {
    font-family: inherit;
  }
  .thought[open] .preview {
    display: none;
  }
  .notice {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .carried,
  .brief-text {
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
