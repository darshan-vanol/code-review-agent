import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { EvalReport } from "../api";
import { ReportTable } from "./ReportTable";

const report: EvalReport = {
  aggregate: { faithfulness: 0.8, answer_correctness: 0.8 },
  threshold: 0.75,
  passed: true,
  items: [
    { id: "ok", faithfulness: 0.75, answer_correctness: 0.9 },
    { id: "bad", faithfulness: 0.74, answer_correctness: 0.9 },
  ],
};

it("marks rows pass/fail at the 0.75 boundary", () => {
  render(<ReportTable report={report} />);
  expect(screen.getByText("ok").closest("tr")).toHaveAttribute("data-status", "pass");
  expect(screen.getByText("bad").closest("tr")).toHaveAttribute("data-status", "fail");
});

it("renders a null score as n/a and marks the row failed", () => {
  // A truncated judge response yields null (not a number) for a metric; the
  // table must render it without crashing on toFixed.
  const withNull: EvalReport = {
    aggregate: { faithfulness: 0.5, answer_correctness: 0.5 },
    threshold: 0.75,
    passed: false,
    items: [{ id: "trunc", faithfulness: 0.9, answer_correctness: null }],
  };
  render(<ReportTable report={withNull} />);
  expect(screen.getByText("n/a")).toBeInTheDocument();
  expect(screen.getByText("trunc").closest("tr")).toHaveAttribute("data-status", "fail");
});
