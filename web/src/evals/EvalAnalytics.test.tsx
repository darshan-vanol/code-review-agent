import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

it("shows a picker with two reports and switches the table on selection", async () => {
  vi.mocked(getReports).mockResolvedValue([
    { id: "1", passed: false, aggregate: { faithfulness: 0.7, answer_correctness: 0.7 } },
    { id: "2", passed: true, aggregate: { faithfulness: 0.9, answer_correctness: 0.9 } },
  ]);
  vi.mocked(getReport).mockImplementation(async (id) => ({
    aggregate: { faithfulness: 0.9, answer_correctness: 0.9 },
    threshold: 0.75,
    passed: id === "2",
    items: [{ id: `pr-${id}`, faithfulness: 0.9, answer_correctness: 0.9 }],
  }));

  render(<EvalAnalytics />);

  // Default: latest report (id "2") is shown
  expect(await screen.findByText("pr-2")).toBeInTheDocument();

  // Picker is rendered (two reports)
  const picker = screen.getByLabelText("select report");
  expect(picker).toBeInTheDocument();

  // Switch to report "1"
  await userEvent.selectOptions(picker, "1");
  expect(await screen.findByText("pr-1")).toBeInTheDocument();
});
