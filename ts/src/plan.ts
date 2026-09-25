/**
 * Plans — pure data describing what *would* be called and what it would cost.
 * The TS twin of `falaw.plan` + `falaw.operations._plan`, in the same wire shape
 * `call_plan_to_dict` / `plan_to_dict` produce, so a plan built here can be sent
 * to a server that runs `falaw.execute_plan` unchanged (metered billing, reelee#146).
 *
 * `cache_status` is always `"unknown"`: a browser has no falaw cache to peek.
 */

import { canonicalBlob, ensureCanonical, planIdentityPayload, sha256Hex } from './canonical';
import { catalogueCostBasis, estimateCallCost, type CostBasis } from './cost';
import { CONSTANTS } from './generated/constants';
import type { CallPlan } from './generated/call-plan';
import type { ModelRecord } from './generated/model-record';
import { getModel, pickModel } from './registry';

export type { CallPlan };
export type OutputKind = CallPlan['output_kind'];

/** The wire form of a whole plan (`falaw.plan_to_dict`). */
export interface Plan {
  readonly schema: string;
  readonly calls: readonly CallPlan[];
}

export interface MakeCallPlanOptions {
  readonly tool: string;
  readonly application: string;
  readonly arguments: Readonly<Record<string, unknown>>;
  readonly outputKind: OutputKind;
  readonly backend?: string;
  readonly estimatedCostUsd?: number | null;
  readonly expectedDurationS?: readonly [number, number] | null;
  readonly metadata?: Readonly<Record<string, unknown>> | null;
  readonly costBasis?: CostBasis | null;
}

/** Build a `CallPlan`, refusing non-canonical arguments while planning is still free. */
export function makeCallPlan(opts: MakeCallPlanOptions): CallPlan {
  ensureCanonical({ ...opts.arguments }, 'arguments');
  const plan: CallPlan = {
    tool: opts.tool,
    application: opts.application,
    backend: opts.backend ?? CONSTANTS.dflt_backend,
    arguments: { ...opts.arguments },
    output_kind: opts.outputKind,
    estimated_cost_usd: opts.estimatedCostUsd ?? null,
    cache_status: 'unknown',
    expected_duration_s: opts.expectedDurationS ? [...opts.expectedDurationS] : null,
    metadata: { ...(opts.metadata ?? {}) },
    key_extra: {},
    // Python omits the key when unset; `null` here parses identically on that side
    // (`call_plan_from_dict`) and keeps the TS type one shape. Never hashed either way.
    cost_basis: opts.costBasis ?? null,
  };
  return plan;
}

function resolveModel(modelId: string | undefined, category: string, qualityTier: string): ModelRecord {
  return modelId ? getModel(modelId) : pickModel({ category, qualityTier });
}

export interface GenerateImageInput {
  readonly prompt: string;
  /** `fast` | `balanced` | `high` | `ultra` (default `balanced`). */
  readonly quality?: string;
  /** fal's image_size vocabulary (default `landscape_4_3`). */
  readonly imageSize?: string;
  /** A catalogue id or alias; overrides the quality pick. */
  readonly modelId?: string;
  /** Model-specific arguments merged over the standard ones (seed, guidance_scale, …). */
  readonly extra?: Readonly<Record<string, unknown>>;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

/** Plan a text-to-image call (`falaw.plan_generate_image`). */
export function planGenerateImage(input: GenerateImageInput): CallPlan {
  const record = resolveModel(input.modelId, 'image', input.quality ?? 'balanced');
  return makeCallPlan({
    tool: 'generate_image',
    application: record.id,
    arguments: { prompt: input.prompt, image_size: input.imageSize ?? 'landscape_4_3', ...(input.extra ?? {}) },
    outputKind: 'image',
    estimatedCostUsd: estimateCallCost(record),
    metadata: input.metadata,
    costBasis: catalogueCostBasis(record.id),
  });
}

export interface ImageToVideoInput {
  /** The still to animate — a URL, or `"<from N>"` to chain onto call N of the same plan. */
  readonly imageUrl: string;
  readonly prompt?: string;
  /** default `high` */
  readonly quality?: string;
  readonly modelId?: string;
  /** Used only to price a `per_second` model; not sent to fal unless you put it in `extra`. */
  readonly durationS?: number | null;
  readonly extra?: Readonly<Record<string, unknown>>;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

/** Plan an image-to-video call (`falaw.plan_image_to_video`). */
export function planImageToVideo(input: ImageToVideoInput): CallPlan {
  const record = resolveModel(input.modelId, 'image_to_video', input.quality ?? 'high');
  const args: Record<string, unknown> = { image_url: input.imageUrl, ...(input.extra ?? {}) };
  if (input.prompt) args.prompt = input.prompt;
  return makeCallPlan({
    tool: 'image_to_video',
    application: record.id,
    arguments: args,
    outputKind: 'video',
    estimatedCostUsd: estimateCallCost(record, { seconds: input.durationS ?? null }),
    metadata: input.metadata,
    costBasis: catalogueCostBasis(record.id, { seconds: input.durationS ?? null }),
  });
}

export function makePlan(calls: readonly CallPlan[]): Plan {
  return { schema: CONSTANTS.plan_dict_schema, calls: [...calls] };
}

/** Sum of the known per-call estimates; calls with unknown cost contribute nothing —
 *  read `hasUnknownCosts` before trusting the total as a ceiling. */
export function totalCostUsd(plan: Plan): number {
  return plan.calls.reduce((sum, c) => sum + (c.estimated_cost_usd ?? 0), 0);
}

export function hasUnknownCosts(plan: Plan): boolean {
  return plan.calls.some((c) => c.estimated_cost_usd == null && c.cache_status !== 'hit');
}

/** Structural idempotency key for a whole plan, byte-compatible with Python's `plan_hash`. */
export async function planHash(plan: Plan): Promise<string> {
  const blob = canonicalBlob(
    plan.calls.map((c) =>
      planIdentityPayload(c.application, c.arguments, {
        tool: c.tool,
        backend: c.backend,
        keyExtra: c.key_extra && Object.keys(c.key_extra).length ? c.key_extra : null,
      }),
    ),
  );
  return sha256Hex(blob);
}
