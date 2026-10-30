# WEB.md

Conventions for the web UI (SvelteKit, `web/`).

## Default page layout: list and details

A page that shows a collection (jobs, conversations, devices) uses the list-and-details layout.
References: `src/routes/jobs/+page.svelte`, `src/routes/devices/+page.svelte`,
`src/routes/conversations/+page.svelte`.

- `TopBar` with the page title. The page's main action (New conversation, Pair a browser) goes in
  its `actions` snippet as a `btn--primary` with an icon, its label wrapped in `hide-narrow`.
- `.screen`: a row as tall as the viewport below the top bar (`height: calc(100dvh - 76px)`,
  `max-width: 1600px`, centered, `padding: 0 16px 16px` so content starts right under the title, 16px gap) with `align-items: flex-start`, so cards take
  the height of their content. The table card has `max-height: 100%`, so a long list scrolls inside
  it. A details column that needs room (messages, run history) gets `align-self: stretch`.
- Left, three quarters of the width (`flex: 3 1 0`): a `table-card surface--glass` with a `toolbar`
  header (`text-heading` title, a `text-meta` line ending in "Click one to see it on the right.",
  and a count `pill`), then a `scroll` area holding a `data-table` with a sticky header.
- Rows are selectable: clicking a row picks it, the picked row has the `selected` style (tinted,
  accent bar on the left). Until the user picks one, select a sensible default (this browser, this
  tab's conversation, the first job).
- Right, one quarter (`flex: 1 1 0`): a column of `details surface--glass` cards for the selected
  item: `text-heading` title with its status or toggle, a `dl` of `micro-label` terms with values
  right-aligned, then its actions (`btn--sm`; destructive ones `btn--danger` and confirmed with
  `Confirm`). Transient panels (a pairing code) go above the details card in this column.
- Empty and error states: `EmptyState` with an icon in the table and in the details column;
  load errors as `error-text pad`.
- Narrow screens: below 900px the screen stacks (`flex-direction: column; align-items: stretch;
height: auto`) and both parts get `flex: none`, so each takes its own height and the page scrolls. Columns that the
  details card also shows get `hide-narrow`.

Chat (`src/routes/conversations/+page.svelte`) is this layout with a message box above it: the screen is
a column, the box first, then the list and details in a row (`.lists`) that takes the rest.

The conversation page (`src/routes/conversations/open`, `src/lib/ui/chat/board/Columns.svelte`) shows several
conversations side by side, where the user is when they want a second one: Open beside in its top bar picks one
(`BesidePicker.svelte`), the sidebar's conversations have Open beside and can be dragged onto the page, and a card's
Open beside goes there too (`openConversation.ts::openBeside`). Up to three columns, each a whole `ChatPanel` on a
conversation open in the tab (`OpenChats.opened`): resized by dragging the dividers, reordered by their headers, closed,
any one full screen until its button or Esc. The column the user is in is the conversation shown, which the top bar and
the sidebar name; showing one that isn't a column shows it alone, and the columns come back with one of them. Below
900px one shows at a time, picked from tabs. Chat's list also shows the conversations as cards (its top bar's List /
Cards, `ConversationBoard.svelte`): each card has its last messages, a live status and a small composer, reorders by
dragging and shows full screen. The rules are pure functions (`src/lib/chat/cardLayout.ts`: `columnsOf`, `besideOf`),
the layout kept per browser (`src/lib/conversationLayout.svelte.ts`).

Home (`src/routes/home/+page.svelte`) is a grid of cards, one per section, saved by the daemon with their order and
width: a card moves by dragging its header or with its arrows (for keyboards and phones), resizes by dragging its
right edge, and shows full screen with its button until pressed again or Esc (`src/lib/fullScreen.ts`; a full-screen
card is drawn outside the grid, whose container query would hold it). The Conversations card (`CONVERSATIONS`) is
drawn live instead of from its result (`src/lib/ui/home/HomeConversations.svelte`): the conversations pinned to Home,
or the most recent while none is (`src/lib/homeConversations.ts`); removed, the editor of a new section offers it
back. Pin to Home (`PinToHome.svelte`, `homePins()`)
sits on every conversation: the list's details, its card and pane, the open conversation's top bar.

Settings-style forms (connecting a service, preferences) stay as cards in the settings page grid.

## Text and languages

The app's own text is in English and Spanish (`src/lib/i18n.svelte.ts`). No text a user reads is written in a
component: each is a key in `src/lib/locales/en.json` and `es.json`, shown with `t("area.key", { name: value })`.
Keys are typed from `en.json`, so `npm run check` fails on one that doesn't exist; `src/lib/i18n.test.ts` fails when
a key is in one file and not the other, or their placeholders differ. A text with a count is an object of plural
forms (`one`, `other`), picked by `count`. A list of labels keeps keys (`Key`) and calls `t` where it renders, so
the page follows a language change at once. Dates, numbers and lists go through `formatDate`, `formatNumber`,
`formatList` and `languageName`, never `toLocaleString()` or a fixed locale. Text the daemon sends (errors, plugin
descriptions, notifications) shows as it comes.
