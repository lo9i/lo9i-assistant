// Home's sections as the user changes them: each change sends the whole list, so the next one has to build on the
// last asked for, not on the last the daemon answered with.
import type { HomeSection } from "./api/types";

export class HomeSaves {
  /** The list last asked for, until every save has been answered; null when none is on its way. */
  asked = $state<HomeSection[] | null>(null);
  private pending = 0;
  private queue: Promise<unknown> = Promise.resolve();

  constructor(private readonly save: (sections: HomeSection[]) => Promise<void>) {}

  /** What the next change builds on: the list last asked for, or `saved` when nothing is on its way. */
  latest(saved: HomeSection[]): HomeSection[] {
    return this.asked ?? saved;
  }

  /** Saves go one at a time, in the order asked, so the last answer shown is the last list asked for. */
  send(sections: HomeSection[]): Promise<void> {
    this.asked = sections;
    this.pending++;
    const sent = this.queue.then(() => this.save(sections)).finally(() => this.settled());
    this.queue = sent.catch(() => {});
    return sent;
  }

  private settled(): void {
    if (--this.pending === 0) this.asked = null;
  }
}
