import { beforeEach, expect, it, vi } from "vitest";

import { getReports, postReview } from "./api";

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

it("postReview throws on a non-ok response", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "bad" }) });
  vi.stubGlobal("fetch", fetchMock);

  await expect(postReview({ diff: "" })).rejects.toThrow();
});
