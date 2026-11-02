import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthGroup, PasskeysGroup } from "./api/client";
import {
  addPasskey,
  authenticationJson,
  creationOptions,
  fromBase64url,
  passkeysWork,
  Prepared,
  registrationJson,
  requestOptions,
  signInWithPasskey,
  toBase64url,
} from "./passkeys";

const bytes = (...values: number[]): ArrayBuffer => new Uint8Array(values).buffer;
const where = (hostname: string) => ({ hostname }) as Location;

function credential(response: object): PublicKeyCredential {
  return {
    id: "AQID",
    rawId: bytes(1, 2, 3),
    type: "public-key",
    authenticatorAttachment: "platform",
    response,
    getClientExtensionResults: () => ({}),
  } as unknown as PublicKeyCredential;
}

afterEach(() => vi.unstubAllGlobals());

describe("base64url", () => {
  it("round-trips bytes without padding or + and /", () => {
    const data = bytes(251, 255, 191, 0, 1);
    const text = toBase64url(data);
    expect(text).toBe("-_-_AAE");
    expect(new Uint8Array(fromBase64url(text))).toEqual(new Uint8Array(data));
  });
});

describe("passkeysWork", () => {
  it("needs a secure page opened by a host name", () => {
    vi.stubGlobal("isSecureContext", true);
    vi.stubGlobal("PublicKeyCredential", class {});
    expect(passkeysWork(where("lo9i.example.com"))).toBe(true);
    expect(passkeysWork(where("192.168.0.33"))).toBe(false);
    expect(passkeysWork(where("[::1]"))).toBe(false);
    vi.stubGlobal("isSecureContext", false);
    expect(passkeysWork(where("lo9i.example.com"))).toBe(false);
  });
});

describe("options", () => {
  it("turn the daemon's base64url values into bytes", () => {
    const created = creationOptions({
      rp: { id: "lo9i.example.com", name: "lo9i" },
      user: { id: "YWJj", name: "Safari on iOS", displayName: "Safari on iOS" },
      challenge: "AQID",
      pubKeyCredParams: [{ type: "public-key", alg: -7 }],
      excludeCredentials: [{ id: "BAU", type: "public-key" }],
    });
    expect(new Uint8Array(created.challenge as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]));
    expect(new TextDecoder().decode(created.user.id as ArrayBuffer)).toBe("abc");
    expect(new Uint8Array(created.excludeCredentials![0].id as ArrayBuffer)).toEqual(new Uint8Array([4, 5]));
    const requested = requestOptions({ challenge: "AQID", rpId: "lo9i.example.com", userVerification: "required" });
    expect(requested.rpId).toBe("lo9i.example.com");
    expect(requested.allowCredentials).toBeUndefined();
  });
});

describe("credentials", () => {
  it("go back as JSON with base64url values", () => {
    const made = registrationJson(credential({ clientDataJSON: bytes(1), attestationObject: bytes(2), getTransports: () => ["internal"] }));
    expect(made).toMatchObject({
      id: "AQID",
      rawId: "AQID",
      type: "public-key",
      response: { clientDataJSON: "AQ", attestationObject: "Ag", transports: ["internal"] },
    });
    const used = authenticationJson(
      credential({ clientDataJSON: bytes(1), authenticatorData: bytes(2), signature: bytes(3), userHandle: bytes(4) }),
    );
    expect(used.response).toEqual({ clientDataJSON: "AQ", authenticatorData: "Ag", signature: "Aw", userHandle: "BA" });
  });
});

describe("ceremonies", () => {
  const options = { challenge: "AQID", rpId: "localhost" };

  it("send the browser's answer for the ceremony they started", async () => {
    const get = vi.fn(async () =>
      credential({ clientDataJSON: bytes(1), authenticatorData: bytes(2), signature: bytes(3), userHandle: null }),
    );
    vi.stubGlobal("navigator", { credentials: { get } });
    const auth = {
      passkeyOptions: vi.fn(async () => ({ ceremony: "c1", options })),
      signInWithPasskey: vi.fn(async () => ({ id: "d1" })),
    };
    const prepared = new Prepared(auth.passkeyOptions);
    prepared.prepare();
    expect(await signInWithPasskey(auth as unknown as AuthGroup, prepared)).toEqual({ id: "d1" });
    expect(auth.signInWithPasskey).toHaveBeenCalledWith("c1", expect.objectContaining({ rawId: "AQID" }));
  });

  it("send nothing when the user closes the browser's dialog", async () => {
    const create = vi.fn(async () => {
      throw new DOMException("cancelled", "NotAllowedError");
    });
    vi.stubGlobal("navigator", { credentials: { create } });
    const passkeys = {
      options: vi.fn(async () => ({ ceremony: "c2", options: { ...options, user: { id: "YQ" } } })),
      add: vi.fn(),
    };
    expect(await addPasskey(passkeys as unknown as PasskeysGroup, new Prepared(passkeys.options))).toBeNull();
    expect(passkeys.add).not.toHaveBeenCalled();
  });

  it("are asked for before the click, and again once taken or stale", async () => {
    let now = 0;
    let asked = 0;
    const prepared = new Prepared(
      async () => ({ ceremony: `c${++asked}`, options }),
      () => now,
    );
    prepared.prepare();
    expect((await prepared.take()).ceremony).toBe("c1");
    expect(asked).toBe(2);
    now = 5 * 60_000;
    expect((await prepared.take()).ceremony).toBe("c3");
  });
});
