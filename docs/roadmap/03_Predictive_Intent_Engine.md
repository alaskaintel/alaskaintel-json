# 03: Predictive Intent Engine

## Overview
Using Large Language Models (LLMs) to transform raw text from meeting agendas and public notices into structured "Intent-to-Act" signals.

## The Strategy
Instead of just reporting *that* a meeting occurred, AlaskaIntel will report *what is likely to happen* based on agenda items.

## Key Mechanisms
- **Agenda Summarization**: Gemini 1.5 Pro parses 500-page meeting packets to find specific "Action Items".
- **Predictive Weighting**: Assigning a score (0-10) based on the likelihood of a policy change or fiscal impact.
- **Entity Linking**: Automatically identifying which businesses, regions, or individuals are mentioned in high-intent documents.

## Milestones
- [ ] Deploy the `predictive_weight` schema update.
- [ ] Automate PDF-to-Structured-JSON pipeline for Anchorage Assembly.
- [ ] Implement "High Intent" alerts in the Global Signal Wall UI.
