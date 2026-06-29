import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { Finding } from "../api";
import { FindingsList } from "./FindingsList";

const finding = (over: Partial<Finding> = {}): Finding => ({
  file: "a.py",
  line_start: 1,
  line_end: 2,
  severity: "high",
  category: "security",
  message: "bad thing",
  suggestion: "fix it",
  ...over,
});

it("groups findings by file and renders badge + location + message", () => {
  render(
    <FindingsList
      findings={[finding(), finding({ file: "b.py", category: "logic", severity: "low" })]}
    />,
  );
  expect(screen.getByText("a.py:1-2")).toBeInTheDocument();
  expect(screen.getByText("high")).toBeInTheDocument();
  expect(screen.getByText("bad thing")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "b.py" })).toBeInTheDocument();
});

it("renders an empty message when there are no findings", () => {
  render(<FindingsList findings={[]} />);
  expect(screen.getByText("No issues found.")).toBeInTheDocument();
});
