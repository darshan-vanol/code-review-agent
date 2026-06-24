# **Goal Title:** LangGraph \+ Langfuse — Build an Observable AI Agent with Evaluation Harness

**Goal Type:** Cross-Skill (Agentic AI)

**Description:** Use case: Build a *Code Review Assistant* — a multi-step AI agent that accepts a GitHub PR diff, runs structured review steps (security check → logic analysis → test coverage suggestion), and returns annotated feedback in JSON. The agent is built using LangGraph as the stateful orchestration layer on top of the LangChain you already know. Langfuse is wired in as the observability layer — every node execution, token count, latency, and score is traced and logged. RAGAS-style evaluation runs on a golden dataset of 20 PRs to measure answer correctness and faithfulness. This is the exact stack being hired for at companies building internal developer tooling — Stripe, Linear, and Vercel all run LLM evaluation pipelines in CI before deploying prompt changes. 

**Deliverables:**

1. LangGraph agent with 3+ nodes (ingestion → analysis → scoring), deployed as a NestJS API endpoint  
2. Langfuse project set up with full trace visibility — spans, token counts, latency per node  
3. Evaluation dataset of 20 synthetic PR diffs with ground-truth expected outputs; RAGAS faithfulness \+ correctness scores ≥ 0.75  
4. CI pipeline (GitHub Actions) that runs eval suite on every prompt change and fails below threshold  
5. Walkthrough demo video

Why Fits you specifically — this pushes him to the *production readiness* layer (observability \+ eval harness) which is the gap between an AI hobbyist and an AI engineer companies actually hire. Langfuse is currently the most-cited open-source LLM observability tool in backend engineering JDs. The harness engineering angle completes the full AI engineering loop: build → deploy → observe → evaluate → iterate.