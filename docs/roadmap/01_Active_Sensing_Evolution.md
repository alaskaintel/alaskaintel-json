# 01: Active Sensing Evolution

## Overview
Transitioning AlaskaIntel from a passive aggregator of RSS feeds to an active, headless-scraping intelligence engine.

## Current State
- 116+ RSS feeds monitored.
- Dependency on third-party feed availability.
- Limited context from headlines only.

## Future State
- **Headless Scrapers**: Playwright-based bots targeting municipal portals, court records, and PDF agendas.
- **Deep Content Extraction**: Full-text parsing of meeting minutes and court filings.
- **LLM-Enriched Signals**: Gemini-powered summarization and intent detection.

## Milestones
- [ ] Implement Anchorage Assembly PDF scraper (Phase 2 completion).
- [ ] Universal PDF-to-Signal pipeline via Gemini 1.5 Pro.
- [ ] Real-time court filing monitoring (9:00 PM nightly pulse).
