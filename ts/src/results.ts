/**
 * Best-effort parser over the common fal response shapes — the TS twin of
 * `falaw.results.parse_response`. Unknown shapes pass through as `raw` only.
 */

import { CONSTANTS } from './generated/constants';
import type { Asset, Result } from './generated/result';

export type { Asset, Result };
export type Json = Record<string, unknown>;

const KIND_KEYS: readonly (readonly [string, string])[] = CONSTANTS.kind_keys.map(([k, v]) => [k, v] as const);

export function parseResponse(raw: unknown, ctx: { application: string; arguments: Readonly<Record<string, unknown>> }): Result {
  const assets: Asset[] = [];
  if (isObject(raw)) {
    for (const [key, kind] of KIND_KEYS) {
      const val = raw[key];
      if (val === null || val === undefined) continue;
      for (const item of Array.isArray(val) ? val : [val]) assets.push(toAsset(item, kind));
    }
  }
  return {
    assets,
    raw: isObject(raw) ? raw : {},
    application: ctx.application,
    arguments: { ...ctx.arguments },
  };
}

const ASSET_KEYS = new Set(['url', 'content_type', 'width', 'height', 'duration']);

function toAsset(item: unknown, kind: string): Asset {
  if (typeof item === 'string') return { url: item, kind, content_type: '', width: 0, height: 0, duration_s: 0, metadata: {} };
  if (isObject(item)) {
    const metadata: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(item)) if (!ASSET_KEYS.has(k)) metadata[k] = v;
    return {
      url: typeof item.url === 'string' ? item.url : '',
      kind,
      content_type: typeof item.content_type === 'string' ? item.content_type : '',
      width: toInt(item.width),
      height: toInt(item.height),
      duration_s: toFloat(item.duration),
      metadata,
    };
  }
  return { url: String(item), kind, content_type: '', width: 0, height: 0, duration_s: 0, metadata: {} };
}

/** Python's `int(x or 0)`. */
function toInt(v: unknown): number {
  if (!v) return 0;
  const n = Math.trunc(Number(v));
  return Number.isFinite(n) ? n : 0;
}

/** Python's `float(x or 0)`. */
function toFloat(v: unknown): number {
  if (!v) return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function isObject(v: unknown): v is Json {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}
