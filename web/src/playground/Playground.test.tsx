import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { postReviewStream } from "../api";
import { Playground } from "./Playground";

vi.mock("../api", () => ({ postReviewStream: vi.fn() }));

const baseResponse = {
  is_trivial: false,
  score: { overall: 0.7, counts: { info: 0, low: 0, medium: 0, high: 1, critical: 0 } },
  security_findings: [
    {
      file: "a.py",
      line_start: 1,
      line_end: 1,
      severity: "high",
      category: "security",
      message: "sql injection",
      suggestion: "parameterize",
    },
  ],
  logic_findings: [],
  test_suggestions: [],
  token_usage: {},
  spans: [],
  errors: [],
};

beforeEach(() => {
  vi.mocked(postReviewStream).mockReset();
});

it("renders findings after a successful review", async () => {
  vi.mocked(postReviewStream).mockResolvedValue(baseResponse as never);
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByText("sql injection")).toBeInTheDocument();
});

it("shows live progress stages while the review streams, then clears them", async () => {
  // Report a couple of stages before the run resolves.
  vi.mocked(postReviewStream).mockImplementation(async (_body, onStage) => {
    onStage("ingest");
    onStage("security");
    return baseResponse as never;
  });
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));

  // The checklist lists the pipeline stages.
  expect(await screen.findByText("sql injection")).toBeInTheDocument();
  // Once finished, the in-progress checklist is gone (result is shown instead).
  expect(screen.queryByLabelText("review progress")).not.toBeInTheDocument();
});

it("shows the trivial notice for a trivial diff", async () => {
  vi.mocked(postReviewStream).mockResolvedValue({
    ...baseResponse,
    is_trivial: true,
    security_findings: [],
  } as never);
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByText(/Trivial diff/)).toBeInTheDocument();
});

it("shows an error message when the request fails", async () => {
  vi.mocked(postReviewStream).mockRejectedValue(new Error("Provide exactly one of"));
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Provide exactly one of");
});
