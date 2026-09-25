// execute() and the queue transport against fakes: no test ever hits the network.

import { describe, expect, it } from 'vitest';

import { FalError } from './errors';
import { execute } from './execute';
import { makePlan, planGenerateImage, planImageToVideo } from './plan';
import { type Transport, queueTransport } from './transport';

describe('execute', () => {
  it('runs calls in order, parses results, and chains "<from N>" by the upstream asset URL', async () => {
    const seen: string[] = [];
    const transport: Transport = async (call) => {
      seen.push(`${call.tool}:${JSON.stringify(call.arguments)}`);
      return call.output_kind === 'image'
        ? { raw: { images: [{ url: 'https://v3.fal.media/still.png', width: 1024, height: 768 }], seed: 1 }, requestId: 'r1' }
        : { raw: { video: { url: 'https://v3.fal.media/clip.mp4', duration: 6 } }, requestId: 'r2' };
    };
    const plan = makePlan([
      planGenerateImage({ prompt: 'a tiger eye' }),
      planImageToVideo({ imageUrl: '<from 0>', prompt: 'push in', durationS: 6 }),
    ]);
    const done = await execute(plan, { transport });
    expect(done).toHaveLength(2);
    expect(done[0]!.result.assets[0]!.url).toBe('https://v3.fal.media/still.png');
    expect(done[1]!.sent.arguments.image_url).toBe('https://v3.fal.media/still.png');
    expect(done[1]!.call.arguments.image_url).toBe('<from 0>'); // the plan itself is untouched
    expect(done[1]!.result.assets[0]!.kind).toBe('video');
    expect(done.map((d) => d.requestId)).toEqual(['r1', 'r2']);
    expect(seen[1]).toContain('still.png');
  });

  it('refuses a placeholder whose upstream has not run or produced nothing', async () => {
    const transport: Transport = async () => ({ raw: { images: [] } });
    await expect(execute([planImageToVideo({ imageUrl: '<from 0>' })], { transport })).rejects.toThrow(/has not run/);
    await expect(
      execute(makePlan([planGenerateImage({ prompt: 'x' }), planImageToVideo({ imageUrl: '<from 0>' })]), { transport }),
    ).rejects.toThrow(/no asset/);
  });
});

/** A fetch that plays fal's queue protocol: submit → status (twice) → response. */
function fakeQueue() {
  const calls: { url: string; method: string; headers: Headers; body: string | null }[] = [];
  let polls = 0;
  const fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const headers = new Headers(init?.headers);
    calls.push({ url, method: init?.method ?? 'GET', headers, body: (init?.body as string | undefined) ?? null });
    const target = headers.get('x-fal-target-url') ?? url;
    const json = (o: unknown) => new Response(JSON.stringify(o), { status: 200 });
    if (target.endsWith('/status')) {
      polls += 1;
      return json(polls < 2 ? { status: 'IN_QUEUE', queue_position: 3 } : { status: 'COMPLETED' });
    }
    if (target.endsWith('/requests/abc')) return json({ images: [{ url: 'https://v3.fal.media/out.png' }] });
    return json({
      request_id: 'abc',
      status_url: 'https://queue.fal.run/fal-ai/flux/schnell/requests/abc/status',
      response_url: 'https://queue.fal.run/fal-ai/flux/schnell/requests/abc',
    });
  }) as typeof globalThis.fetch;
  return { fetch, calls };
}

describe('queueTransport', () => {
  it('through a relay: every hop goes to the proxy with the fal URL in X-Fal-Target-Url and the key in X-Fal-Key', async () => {
    const q = fakeQueue();
    const events: string[] = [];
    const transport = queueTransport({ proxyUrl: '/api/fal/proxy', key: () => 'SECRET', fetch: q.fetch, pollIntervalMs: 1 });
    const [done] = await execute([planGenerateImage({ prompt: 'x', quality: 'fast' })], {
      transport,
      onEvent: (e) => events.push(e.kind),
    });
    expect(done!.result.assets[0]!.url).toBe('https://v3.fal.media/out.png');
    expect(done!.requestId).toBe('abc');
    expect(q.calls.every((c) => c.url === '/api/fal/proxy')).toBe(true);
    expect(q.calls[0]!.method).toBe('POST');
    expect(q.calls[0]!.headers.get('x-fal-target-url')).toBe('https://queue.fal.run/fal-ai/flux/schnell');
    expect(q.calls[0]!.headers.get('x-fal-key')).toBe('SECRET');
    expect(q.calls[0]!.headers.has('authorization')).toBe(false);
    expect(JSON.parse(q.calls[0]!.body!)).toMatchObject({ prompt: 'x' });
    expect(q.calls.slice(1).every((c) => c.method === 'GET')).toBe(true);
    expect(events).toEqual(['queued', 'progress', 'progress', 'done']);
  });

  it('through a relay without a key: sends no key header and lets the relay decide', async () => {
    const q = fakeQueue();
    await execute([planGenerateImage({ prompt: 'x' })], {
      transport: queueTransport({ proxyUrl: '/api/fal/proxy', fetch: q.fetch, pollIntervalMs: 1 }),
    });
    expect(q.calls[0]!.headers.has('x-fal-key')).toBe(false);
  });

  it('direct: Authorization: Key …, and refuses to run keyless', async () => {
    const q = fakeQueue();
    await execute([planGenerateImage({ prompt: 'x' })], {
      transport: queueTransport({ key: 'SECRET', fetch: q.fetch, pollIntervalMs: 1 }),
    });
    expect(q.calls[0]!.url).toBe('https://queue.fal.run/fal-ai/flux/dev');
    expect(q.calls[0]!.headers.get('authorization')).toBe('Key SECRET');
    await expect(
      execute([planGenerateImage({ prompt: 'x' })], { transport: queueTransport({ fetch: q.fetch }) }),
    ).rejects.toThrow(FalError);
  });

  it('surfaces an upstream failure with its status, never the key', async () => {
    const fetch = (async () => new Response('{"detail":"nope"}', { status: 402 })) as typeof globalThis.fetch;
    await expect(
      execute([planGenerateImage({ prompt: 'x' })], { transport: queueTransport({ key: 'SECRET', fetch }) }),
    ).rejects.toThrow(/402/);
    await expect(
      execute([planGenerateImage({ prompt: 'x' })], { transport: queueTransport({ key: 'SECRET', fetch }) }),
    ).rejects.not.toThrow(/SECRET/);
  });
});
