import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { postReview } from "../api";
import { Playground } from "./Playground";

vi.mock("../api", () => ({ postReview: vi.fn() }));

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
  vi.mocked(postReview).mockReset();
});

it("renders findings after a successful review", async () => {
  vi.mocked(postReview).mockResolvedValue(baseResponse as never);
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByText("sql injection")).toBeInTheDocument();
});

it("shows the trivial notice for a trivial diff", async () => {
  vi.mocked(postReview).mockResolvedValue({
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
  vi.mocked(postReview).mockRejectedValue(new Error("Provide exactly one of"));
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Provide exactly one of");
});
