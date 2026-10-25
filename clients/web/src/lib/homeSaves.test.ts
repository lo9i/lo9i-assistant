import { describe, expect, it } from "vitest";
import type { HomeSection } from "./api/types";
import { HomeSaves } from "./homeSaves.svelte";
import { moved } from "./home";

const section = (id: string) => ({ id, title: id, instructions: "", plugins: [] }) as unknown as HomeSection;

describe("HomeSaves", () => {
  it("builds each change on the last asked for and saves them in order", async () => {
    const sent: string[][] = [];
    const answers: (() => void)[] = [];
    const saves = new HomeSaves(
      (sections) =>
        new Promise((resolve) => {
          sent.push(sections.map((s) => s.id ?? ""));
          answers.push(resolve);
        }),
    );
    const saved = [section("a"), section("b"), section("c")];
    const first = saves.send(moved(saves.latest(saved), "a", 1));
    const second = saves.send(moved(saves.latest(saved), "a", 1));
    expect(saves.latest(saved).map((s) => s.id)).toEqual(["b", "c", "a"]);
    await Promise.resolve();
    expect(sent).toEqual([["b", "a", "c"]]);
    answers[0]();
    await first;
    await Promise.resolve();
    expect(sent).toEqual([
      ["b", "a", "c"],
      ["b", "c", "a"],
    ]);
    answers[1]();
    await second;
    expect(saves.asked).toBeNull();
  });

  it("goes on with the next save when one fails", async () => {
    const sent: number[] = [];
    const saves = new HomeSaves(async (sections) => {
      sent.push(sections.length);
      if (sections.length === 1) throw new Error("no");
    });
    const failed = saves.send([section("a")]);
    const next = saves.send([section("a"), section("b")]);
    await expect(failed).rejects.toThrow("no");
    await next;
    expect(sent).toEqual([1, 2]);
    expect(saves.asked).toBeNull();
  });
});
