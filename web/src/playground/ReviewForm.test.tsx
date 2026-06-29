import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ReviewForm } from "./ReviewForm";

it("submits a diff in diff mode", async () => {
  const onSubmit = vi.fn();
  render(<ReviewForm onSubmit={onSubmit} loading={false} />);
  await userEvent.type(screen.getByLabelText("diff"), "my diff");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(onSubmit).toHaveBeenCalledWith({ diff: "my diff" });
});

it("submits a pr_url in URL mode", async () => {
  const onSubmit = vi.fn();
  render(<ReviewForm onSubmit={onSubmit} loading={false} />);
  await userEvent.click(screen.getByRole("tab", { name: "PR URL" }));
  await userEvent.type(screen.getByLabelText("pr_url"), "http://x/pull/1");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(onSubmit).toHaveBeenCalledWith({ pr_url: "http://x/pull/1" });
});

it("disables submit while loading", () => {
  render(<ReviewForm onSubmit={vi.fn()} loading={true} />);
  expect(screen.getByRole("button", { name: /Reviewing/ })).toBeDisabled();
});
