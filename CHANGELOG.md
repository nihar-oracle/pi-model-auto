# Changelog

## 0.2.0 - 2026-07-26

### Breaking changes

- Replaced user-facing `cheap` / `strong` routing hints with capability-mode hints: `low`, `medium`, `high`, and `ultra`.
- `@low`, `@medium`, `@high`, `@ultra`, and `@model:provider/model` are now only honored on the first user turn of a conversation. Mid-conversation prefixes are ignored and the user is warned, avoiding accidental high-cost routing over long existing histories.
- Core API `resolveRouteModel({ hint })` now accepts `low | medium | high | ultra | auto | provider/model`; `cheap` and `strong` no longer resolve.
- Router config now uses `modeModels` for optional `low` / `medium` / `high` / `ultra` endpoint pins instead of cheap/strong tier pins.
- Classifier output now uses the same mode vocabulary directly (`mode=<low|medium|high|ultra>`) instead of the old `trivial` / `normal` / `hard` / `max` labels.
- The LLM classifier is now opt-in: it only runs when `classifierModel` pins an exact model; default routing uses the local heuristic with no extra classifier model call.

### Changed

- Artificial Analysis (`aa`) routing now maps models onto the same Low / Medium / High / Ultra capability modes using conservative Intelligence Index bands (`Ultra >= 56`, `High >= 52`, `Medium > 41`, `Low <= 41`), so both `ramp` and `aa` share the same user-facing mode vocabulary.
- README now documents representative models for each capability mode and explains fallback behavior when those models are not available locally.
