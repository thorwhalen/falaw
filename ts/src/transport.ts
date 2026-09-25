/**
 * The transport seam: how a `CallPlan` becomes a fal request.
 *
 * A `Transport` takes one call and returns fal's raw response. The default,
 * `queueTransport`, speaks fal's queue API with plain `fetch` — no client library —
 * and has two configurations of one shape:
 *
 * - **through a relay** (`proxyUrl`): every request is POSTed/GETed to the relay with
 *   the real fal URL in `X-Fal-Target-Url` and the caller's key, if any, in `X-Fal-Key`.
 *   This is the protocol `reelee/fal_proxy.py` implements (and what `@fal-ai/client`'s
 *   proxy mode speaks), because fal.ai forbids browser-held keys. With no key the relay
 *   may supply a server-held one and meter the call (reelee#146).
 * - **direct** (no `proxyUrl`): for Node or a server, with `Authorization: Key …`.
 *
 * Replacing the transport is one argument to `execute`; a server endpoint that runs
 * `falaw.execute_plan` on the posted plan is the same seam with a different value.
 */

import { FalError } from './errors';
import type { CallPlan } from './generated/call-plan';

export type Json = Record<string, unknown>;

export interface TransportContext {
  readonly signal?: AbortSignal;
  readonly onEvent?: (event: ProgressEvent) => void;
}

export interface ProgressEvent {
  readonly kind: 'queued' | 'progress' | 'done' | 'error';
  readonly application: string;
  readonly requestId?: string;
  readonly queuePosition?: number;
  readonly status?: string;
  readonly message?: string;
}

export interface TransportResult {
  readonly raw: Json;
  readonly requestId?: string;
}

export type Transport = (call: CallPlan, ctx: TransportContext) => Promise<TransportResult>;

export interface QueueTransportOptions {
  /** The relay endpoint (e.g. `/api/fal/proxy`). Omit to call fal directly (server/Node only). */
  readonly proxyUrl?: string | null;
  /** The caller's fal key, or a getter read per request (so a rotated key applies at once). */
  readonly key?: string | null | (() => string | null | undefined);
  /** fal's queue host (default `https://queue.fal.run`). */
  readonly queueBaseUrl?: string;
  readonly fetch?: typeof globalThis.fetch;
  /** Status poll cadence (default 1000 ms). */
  readonly pollIntervalMs?: number;
  /** Give up waiting for a result after this long (default 10 minutes). */
  readonly timeoutMs?: number;
}

const DFLT_QUEUE_BASE_URL = 'https://queue.fal.run';
const DFLT_POLL_INTERVAL_MS = 1000;
const DFLT_TIMEOUT_MS = 10 * 60 * 1000;

interface QueueSubmission {
  request_id?: string;
  status_url?: string;
  response_url?: string;
}

interface QueueStatus {
  status?: string;
  queue_position?: number;
  response_url?: string;
}

export function queueTransport(opts: QueueTransportOptions = {}): Transport {
  const doFetch = opts.fetch ?? globalThis.fetch;
  const base = (opts.queueBaseUrl ?? DFLT_QUEUE_BASE_URL).replace(/\/$/, '');
  const pollInterval = opts.pollIntervalMs ?? DFLT_POLL_INTERVAL_MS;
  const timeout = opts.timeoutMs ?? DFLT_TIMEOUT_MS;
  const readKey = () => (typeof opts.key === 'function' ? opts.key() : opts.key) ?? null;

  async function request(method: 'GET' | 'POST', target: string, body: unknown, signal?: AbortSignal): Promise<Json> {
    const key = readKey();
    const headers = new Headers({ Accept: 'application/json' });
    if (body !== undefined) headers.set('Content-Type', 'application/json');
    let url = target;
    if (opts.proxyUrl) {
      url = opts.proxyUrl;
      headers.set('X-Fal-Target-Url', target);
      if (key) headers.set('X-Fal-Key', key);
    } else {
      if (!key) throw new FalError('fal needs a key: pass `key`, or route through a relay with `proxyUrl`.');
      headers.set('Authorization', `Key ${key}`);
    }
    let response: Response;
    try {
      response = await doFetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal });
    } catch (e) {
      throw new FalError(`fal request failed: ${(e as Error).message ?? String(e)}`);
    }
    if (!response.ok) throw new FalError(`fal ${method} ${target}: ${await shortBody(response)}`, response.status);
    return (await response.json()) as Json;
  }

  return async (call, ctx) => {
    const { signal } = ctx;
    const submitted = (await request('POST', `${base}/${call.application}`, call.arguments, signal)) as QueueSubmission;
    const requestId = submitted.request_id;
    if (!submitted.status_url || !submitted.response_url) {
      // Some endpoints answer synchronously with the result itself.
      ctx.onEvent?.({ kind: 'done', application: call.application, requestId });
      return { raw: submitted as Json, requestId };
    }
    ctx.onEvent?.({ kind: 'queued', application: call.application, requestId });
    const deadline = Date.now() + timeout;
    for (;;) {
      const status = (await request('GET', submitted.status_url, undefined, signal)) as QueueStatus;
      ctx.onEvent?.({
        kind: 'progress',
        application: call.application,
        requestId,
        status: status.status,
        queuePosition: status.queue_position,
      });
      if (status.status === 'COMPLETED') break;
      if (status.status && status.status !== 'IN_QUEUE' && status.status !== 'IN_PROGRESS') {
        throw new FalError(`fal request ${requestId ?? ''} ended with status ${status.status}`);
      }
      if (Date.now() > deadline) throw new FalError(`fal request ${requestId ?? ''} timed out after ${timeout} ms`);
      await sleep(pollInterval, signal);
    }
    const raw = await request('GET', submitted.response_url, undefined, signal);
    ctx.onEvent?.({ kind: 'done', application: call.application, requestId });
    return { raw, requestId };
  };
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError(signal));
    const t = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(t);
      reject(abortError(signal!));
    }
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function abortError(signal: AbortSignal): Error {
  return signal.reason instanceof Error ? signal.reason : new FalError('fal request aborted');
}

async function shortBody(response: Response): Promise<string> {
  try {
    const text = (await response.text()).trim();
    return text.length > 300 ? `${text.slice(0, 300)}…` : text || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}
