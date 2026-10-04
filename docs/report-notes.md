# Report notes

## Please confirm or delete

- [CONFIRM] The self-hosted workflow context failure shown in the provided Actions log was caused by runner context configuration. The log says the active context was empty while `shortly` was expected; the repository runbook explains the `ALLOW_CONTEXT` and `PROFILE` settings.

## Fill in before submission

- Group members: `Harsh Ledwani, Shivam Kapure, Kashyup Gaud, Kisna Kanti`
- Roll numbers: `23070122100, 23070122113, 23070122114, 23070122116`
- Step 6 external challenge: `[TO BE FILLED]`; no proof was present in the repository at report generation.

## Decisions and evidence limits

- The assignment calls for four to five slides; the deck uses exactly five assertion-title slides and no title or closing slide.
- Challenge confidence means repository-backed evidence. Scenario and Ansible results use committed reports/logs; plans and expected outcomes in runbooks are not presented as observed results.
- The scenario summary records the first `scenario-all` abuse run as FAIL. A focused rerun passed, but the full suite was not rerun; report this split accurately.
- The captured Ansible host evidence is a macOS negative preflight with zero changes. Positive apply, idempotence and verify evidence comes from the disposable Ubuntu 24.04 container.
- No screenshot images existed in the repository when checked. Slides use pending frames and the screenshot checker reports missing files; no screenshot is synthesized.
- Mermaid CLI was unavailable. Mermaid blocks are syntax-reviewed and the slide diagrams are editable PowerPoint shapes.
- Typical pipeline duration is documented as 7–15 minutes in `docs/cicd.md`; there is no committed `gh run list` duration sample. Label it as the runbook's typical estimate.
- Visual QA used LibreOffice PDF export and `pdftoppm` at 120 dpi, and all five pages were inspected. Slide 1's monitoring line was routed above the app/state boxes and its Ansible connector points to the runner automation; slide 2's GHCR handoff was routed to preflight. Slide 5's title was shortened after the first render clipped its first character. The final five pages had no overlaps or off-page shapes. The temporary embed-path check used an unmistakable `NOT PROJECT EVIDENCE` card and was deleted before the final rebuild.
- The capture session has been sequenced to focus first on rubric MUST evidence; actual scenario runs may take longer than one hour if all SHOULD shots are captured.
