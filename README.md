# Inference Forensics

**Explore · Observe · Learn · Improve**

Inference Forensics is a personal, evidence-driven research repository for learning how large language models (LLMs), inference models, and agentic AI behave in different conditions.

## Purpose

The project investigates:

- how model harnesses work and influence execution;
- how the Agent Client Protocol (ACP) works in practice;
- how prompts, configuration, context, and tool/skill availability affect model behaviour;
- how to select the right model for each task; and
- how to optimise token use—for both cloud/billing cost and context capacity—without sacrificing useful outcomes.

The goal is to build a practical understanding of agentic AI and to make its behaviour observable. Findings are grounded in repeatable tests, recorded facts, and direct observations rather than assuming that an AI system is correct or deterministic.

## Experiments

- [Check Skills](./check-skills/) — isolated Codex CLI tests that examine skill invocation, prompt spelling, skill loading, custom system prompts, token usage, and execution time.

Each experiment should preserve its inputs, configuration, raw outputs, and measurements so results can be reviewed and challenged as the tools and models evolve.
