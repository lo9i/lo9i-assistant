<script lang="ts">
  import { changeLetter, type Mark } from "$lib/chat/folderChanges";
  import { t } from "$lib/i18n.svelte";

  // A change git sees, beside a file's name as git's short status writes it (M, A, D, U); a dot beside a folder
  // with changes inside.
  let { mark }: { mark: Mark } = $props();
</script>

<span class="mark mark--{mark}" title={t(`handedFolder.status.${mark}`)} aria-label={t(`handedFolder.status.${mark}`)}
  >{mark === "inside" ? "•" : changeLetter(mark)}</span
>

<style>
  .mark {
    flex: none;
    min-width: 1.2em;
    text-align: center;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 700;
    color: var(--tone);
  }
  .mark--modified {
    --tone: var(--color-warn);
  }
  .mark--added,
  .mark--untracked {
    --tone: var(--color-success);
  }
  .mark--deleted {
    --tone: var(--color-danger);
  }
  .mark--inside {
    --tone: var(--color-warn);
  }
</style>
