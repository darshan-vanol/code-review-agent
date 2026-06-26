from __future__ import annotations

import os
import sys
import types

from evals.harness import EvalRecord


def _patch_langchain_community_vertexai() -> None:
    """Inject compatibility stubs for removed langchain-community Vertex AI modules.

    ragas<=0.4.x has a top-level hard import of ChatVertexAI / VertexAI from
    langchain-community. These were removed in langchain-community>=0.4 (moved to
    langchain-google-vertexai). The stubs let ragas import without requiring the
    full google-cloud-aiplatform stack.

    This must be called before any ``import ragas`` statement.
    """
    # 1. Stub langchain_community.chat_models.vertexai → ChatVertexAI
    chat_key = "langchain_community.chat_models.vertexai"
    if chat_key not in sys.modules:
        stub = types.ModuleType(chat_key)

        class ChatVertexAI:
            """Stub — install langchain-google-vertexai for real Vertex AI use."""

            def __init__(self, *args, **kwargs):
                raise ImportError(
                    "ChatVertexAI requires langchain-google-vertexai. "
                    "Run: pip install langchain-google-vertexai"
                )

        stub.ChatVertexAI = ChatVertexAI  # type: ignore[attr-defined]
        sys.modules[chat_key] = stub

        parent_key = "langchain_community.chat_models"
        if parent_key in sys.modules:
            sys.modules[parent_key].vertexai = stub  # type: ignore[attr-defined]

    # 2. Stub VertexAI on langchain_community.llms (imported as an attribute)
    try:
        import langchain_community.llms as _llms_mod  # noqa: PLC0415

        if not hasattr(_llms_mod, "VertexAI"):

            class VertexAI:
                """Stub — install langchain-google-vertexai for real Vertex AI use."""

                def __init__(self, *args, **kwargs):
                    raise ImportError(
                        "VertexAI requires langchain-google-vertexai. "
                        "Run: pip install langchain-google-vertexai"
                    )

            _llms_mod.VertexAI = VertexAI  # type: ignore[attr-defined]
    except ImportError:
        pass


def score_with_ragas(records: list[EvalRecord]) -> list[dict]:
    """Score records with RAGAS faithfulness + answer correctness, using a Groq
    judge LLM and local fastembed embeddings. Requires GROQ_API_KEY in the env.

    Returns one {"id", "faithfulness", "answer_correctness"} dict per record.

    Adaptation notes (ragas 0.4.3 / langchain-community 0.4.x):
    - langchain-community 0.4 removed chat_models.vertexai and llms.VertexAI;
      _patch_langchain_community_vertexai() injects stubs before the ragas import.
    - Faithfulness / AnswerCorrectness moved to ragas.metrics.collections in 0.4.x;
      we try that path first and fall back to ragas.metrics for older versions.
    """
    _patch_langchain_community_vertexai()

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
