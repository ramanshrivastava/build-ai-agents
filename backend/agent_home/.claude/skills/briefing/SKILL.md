---
name: briefing
description: Generate a structured pre-consultation patient briefing. Use when
  the physician asks for a briefing, a pre-consultation summary, or sends
  /briefing.
---

# Pre-consultation briefing

Generate a structured briefing for the patient in this conversation, grounded
in retrieved clinical evidence.

## Workflow

1. Review the patient record already present in this conversation
   (demographics, conditions, medications, labs with reference ranges,
   allergies, visits).
2. Call `mcp__guidelines__search_clinical_guidelines` for each major
   condition, and for drug interactions when the patient takes 2+ medications.
   Use specific clinical queries (e.g. "metformin renal dosing eGFR 45"),
   not vague ones (e.g. "diabetes"). If any guidelines search returns nothing
   relevant — for a condition, medication interaction, or screening — and the
   web-research skill is available, you may search the web for authoritative
   guidance and cite the source URL in the flag/action description — local
   guidelines remain the primary source.
3. Build the briefing:
   - **flags** — category one of `labs` (values outside reference ranges),
     `medications` (interaction/dosing concerns), `screenings` (overdue
     preventive screenings for age/gender/conditions), `ai_insight` (clinical
     patterns across the data). Severity: `critical` = immediate concern,
     `warning` = needs attention this visit, `info` = worth noting. `source`
     is always `"ai"`. Include `suggested_action` when a concrete next step
     exists.
   - **summary** — `one_liner` (single sentence capturing the clinical
     picture), `key_conditions` (active conditions from the record),
     `relevant_history` (brief clinically relevant context).
   - **suggested_actions** — 3-5 actions prioritized by clinical urgency
     (priority 1 = most urgent), each with a brief reason.
   - Cite a `[source_id]` from search results for every clinical claim. If no
     relevant guidelines were found, state that explicitly — never invent
     source backing.
4. REQUIRED FINAL STEP: call `mcp__publisher__publish_briefing` exactly once
   with the complete briefing. Do NOT paste the briefing JSON into your chat
   reply — the dashboard renders it from the publish call.
5. After the tool confirms, reply with one or two sentences summarizing the
   most important finding so the physician sees it in the chat thread.

## Constraints

- Only flag issues visible in the provided data.
- Be concise: physicians need quick, scannable information.
