// @vitest-environment jsdom
// DOMPurify cleans with a DOM, which jsdom gives the renderer here.
import { describe, expect, it } from "vitest";
import { APP_POLICY, APP_SANDBOX, appDocument, appHeight } from "./htmlApp";
import { markdownParts } from "./markdown";
import framePage from "../../static/html-app.html?raw";

const APP = '<!doctype html><html><body><button onclick="n++">+</button><script>let n = 0</script></body></html>';

describe("markdownParts", () => {
  it("takes a closed html-app block out as an app, around Markdown rendered as before", () => {
    const parts = markdownParts(`Here:\n\n\`\`\`html-app\n${APP}\n\`\`\`\n\nDone.`);
    expect(parts.map((part) => part.kind)).toEqual(["html", "app", "html"]);
    expect(parts[1]).toEqual({ kind: "app", source: APP });
    expect(parts[2]).toEqual({ kind: "html", html: "<p>Done.</p>\n" });
  });

  it("shows a block still streaming as code, its HTML escaped", () => {
    const parts = markdownParts(`Here:\n\n\`\`\`html-app\n${APP}\n`);
    expect(parts).toHaveLength(1);
    const [part] = parts;
    expect(part.kind === "html" && part.html).toContain('<code class="language-html-app">&lt;!doctype html&gt;');
  });

  it("keeps a fence that only looks closed, or is shorter than its opening, open", () => {
    expect(markdownParts("````html-app\n<p>x</p>\n```\n")[0].kind).toBe("html");
    expect(markdownParts("```html-app\n```")[0].kind).toBe("app");
  });

  it("still sanitizes the reply's own HTML", () => {
    const parts = markdownParts('<img src="x" onerror="alert(1)"><script>alert(2)</script><iframe src="https://x"></iframe>');
    const html = parts.map((part) => (part.kind === "html" ? part.html : "")).join("");
    expect(html).toContain("<img");
    expect(html).not.toMatch(/onerror|<script|<iframe/);
  });
});

describe("appDocument", () => {
  it("puts the policy before anything of the app's, which can't close it or end the document early", () => {
    const sneaky = '"></meta><meta http-equiv="Content-Security-Policy" content="default-src *"><script>fetch("//x")</script>';
    const shown = appDocument(sneaky, "light");
    const written = new DOMParser().parseFromString(shown, "text/html");
    const policies = [...written.querySelectorAll('meta[http-equiv="Content-Security-Policy"]')];
    // A second policy of the app's only narrows what the first allows; the first is ours, whole.
    expect(policies[0].getAttribute("content")).toBe(APP_POLICY);
    expect(shown.indexOf(APP_POLICY)).toBeLessThan(shown.indexOf(sneaky));
    expect(written.documentElement.outerHTML).toContain("color-scheme:light");
  });

  it("allows no network and nothing but scripts in the sandbox", () => {
    expect(APP_POLICY).toMatch(/^default-src 'none';/);
    expect(APP_POLICY).not.toMatch(/connect-src|https?:|\*/);
    expect(APP_SANDBOX).toBe("allow-scripts");
  });

  it("is written by a frame page that declares the same policy", () => {
    expect(framePage).toContain(`content="${APP_POLICY}"`);
    expect(framePage).toContain("event.source !== parent");
  });
});

describe("appHeight", () => {
  it("takes only the frame's height report, within bounds", () => {
    expect(appHeight({ lo9iAppHeight: 412.4 })).toBe(412);
    expect(appHeight({ lo9iAppHeight: 99999 })).toBe(900);
    expect(appHeight({ lo9iAppHeight: -5 })).toBe(60);
    expect(appHeight({ lo9iAppHeight: Number.NaN })).toBeNull();
    expect(appHeight({ lo9iAppHeight: "500" })).toBeNull();
    expect(appHeight("500")).toBeNull();
    expect(appHeight(null)).toBeNull();
  });
});
