from __future__ import annotations

import math
import os

from evals.harness import EvalRecord


def _finite_or_none(value) -> float | None:
    """RAGAS returns NaN when a metric can't be computed (e.g. a truncated judge
    response). NaN is invalid JSON and breaks the dashboard's JSON.parse, so map
    non-finite values to None (-> JSON null)."""
    v = float(value)
    return None if math.isnan(v) or math.isinf(v) else v


def score_with_ragas(records: list[EvalRecord]) -> list[dict]:
    """Score records with RAGAS faithfulness + answer correctness, using a Groq
    judge LLM and local fastembed embeddings. Requires GROQ_API_KEY in the env.

    Returns one {"id", "faithfulness", "answer_correctness"} dict per record.

    Notes (ragas 0.4.x): Faithfulness / AnswerCorrectness live in
    ragas.metrics.collections (with a fallback to ragas.metrics for older
    versions). ragas pins langchain-community<0.4 in this project so its internal
    Vertex AI import resolves cleanly.
    """
    from langchain_community.embeddings.fastembed import FastEmbedEmbeddings  # noqa: PLC0415
    from langchain_core.embeddings import Embeddings  # noqa: PLC0415
    from langchain_groq import ChatGroq  # noqa: PLC0415
    from ragas import EvaluationDataset, evaluate  # noqa: PLC0415
    from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: PLC0415
    from ragas.llms import LangchainLLMWrapper  # noqa: PLC0415
    from ragas.run_config import RunConfig  # noqa: PLC0415

    # Use the classic evaluate()-compatible metrics. In ragas 0.4.x the
    # ragas.metrics.collections variants are a separate instructor-based API
    # (llm passed to the constructor, scored via .score()/.batch_score()) that
    # is NOT compatible with evaluate(metrics=[...], llm=...). The classic
    # classes only emit a deprecation warning here; fall back to collections
    # only if a future release removes them entirely.
    try:
        from ragas.metrics import AnswerCorrectness, Faithfulness  # noqa: PLC0415
    except ImportError:
        from ragas.metrics.collections import AnswerCorrectness, Faithfulness  # noqa: PLC0415

    model = os.environ.get("RAGAS_JUDGE_MODEL", "llama-3.3-70b-versatile")
    # max_retries lets langchain-groq ride out Groq's per-minute token cap rather
    # than failing the whole eval on the first 429.
    judge = LangchainLLMWrapper(ChatGroq(model=model, temperature=0, max_retries=6))
    # ragas reads embeddings.model (expecting a str) for telemetry, but
    # FastEmbedEmbeddings stores the loaded model OBJECT there — which crashes
    # EmbeddingUsageEvent validation and NaNs out answer_correctness. This
    # adapter delegates the actual embed calls while exposing .model as the
    # string name ragas wants.
    embed_model = "BAAI/bge-small-en-v1.5"

    class _NamedEmbeddings(Embeddings):
        def __init__(self, inner: Embeddings, model: str):
            self._inner = inner
            self.model = model

        def embed_documents(self, texts):
            return self._inner.embed_documents(texts)

        def embed_query(self, text):
            return self._inner.embed_query(text)

        async def aembed_documents(self, texts):
            return await self._inner.aembed_documents(texts)

        async def aembed_query(self, text):
            return await self._inner.aembed_query(text)

    embeddings = LangchainEmbeddingsWrapper(
        _NamedEmbeddings(FastEmbedEmbeddings(model_name=embed_model), embed_model)
    )
    # Serialize judge calls (max_workers=1) so RAGAS doesn't fan out a burst that
    # blows the token-per-minute budget; raise the timeout to absorb backoff waits.
    run_config = RunConfig(
        max_workers=int(os.environ.get("RAGAS_MAX_WORKERS", "1")),
        timeout=int(os.environ.get("RAGAS_TIMEOUT_S", "300")),
    )

    dataset = EvaluationDataset.from_list([
        {
            "user_input": r.user_input,
            "response": r.response,
            "retrieved_contexts": r.retrieved_contexts,
            "reference": r.reference,
        }
        for r in records
    ])
    result = evaluate(
        dataset,
        metrics=[Faithfulness(), AnswerCorrectness()],
        llm=judge,
        embeddings=embeddings,
        run_config=run_config,
    )
    df = result.to_pandas()
    out: list[dict] = []
    for record, (_, row) in zip(records, df.iterrows()):
        out.append({
            "id": record.id,
            "faithfulness": _finite_or_none(row["faithfulness"]),
            "answer_correctness": _finite_or_none(row["answer_correctness"]),
        })
    return out
