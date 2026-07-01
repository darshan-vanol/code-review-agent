import { beforeEach, expect, it, vi } from "vitest";

import { getReports, postReview, postReviewStream, type ReviewStage } from "./api";

// A ReadableStream that emits the given chunks, for exercising postReviewStream.
function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i < chunks.length) controller.enqueue(enc.encode(chunks[i++]));
      else controller.close();
    },
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

it("postReview POSTs the body to /review and returns json", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ is_trivial: false }) });
  vi.stubGlobal("fetch", fetchMock);

  const res = await postReview({ diff: "d" });

  expect(fetchMock).toHaveBeenCalledWith(
    "/review",
    expect.objectContaining({ method: "POST" }),
  );
  const [, init] = fetchMock.mock.calls[0];
  expect(JSON.parse(init.body)).toEqual({ diff: "d" });
  expect(res).toEqual({ is_trivial: false });
});

it("getReports GETs /eval/reports", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  vi.stubGlobal("fetch", fetchMock);

  await getReports();

  expect(fetchMock).toHaveBeenCalledWith("/eval/reports");
});

it("postReviewStream reports stages then resolves with the result", async () => {
  // Progress events split mid-line across chunks to exercise the buffering.
  const body = streamOf([
    '{"type":"progress","stage":"ingest"}\n{"type":"progr',
    'ess","stage":"security"}\n',
    '{"type":"result","data":{"is_trivial":false}}\n',
  ]);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body }));

  const stages: ReviewStage[] = [];
  const res = await postReviewStream({ diff: "d" }, (s) => stages.push(s));

  expect(stages).toEqual(["ingest", "security"]);
  expect(res).toEqual({ is_trivial: false });
});

it("postReviewStream throws when the stream reports an error event", async () => {
  const body = streamOf(['{"type":"error","detail":"boom"}\n']);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body }));

  await expect(postReviewStream({ diff: "d" }, () => {})).rejects.toThrow("boom");
});

it("postReview throws on a non-ok response", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "bad" }) });
  vi.stubGlobal("fetch", fetchMock);

  await expect(postReview({ diff: "" })).rejects.toThrow();
});
