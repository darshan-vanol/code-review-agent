from __future__ import annotations

import os

from evals.harness import EvalRecord


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
    from langchain_groq import ChatGroq  # noqa: PLC0415
    from ragas import EvaluationDataset, evaluate  # noqa: PLC0415
    from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: PLC0415
    from ragas.llms import LangchainLLMWrapper  # noqa: PLC0415

    try:
        from ragas.metrics.collections import AnswerCorrectness, Faithfulness  # noqa: PLC0415
    except ImportError:
        from ragas.metrics import AnswerCorrectness, Faithfulness  # noqa: PLC0415

    model = os.environ.get("RAGAS_JUDGE_MODEL", "llama-3.3-70b-versatile")
    judge = LangchainLLMWrapper(ChatGroq(model=model, temperature=0))
    embeddings = LangchainEmbeddingsWrapper(
        FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
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
    )
    df = result.to_pandas()
    out: list[dict] = []
    for record, (_, row) in zip(records, df.iterrows()):
        out.append({
            "id": record.id,
            "faithfulness": float(row["faithfulness"]),
            "answer_correctness": float(row["answer_correctness"]),
        })
    return out
