# Interface comparison

The review interface lives in `analysis/review_app/` and reuses the reference server's endpoint contract so the state files stay readable by `analysis/helpers` and the Module 3 tooling.

## One design retained from the reference interface

The four-view structure and the file-backed API were kept unchanged: a trace view for reading and annotating, a map view projecting every session into two dimensions coloured by cluster, a progress view, and a structured labelling view that only opens once the taxonomy has stabilised. The inline annotation pattern was also retained, including wrapping the selected range in a temporary highlight before focusing the input, because the browser clears the native selection when focus moves.

## One design changed after inspecting the traces

A pinned answer-key panel was added beside the conversation. Every Cartwheel scenario carries a verified expected outcome, the database record it was derived from, the applicable policy text and the relevant `SPEC.md` requirements. Reviewing without them meant leaving the trace to look up whether a reply was actually wrong, which is the slowest step in open coding. The panel shows the expected outcome and its reason and source, the order or product record with its status, dates, window and eligibility, the caller's role and store, the full text of each applicable policy, the text of each cited requirement, and the seeded world date of 2026-07-01 that all date arithmetic depends on.

A second, smaller adaptation follows from the trace structure: Cartwheel writes one Langfuse trace per user turn, so 250 scenarios produced 359 traces and 100 sessions span two or three of them. The interface groups by `cartwheel.session_id` and renders the whole conversation in order with turn dividers, because a follow-up turn read in isolation hides the tool calls from earlier turns.

## One remaining limitation

Structured labels are written to `analysis/state/labels/` through the interface and a helper script, but the interface does not push Langfuse scores itself; that is a separate step. Margin notes are also positioned from the highlighted span's bounding box, so a note whose quoted text appears more than once in a session attaches to the first occurrence. Finally, the map view draws no cluster hulls, so cluster membership is readable only from node colour.
