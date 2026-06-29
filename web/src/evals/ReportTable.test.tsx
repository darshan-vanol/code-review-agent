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
