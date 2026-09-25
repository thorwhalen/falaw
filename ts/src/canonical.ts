/**
 * One canonical byte-form for everything falaw hashes — the TS twin of `falaw.canonical`.
 *
 * `canonicalBlob` reproduces Python's `json.dumps(payload, sort_keys=True, allow_nan=False)`
 * byte for byte: keys sorted by code point at every depth, `", "` and `": "` separators,
 * every non-ASCII and control character escaped as `\uXXXX` (lower-case hex, surrogate
 * pairs for astral characters), and **no "give up quietly" branch** — anything JSON cannot
 * represent faithfully throws `FalNonCanonicalArgument`, so the failure is a diagnosable
 * refusal at plan time rather than a wrong artifact at collect time.
 *
 * The one known divergence, recorded in the decision record: a number with an integral
 * value serialises as `1` here and as `1.0` in Python when Python holds a float. Every
 * planner on either side emits ints for integral quantities, and `schema/fixtures/canonical.json`
 * pins the rest.
 */

import { FalNonCanonicalArgument } from './errors';
import { CONSTANTS } from './generated/constants';

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export const DFLT_BACKEND: string = CONSTANTS.dflt_backend;

/** Throw unless `payload` is canonical JSON: finite numbers, strings, booleans, null,
 *  arrays and plain objects, recursively. `undefined` anywhere is a refusal. */
export function ensureCanonical(payload: unknown, context = 'arguments'): void {
  const offender = firstOffender(payload, context);
  if (offender) {
    const [path, why] = offender;
    throw new FalNonCanonicalArgument(
      `${path}: ${why}. Cache keys and plan hashes require JSON-native values — convert at the plan* boundary and say what you mean.`,
      path,
    );
  }
}

function firstOffender(value: unknown, path: string): [string, string] | null {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return null;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? null : [path, `non-finite number ${String(value)}`];
  }
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      const found = firstOffender(value[i], `${path}[${i}]`);
      if (found) return found;
    }
    return null;
  }
  if (isPlainObject(value)) {
    for (const [k, v] of Object.entries(value)) {
      const found = firstOffender(v, `${path}.${k}`);
      if (found) return found;
    }
    return null;
  }
  const kind = value === undefined ? 'undefined' : typeof value === 'object' ? (value as object).constructor?.name ?? 'object' : typeof value;
  return [path, `${kind} is not JSON-native`];
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/** The blob falaw hashes, as a string of ASCII (encode as UTF-8 for the digest). */
export function canonicalBlob(payload: unknown): string {
  ensureCanonical(payload, 'payload');
  return serialize(payload as Json);
}

function serialize(value: Json): string {
  if (value === null) return 'null';
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (typeof value === 'number') return serializeNumber(value);
  if (typeof value === 'string') return serializeString(value);
  if (Array.isArray(value)) return value.length ? `[${value.map(serialize).join(', ')}]` : '[]';
  const keys = Object.keys(value).sort(compareCodePoints);
  return keys.length ? `{${keys.map((k) => `${serializeString(k)}: ${serialize(value[k]!)}`).join(', ')}}` : '{}';
}

function serializeNumber(n: number): string {
  // Python's repr(float) and JS's Number#toString agree on the shortest round-trip digits;
  // they differ only in exponent thresholds (Python switches at 1e16, JS at 1e21), which no
  // planner argument reaches. Integral values are the documented divergence (module docstring).
  return String(n);
}

/** Python's `ensure_ascii=True` escaping: everything outside `' '..'~'` becomes `\uXXXX`. */
function serializeString(s: string): string {
  let out = '"';
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i);
    const ch = s[i]!;
    if (ch === '"') out += '\\"';
    else if (ch === '\\') out += '\\\\';
    else if (ch === '\n') out += '\\n';
    else if (ch === '\r') out += '\\r';
    else if (ch === '\t') out += '\\t';
    else if (ch === '\b') out += '\\b';
    else if (ch === '\f') out += '\\f';
    else if (code < 0x20 || code > 0x7e) out += `\\u${code.toString(16).padStart(4, '0')}`;
    else out += ch;
  }
  return `${out}"`;
}

function compareCodePoints(a: string, b: string): number {
  const ia = a[Symbol.iterator]();
  const ib = b[Symbol.iterator]();
  for (;;) {
    const na = ia.next();
    const nb = ib.next();
    if (na.done && nb.done) return 0;
    if (na.done) return -1;
    if (nb.done) return 1;
    const ca = na.value.codePointAt(0)!;
    const cb = nb.value.codePointAt(0)!;
    if (ca !== cb) return ca - cb;
  }
}

/** SHA-256 of the UTF-8 bytes of `text`, as lower-case hex (WebCrypto; browsers and Node ≥ 19). */
export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

export interface IdentityOptions {
  readonly backend?: string;
  readonly keyExtra?: Readonly<Record<string, unknown>> | null;
}

/** `{app, args}` — what the per-call content-addressed cache keys on.
 *  `backend` joins only when non-default; `key_extra` only when non-empty. */
export function cacheKeyPayload(
  application: string,
  args: Readonly<Record<string, unknown>>,
  opts: IdentityOptions = {},
): Record<string, unknown> {
  const payload: Record<string, unknown> = { app: application, args: { ...args } };
  const backend = opts.backend ?? DFLT_BACKEND;
  if (backend !== DFLT_BACKEND) payload.backend = backend;
  if (opts.keyExtra && Object.keys(opts.keyExtra).length) payload.key_extra = { ...opts.keyExtra };
  return payload;
}

/** `{app, args, tool}` — the structural form behind `plan_hash`. */
export function planIdentityPayload(
  application: string,
  args: Readonly<Record<string, unknown>>,
  opts: IdentityOptions & { readonly tool: string | null },
): Record<string, unknown> {
  const payload: Record<string, unknown> = { app: application, args: { ...args }, tool: opts.tool };
  const backend = opts.backend ?? DFLT_BACKEND;
  if (backend !== DFLT_BACKEND) payload.backend = backend;
  if (opts.keyExtra && Object.keys(opts.keyExtra).length) payload.key_extra = { ...opts.keyExtra };
  return payload;
}
