import { type FormEvent, useState } from "react";

type Mode = "diff" | "pr_url";

export function ReviewForm({
  onSubmit,
  loading,
}: {
  onSubmit: (body: { diff?: string; pr_url?: string }) => void;
  loading: boolean;
}) {
  const [mode, setMode] = useState<Mode>("diff");
  const [diff, setDiff] = useState("");
  const [prUrl, setPrUrl] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit(mode === "diff" ? { diff } : { pr_url: prUrl });
  }

  return (
    <form className="review-form" onSubmit={submit}>
      <div role="tablist" className="mode-toggle">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "diff"}
          onClick={() => setMode("diff")}
        >
          Diff
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "pr_url"}
          onClick={() => setMode("pr_url")}
        >
          PR URL
        </button>
      </div>

      {mode === "diff" ? (
        <textarea
          aria-label="diff"
          rows={12}
          value={diff}
          onChange={(e) => setDiff(e.target.value)}
          placeholder="Paste a unified diff (diff --git ...)"
        />
      ) : (
        <input
          aria-label="pr_url"
          value={prUrl}
          onChange={(e) => setPrUrl(e.target.value)}
          placeholder="https://github.com/owner/repo/pull/123"
        />
      )}

      <button type="submit" disabled={loading}>
        {loading ? "Reviewing…" : "Review"}
      </button>
    </form>
  );
}
