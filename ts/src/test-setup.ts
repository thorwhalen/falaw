// The offline guard: no vitest test ever reaches the network.
//
// `queueTransport` defaults to `globalThis.fetch`, and Node has a real one, so a test that
// forgets to inject a fake would submit a real, billable job and could still pass.
import { beforeAll } from 'vitest';

beforeAll(() => {
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    throw new Error(`offline test tried to fetch ${String(input)} — inject a fake \`fetch\``);
  }) as typeof globalThis.fetch;
});
