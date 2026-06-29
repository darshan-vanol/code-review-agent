import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("./playground/Playground", () => ({ Playground: () => <div>PLAYGROUND</div> }));
vi.mock("./evals/EvalAnalytics", () => ({ EvalAnalytics: () => <div>ANALYTICS</div> }));

it("shows the playground by default and switches to analytics", async () => {
  render(<App />);
  expect(screen.getByText("PLAYGROUND")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Eval Analytics" }));
  expect(screen.getByText("ANALYTICS")).toBeInTheDocument();
});
