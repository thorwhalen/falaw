/**
 * Cost rules — the TS twin of `falaw.cost.estimate_call_cost` and the catalogue cost basis.
 *
 * `null` means **unknown**, never free: a `per_second` call with no duration is unpriceable,
 * and returning `0` would let a budget gate wave through the most expensive thing fal bills
 * for. `per_megapixel` alone has a house default (`CONSTANTS.default_megapixels`).
 */

import { CONSTANTS } from './generated/constants';
import type { CallPlan } from './generated/call-plan';
import type { ModelRecord } from './generated/model-record';
import { MODELS_TABLE_VERSION } from './generated/models';

export type CostBasis = NonNullable<CallPlan['cost_basis']>;

export interface CostHints {
  readonly count?: number;
  readonly seconds?: number | null;
  readonly megapixels?: number | null;
  readonly tokens?: number | null;
}

export function estimateCallCost(record: Pick<ModelRecord, 'cost_estimate'>, hints: CostHints = {}): number | null {
  const ce = record.cost_estimate;
  if (!ce) return null;
  const count = hints.count ?? 1;
  switch (ce.kind) {
    case 'per_call':
    case 'per_image':
      return ce.amount * count;
    case 'per_second':
      if (hints.seconds == null) return null; // unknown duration → unpriceable, NOT free
      return ce.amount * hints.seconds * count;
    case 'per_megapixel': {
      const mp = hints.megapixels ?? CONSTANTS.default_megapixels;
      return ce.amount * mp * count;
    }
    case 'per_token':
      if (hints.tokens == null) return null;
      return ce.amount * hints.tokens * count;
    default:
      return null;
  }
}

/** The basis for a call priced from the catalogue: which record, which quantities,
 *  which table and which version of it — enough to re-quote later. `null` hints are
 *  dropped, as on the Python side (absent is what the estimator saw). */
export function catalogueCostBasis(modelId: string, quantities: Omit<CostHints, 'count'> = {}): CostBasis {
  const supplied: Record<string, number> = {};
  for (const [k, v] of Object.entries(quantities)) if (v != null) supplied[k] = v;
  return {
    pricer: CONSTANTS.catalogue_pricer,
    priced: modelId,
    quantities: supplied,
    table: CONSTANTS.model_catalogue_table,
    table_version: MODELS_TABLE_VERSION,
  };
}
