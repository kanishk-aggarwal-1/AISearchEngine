# SignalScope AI Demo Script

## Goal

Show the strongest end-to-end workflow in under five minutes:

Search -> grounded answer -> source comparison -> save context -> follow-up -> alert

## Demo setup

Before presenting:

1. Start the stack locally or via Docker
2. Open:
- frontend home page
- backend `/docs`
- backend `/health/deep`
3. Log in with an account that can access the admin panel

## Suggested demo flow

### 1. Show the product scope

On the homepage:
- point out category coverage
- point out latest headlines
- mention this is one retrieval workspace for tech, research, sports, and world news

### 2. Run a strong query

Suggested examples:
- `latest breakthroughs in AI agents`
- `middle east conflict updates`
- `latest NBA playoff updates`

Show:
- grounded explanation
- provider used
- key takeaways
- claim confidence

### 3. Open the source layer

Show:
- source cards
- grounding snippet
- credibility/confidence/bias labels
- “why this source” explanation

### 4. Show workflow continuity

From the same result:
- save the context
- save the top source
- ask a follow-up question
- create an alert from the current query

### 5. Show domain depth

Optionally open:
- a sports team page
- a research paper page

This helps communicate that the app is not just a generic answer surface.

### 6. Show operations/admin credibility

Open the admin section and point out:
- source health
- success/failure counts
- source freshness
- recent ingestion runs
- manual reingest

Then open:
- `/health/deep`
- `/metrics`

This reinforces that the project is production-minded, not only UI-focused.

## Closing line

SignalScope AI is a retrieval-first AI search platform that turns live multi-source information into grounded answers, reusable research context, and operationally observable search workflows.
