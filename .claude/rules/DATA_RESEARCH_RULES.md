# Data Research Rules

Read before gathering any data. The goal is a resourceful team that collects **excellent,
high-quality media/datasets, fast**. Be capable first — these rules keep you safe and useful, not
bureaucratic.

## The one hard rule (non-negotiable)

1. **Content safety**: NEVER gather, download, or include pornographic / sexually explicit media,
   or graphic/gratuitous violence and gore. If a source is mixed, filter the unsafe material out at
   harvest time — do not pass it downstream. The Reviewer screens for this, and an automated
   content-safety guardrail HALTS the run if such material reaches the output. Tasteful art, news,
   medical, and academic context is fine; explicit/graphic content is not.

## Good practice (keeps the haul useful — not run-gating)

2. **Record provenance**: For every item, note the source URL and a one-line description so the
   manifest is actually usable later. A dataset nobody can trace back is low value.

3. **Prefer working, primary sources**: Favor official dataset hosts (Hugging Face, data portals,
   the original publisher) and links that actually resolve. Verify a sample downloads/opens before
   listing it as acquired.

4. **Never fabricate data**: Do not invent rows, samples, URLs, or stats. If you couldn't fetch
   something, say so. Real-but-small beats fake-but-large.

5. **Respect access terms**: Honor robots.txt / site terms when scraping; don't hammer a host —
   spread requests and use parallel subagents responsibly.

6. **Quality over volume**: The Curator keeps only the best. A small, clean, well-sourced set is the
   target, not a giant noisy dump.

## Output

Write the haul under `datasets/`:
- `datasets/DATASETS.md` — the manifest (Coordinator owns): one row per dataset with name, source,
  a short quality note, and the Reviewer's verdict.
- `datasets/<slug>/CARD.md` — a short note per dataset: source URL, what it is, how it was fetched.
- `datasets/<slug>/` — the media/data itself (or a fetch manifest when it's too large to store).
