import { describe, expect, it } from "vitest";
import { NoticeBoard } from "./notices";

describe("NoticeBoard", () => {
  it("keeps what a notice offers to do", () => {
    const board = new NoticeBoard();
    let opened = false;
    board.notify("✅ photos: done", "info", { label: "Open its conversation", run: () => (opened = true) });
    const [notice] = board.getSnapshot();
    notice.action?.run();
    expect([notice.action?.label, opened]).toEqual(["Open its conversation", true]);
  });
});
