import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { getReport, getReports } from "../api";
import { EvalAnalytics } from "./EvalAnalytics";

vi.mock("../api", () => ({ getReports: vi.fn(), getReport: vi.fn() }));
vi.mock("./TrendChart", () => ({ TrendChart: () => <div data-testid="trend" /> }));

beforeEach(() => {
  vi.mocked(getReports).mockReset();
  vi.mocked(getReport).mockReset();
});

it("shows an empty state when there are no reports", async () => {
  vi.mocked(getReports).mockResolvedValue([]);
  render(<EvalAnalytics />);
  expect(await screen.findByText(/No eval runs yet/)).toBeInTheDocument();
});

it("renders the table for the latest report", async () => {
  vi.mocked(getReports).mockResolvedValue([
    { id: "1", passed: true, aggregate: { faithfulness: 0.9, answer_correctness: 0.9 } },
  ]);
  vi.mocked(getReport).mockResolvedValue({
    aggregate: { faithfulness: 0.9, answer_correctness: 0.9 },
    threshold: 0.75,
    passed: true,
    items: [{ id: "pr-x", faithfulness: 0.9, answer_correctness: 0.9 }],
  });
  render(<EvalAnalytics />);
  expect(await screen.findByText("pr-x")).toBeInTheDocument();
  expect(screen.getByTestId("trend")).toBeInTheDocument();
});
