// Passkeys in this browser: the daemon's options (JSON, binary values in base64url) as what
// navigator.credentials takes, and the credential it returns as JSON for the daemon to check. Written out rather
// than with PublicKeyCredential.parseCreationOptionsFromJSON and toJSON, which older Safari lacks.
import type { AuthGroup, PasskeysGroup } from "./api/client";
import type { Device, Passkey, PasskeyCeremony } from "./api/types";

// The daemon keeps a ceremony 5 minutes; one older than this is asked for again.
const FRESH_MS = 4 * 60_000;

/** Whether this page can use a passkey: a secure context opened by a host name, as the daemon's are over HTTPS
 * (an IP address can't be a passkey's site). */
export function passkeysWork(where: Location = location): boolean {
  return globalThis.isSecureContext === true && "PublicKeyCredential" in globalThis && !isAddress(where.hostname);
}

/** A ceremony asked for before the user clicks: Safari lets a page ask for a passkey only right after the click,
 * which a request to the daemon in between can outlast. Each one taken asks for the next. */
export class Prepared {
  private ready: { at: number; ceremony: Promise<PasskeyCeremony> } | null = null;

  constructor(
    private readonly start: () => Promise<PasskeyCeremony>,
    private readonly now: () => number = Date.now,
  ) {}

  prepare(): void {
    const ceremony = this.start();
    ceremony.catch(() => undefined); // Taking it reports the error.
    this.ready = { at: this.now(), ceremony };
  }

  take(): Promise<PasskeyCeremony> {
    const ready = this.ready;
    const ceremony = ready && this.now() - ready.at < FRESH_MS ? ready.ceremony : this.start();
    this.prepare();
    return ceremony;
  }
}

/** Adds a passkey for this browser's device; null when the user cancelled. `prepared` asks `passkeys.options`. */
export async function addPasskey(passkeys: PasskeysGroup, prepared: Prepared): Promise<Passkey | null> {
  const { ceremony, options } = await prepared.take();
  const credential = await createPasskey(options);
  return credential && passkeys.add(ceremony, credential);
}

/** Signs this browser in with a passkey, as the device it belongs to; null when the user cancelled. `prepared` asks
 * `auth.passkeyOptions`. */
export async function signInWithPasskey(auth: AuthGroup, prepared: Prepared): Promise<Device | null> {
  const { ceremony, options } = await prepared.take();
  const credential = await usePasskey(options);
  return credential && auth.signInWithPasskey(ceremony, credential);
}

type Signal = (o: { rpId: string; credentialId: string }) => Promise<void>;

/** Tells this browser's password manager that a passkey was removed, so it stops offering it (the WebAuthn Signal
 * API, where the browser has it; elsewhere the user deletes it there). */
export function forgetPasskey(passkey: Pick<Passkey, "id" | "host">): void {
  if (!("PublicKeyCredential" in globalThis)) return;
  const signal = (PublicKeyCredential as unknown as { signalUnknownCredential?: Signal }).signalUnknownCredential;
  void signal?.call(PublicKeyCredential, { rpId: passkey.host, credentialId: passkey.id }).catch(() => undefined);
}

/** Makes a passkey from the daemon's registration options; null when the user cancelled. */
export async function createPasskey(options: Record<string, unknown>): Promise<Record<string, unknown> | null> {
  const made = await asked(() => navigator.credentials.create({ publicKey: creationOptions(options) }));
  return made && registrationJson(made);
}

/** Signs with a passkey for the daemon's sign-in options; null when the user cancelled. */
export async function usePasskey(options: Record<string, unknown>): Promise<Record<string, unknown> | null> {
  const used = await asked(() => navigator.credentials.get({ publicKey: requestOptions(options) }));
  return used && authenticationJson(used);
}

type Descriptor = { id: string; type: PublicKeyCredentialType; transports?: AuthenticatorTransport[] };

export function creationOptions(json: Record<string, unknown>): PublicKeyCredentialCreationOptions {
  const options = json as unknown as PublicKeyCredentialCreationOptions & {
    challenge: string;
    user: { id: string; name: string; displayName: string };
    excludeCredentials?: Descriptor[];
  };
  return {
    ...options,
    challenge: fromBase64url(options.challenge),
    user: { ...options.user, id: fromBase64url(options.user.id) },
    excludeCredentials: options.excludeCredentials?.map(descriptor),
  };
}

export function requestOptions(json: Record<string, unknown>): PublicKeyCredentialRequestOptions {
  const options = json as unknown as PublicKeyCredentialRequestOptions & { challenge: string; allowCredentials?: Descriptor[] };
  return { ...options, challenge: fromBase64url(options.challenge), allowCredentials: options.allowCredentials?.map(descriptor) };
}

export function registrationJson(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    ...common(credential),
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      attestationObject: toBase64url(response.attestationObject),
      transports: response.getTransports?.() ?? [],
    },
  };
}

export function authenticationJson(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    ...common(credential),
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      authenticatorData: toBase64url(response.authenticatorData),
      signature: toBase64url(response.signature),
      userHandle: response.userHandle ? toBase64url(response.userHandle) : undefined,
    },
  };
}

export function toBase64url(data: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(data)))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

export function fromBase64url(text: string): ArrayBuffer {
  const binary = atob(text.replaceAll("-", "+").replaceAll("_", "/"));
  return Uint8Array.from(binary, (c) => c.charCodeAt(0)).buffer;
}

function common(credential: PublicKeyCredential): Record<string, unknown> {
  return {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

function descriptor(d: Descriptor): PublicKeyCredentialDescriptor {
  return { ...d, id: fromBase64url(d.id) };
}

/** The browser's answer, or null when the user closed its dialog (it says NotAllowedError, as for a timeout). */
async function asked(ask: () => Promise<Credential | null>): Promise<PublicKeyCredential | null> {
  try {
    return (await ask()) as PublicKeyCredential | null;
  } catch (e) {
    if (e instanceof DOMException && e.name === "NotAllowedError") return null;
    throw e;
  }
}

function isAddress(host: string): boolean {
  return host.includes(":") || /^[\d.]+$/.test(host);
}
