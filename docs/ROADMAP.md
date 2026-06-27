# Jarvis Roadmap

This roadmap starts after the v0.2.0 stable checkpoint. Items here are directional and should remain behind explicit settings, tests, and permission boundaries.

## v0.3.0 Agent Workflows

- Make the optional agent path useful for multi-step but bounded workflows.
- Keep `AssistantCore` and the existing tool routes as the source of truth for permissions and confirmations.
- Add workflow state, cancellation, and clearer progress reporting.
- Avoid autonomous background execution unless a later phase explicitly approves it.

## Better TTS

- Improve interruption reliability for spoken responses.
- Add better provider diagnostics and fallback messages.
- Support more natural voice pacing and shorter acknowledgement modes.
- Keep voice selection original and avoid imitation of real people or copyrighted characters.

## Better STT Providers

- Improve provider selection and health checks.
- Add clearer model/device guidance for CPU and GPU setups.
- Continue reducing false accepts from weak, incomplete, or noisy transcripts.
- Preserve local validation before commands reach OpenAI or tools.

## Gmail And Calendar

- Improve setup guidance for OAuth credentials and token scope refreshes.
- Add safer summaries for Gmail and Calendar data after confirmation.
- Keep draft creation, draft sending, calendar reads, and event creation separately enabled.
- Keep every high-risk action permission-classified and confirmation-gated.

## Screen Automation

- Explore read-only screen understanding first, then narrowly scoped interaction primitives.
- Require explicit user confirmation before any click, typing, or window control.
- Add preview plans before actions are executed.
- Keep password, banking, credential, and sensitive screens blocked from automation.
