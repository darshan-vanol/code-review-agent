import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { EvalReport } from "../api";
import { ReportTable } from "./ReportTable";

const report: EvalReport = {
  aggregate: { score: 0.8, recall: 0.9 },
  threshold: 0.75,
  passed: true,
  items: [
    { id: "ok", score: 0.75, recall: 1.0 },
    { id: "bad", score: 0.74, recall: 1.0 },
  ],
};

it("marks rows pass/fail at the threshold on score", () => {
  render(<ReportTable report={report} />);
  expect(screen.getByText("ok").closest("tr")).toHaveAttribute("data-status", "pass");
  expect(screen.getByText("bad").closest("tr")).toHaveAttribute("data-status", "fail");
});

it("passes a row on score even when recall is low", () => {
  const r: EvalReport = {
    aggregate: { score: 0.8, recall: 0.5 },
    threshold: 0.75,
    passed: true,
    items: [{ id: "hi", score: 0.9, recall: 0.2 }],
  };
  render(<ReportTable report={r} />);
  expect(screen.getByText("hi").closest("tr")).toHaveAttribute("data-status", "pass");
});
