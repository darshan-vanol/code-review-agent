import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ProviderBadge } from "./ProviderBadge";

beforeEach(() => {
  vi.restoreAllMocks();
});

it("shows the provider and model from /version", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        version: "0.1.0",
        provider: "groq",
        model: "llama-3.3-70b-versatile",
        langfuse_enabled: false,
      }),
    }),
  );

  render(<ProviderBadge />);

  expect(await screen.findByText("groq")).toBeInTheDocument();
  expect(screen.getByText("llama-3.3-70b-versatile")).toBeInTheDocument();
});

it("renders nothing when /version fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));

  const { container } = render(<ProviderBadge />);

  await waitFor(() => expect(container).toBeEmptyDOMElement());
});
