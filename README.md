# pi-model-auto

`pi-model-auto` adds one Pi model: **Pi Router (Auto)**.

Choose it once with `/model`. After that, Pi keeps using the router, and the router chooses one of your authenticated models for each turn.

## Start

Install from npm:

```bash
pi install npm:pi-model-auto
```

Or install from git (pin a release with `@vX.Y.Z`, or omit it to track the default branch):

```bash
pi install git:github.com/maynewong/pi-model-auto@v0.1.0
```

Update later with `pi update --extensions`.

To try it once without installing, point `-e` at a local checkout:

```bash
pi -e /path/to/pi-model-auto
```

Then:

1. Run `/model`.
2. Choose **Pi Router (Auto)**.
3. Use Pi normally.

No config is required at first. If the router says no authenticated models are available, run `/login` for the providers you want to use, then reload Pi.

## Use

Check what the router sees:

```text
/auto
```

Most turns should use automatic routing. At the start of a new conversation, you can pin the initial capability mode:

```text
@low summarize this file
@medium implement this small change
@high debug this failing test
@ultra investigate this architecture issue
@model:anthropic/claude-3-5-sonnet-20241022 use Sonnet here
```

- `@low`, `@medium`, `@high`, and `@ultra` target the matching capability mode.
- `@model:provider/model-id` uses that exact model.
- Without a prefix, `auto` routing lets task difficulty choose the target mode.

These prefixes are intentionally only honored on the first user turn of a conversation. They do not create an isolated subagent or trimmed context. If you used them after a long history, the selected model would need to read the existing session history, which can be much more expensive. Start a new session when you want to pin a mode cleanly.

The prefix is removed before the model sees your prompt. `cheap` and `strong` are no longer supported routing hints; use `low` and `ultra` instead.

## Configure When Needed

Most people only need config for two reasons:

1. Limit the pool to providers they trust.
2. Tell the router what each model really costs them.

Config lives in either file:

- `~/.pi/agent/model-router.json`
- `.pi/model-router.json` in trusted projects

Project config overrides user config.

```jsonc
{
  "router": {
    "modelFilter": { "include": ["anthropic", "z-ai"], "exclude": [] },
    "modeModels": {
      "ultra": "anthropic/claude-3-5-sonnet-20241022"
    },
    "modelOverrides": {
      "anthropic/claude-3-5-sonnet-20241022": { "costCoef": 0.05 },
      "z-ai/glm-5.2": {
        "costCoef": 0.4,
        "costCoefHours": [{ "hours": [14, 18], "factor": 3 }]
      }
    }
  }
}
```

Use provider/model ids exactly as they appear in your Pi registry. The names above are public examples. `modeModels` is optional; if you omit it, the router builds each mode from benchmark metadata.

### `costCoef`

`costCoef` multiplies the benchmark cost:

- `< 1`: cheaper for you than the benchmark, such as a subscription or discount.
- `= 1`: roughly benchmark cost.
- `> 1`: more expensive for you.

Avoid setting a limited subscription near zero unless you want it to win almost every turn.

### `costCoefHours`

Use this when a model is more expensive during local hours:

```jsonc
"z-ai/glm-5.2": {
  "costCoef": 0.4,
  "costCoefHours": [{ "hours": [14, 18], "factor": 3 }]
}
```

This means `0.4` normally, `1.2` from 14:00 through 17:59. Windows are half-open `[start, end)`. `[22, 2]` wraps across midnight.

## How It Chooses

The router compares quality against your effective cost.

Quality comes from one benchmark table. Cost starts from the same table, then applies your `costCoef` and any active time window. When the table reports reasoning effort, the router treats `(model, effort)` as the measured operating point. The router keeps to the efficient frontier: a model-effort variant is only worth considering if no other available variant is both better and cheaper.

`capabilitySource` chooses the benchmark:

- `"ramp"` (default): this package's [Ramp SWE-Bench](https://labs.ramp.com/swebench#score-vs-spend) table, using coding-agent resolve rate and measured cost per task. It is a narrow coding-agent slice, not a general model score. The task family follows [SWE-bench](https://arxiv.org/abs/2310.06770).
- `"aa"`: [Artificial Analysis](https://artificialanalysis.ai/models) model data, using its Intelligence Index and blended price metrics.

The numeric tables live in [`src/canonical-models.ts`](src/canonical-models.ts). The two sources are not mixed.

The user-facing status label is a capability mode. Cost is a separate routing axis and never determines this label.

For the Ramp source, the mode is derived only from SWE-bench solve rate:

| mode | Ramp solve rate | representative measured models |
| --- | --- | --- |
| `Ultra` | `>= 85%` | `claude-opus-5`, `claude-fable-5`, `kimi-k3` |
| `High` | `80–85%` | `gpt-5.5`, `gpt-5.6-sol`, `grok-4.5`, `glm-5.2` |
| `Medium` | `75–80%` | `kimi-k2.7-code`, `claude-opus-4-8`, `gpt-5.6-terra` |
| `Low` | `< 75%` | `gemini-3.1-pro`, `claude-sonnet-5`, `gpt-5.4`, `gpt-5.4-nano` |

For the AA source, the same four modes are mapped from Artificial Analysis Intelligence Index bands:

| mode | AA Intelligence Index | representative AA models |
| --- | --- | --- |
| `Ultra` | `>= 56` | `claude-opus-5`, `claude-fable-5`, `gpt-5.6-sol`, `kimi-k3` |
| `High` | `52–56` | `gpt-5.6-terra`, `grok-4.5`, `claude-opus-4-7`, `claude-sonnet-5`, `gpt-5.5` |
| `Medium` | `> 41 and < 52` | `gpt-5.4`, `gpt-5.6-luna`, `glm-5.2`, `gemini-3.1-pro`, `kimi-k2.7-code` |
| `Low` | `<= 41` | `deepseek-v4-flash`, `glm-5.1`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gemini-3.1-flash-lite` |

Representative models are examples from the bundled benchmark tables, not requirements. The router only uses models that are present in your local Pi registry, authenticated, and allowed by `modelFilter`. If none of your available models are in the target mode, the router borrows the nearest stronger mode; if no stronger mode exists, it uses the strongest available lower mode. If no authenticated benchmark-backed models are available at all, it asks you to `/login` or configure model metadata.

Task difficulty chooses the mode, while the continuous difficulty score sets a capability floor inside that mode. The router picks the cheapest effective-cost model meeting the floor, then permits only affordable `willingness` upgrades inside the same mode. It never enters the next mode early. Models without capability-mode metadata retain Pareto routing.

Task difficulty is judged from language-neutral signals: context size, prompt length, and recent tool activity. In automatic routing, benchmark-backed effort is selected with the model and takes precedence over Pi's session default before the model's `thinkingLevelMap` is applied. Forced concrete-model routes still honor Pi's selected effort. When you know a task is harder than it looks, start a new session with `@high` or `@ultra`.

By default, the router uses only the local heuristic and makes no extra classifier model call. You can opt in to a small current-turn LLM classifier by setting `classifierModel`.

### Classifier and Coarse Auto Detection

Automatic routing has two layers:

1. **Local heuristic, always available.** It computes a rough difficulty score from language-neutral signals: estimated context size, current prompt length, and recent tool-result density. This is free, deterministic, and private, but intentionally coarse; it cannot deeply understand whether a short request is semantically hard.
2. **Bounded LLM classifier, opt-in.** It runs only after you configure `classifierModel` with an exact model id. For auto routing, the router first makes a local draft decision. It runs the classifier for the current turn only when there is no previous route yet, or when that draft decision would switch away from the previous/warm model. Forced `@low`/`@medium`/`@high`/`@ultra`/`@model:...` turns and tool-call continuations do not run the classifier.

#### Local heuristic, no LLM

When the classifier is disabled or skipped, the router computes:

```text
score = normalize(estimatedContextTokens, 8_000, 120_000) * weights.contextTokens
      + normalize(lastUserMessage.length, 120, 1_200) * weights.lastUserLen
      + min(1, recentToolResults / 8) * weights.toolDensity
```

Default weights are:

```jsonc
{
  "weights": {
    "contextTokens": 0.3,
    "lastUserLen": 0.5,
    "toolDensity": 0.2
  }
}
```

The score maps to mode buckets:

| score | mode |
| --- | --- |
| `< 0.30` | `low` |
| `0.30–0.52` | `medium` |
| `0.52–0.74` | `high` |
| `>= 0.74` | `ultra` |

This is deliberately language-neutral: it does not look for English keywords. It mostly asks, "how much context, how much prompt, how much recent tool activity?" That makes it cheap and predictable, but it can under-classify short, high-risk requests.

#### LLM classifier prompt

If the bounded classifier runs, it receives the following system prompt:

```text
You are Pi Router's classifier. Classify the current user turn for model routing.
Return exactly one line and no prose: mode=<low|medium|high|ultra> profile=<balanced|coder|deep|fast|vision> score=<0..1>.
Mode is required capability, not cost. Cost is handled later by the router.
Mode rubric:
- low: trivial, explain, summarize, docs/copy edits, tiny localized change, low ambiguity.
- medium: routine coding/debugging/refactor, small scoped implementation, ordinary tests, a few files.
- high: multi-file work, failing tests, unknown root cause, API/design decisions, non-trivial tool use, sizeable context.
- ultra: architecture/security/migrations, production-risk changes, large refactor, long-horizon investigation, high ambiguity or high cost of failure.
Profile rubric:
- vision if hasImage=true.
- fast only when the user explicitly prioritizes speed/latency or the task is a simple transform.
- coder for implementation, debugging, refactoring, tests, or code review.
- deep for architecture, root-cause analysis, security, planning, or long-horizon reasoning.
- balanced otherwise.
Score is position inside the chosen mode: low 0.00-0.29, medium 0.30-0.51, high 0.52-0.73, ultra 0.74-1.00.
If uncertain between adjacent modes, choose the lower mode unless the task is risky, irreversible, security-sensitive, or explicitly asks for deep investigation.
```

The classifier model receives only this user payload:

```text
estimatedContextTokens=<local estimate>
hasImage=<true|false>
lastUserMessage:
<the latest user message>
```

It does **not** receive the full conversation history. The full session is only inspected locally to estimate token count, count recent tool results, and detect whether images exist.

The classifier returns the same `low` / `medium` / `high` / `ultra` vocabulary users see in the UI. The optional `score` positions the request inside that mode's capability floor; the classifier does not directly choose a model.

#### Classifier cost controls

Classifier cost is bounded in several ways:

- The classifier prompt omits prior assistant/user turns and tool output bodies.
- Output is capped at `maxTokens: 80`.
- It uses `temperature: 0`, `reasoning: minimal` when the model supports reasoning, the configured timeout, and no internal retries.
- It is gated by the local draft decision: after the first auto turn, if the draft keeps the previous/warm model, no classifier call is made.
- Tool-call continuations reuse the same turn route and do not run extra classifier calls.
- Forced first-turn pins (`@low`/`@medium`/`@high`/`@ultra`/`@model:...`) do not run the classifier.
- If the classifier output cannot be parsed or the model fails repeatedly, that classifier model is temporarily disabled and routing falls back to the local heuristic / other classifier candidates.

#### Choosing whether to use the classifier

The classifier is off by default. To enable semantic classification, pin it to an exact endpoint:

```jsonc
{
  "router": {
    "classifierModel": "gateway/gpt-5.4-nano"
  }
}
```

Use the exact `provider/model` id from your Pi registry. If you want a Low-mode classifier, pick a model that is actually available locally and falls in Low for your active `capabilitySource`; for example, with the default Ramp source, `gpt-5.4-nano`, `qwen3.7-plus`, or another local Low model can be good candidates. `classifierModel` is an exact pin, not a mode name: use `"gateway/gpt-5.4-nano"`, not `"low"`.

You can still force it off explicitly, even if a shared config sets a classifier model:

```jsonc
{
  "router": {
    "classifier": "off"
  }
}
```

Trade-offs:

- **Default / classifier off:** no extra model call; routing relies only on local context size, prompt length, and recent tool activity.
- **Pinned low-cost classifier:** predictable and cheap, but may miss subtle hard requests.
- **Pinned stronger classifier:** may classify hard/ambiguous work better, but adds cost and is usually unnecessary because the main route still has local heuristics, manual first-turn mode pins, and cache-aware routing.

One user turn keeps one model, including tool-call continuations. Automatic routing also avoids quota-cooled plans and avoids switching away from a useful warm cache when the switch is not worth it.

### Context Window and Compaction

Pi displays context usage and decides when to compact from the selected `pi-router/auto` model. The router keeps that virtual model's `contextWindow` synchronized with the concrete model selected for the current turn. It preselects the route before Pi's preflight compaction check, refreshes the value again when the provider request starts, and restores the most recent concrete model's window when resuming a session.

As a result, a turn routed to a 272K model displays and compacts against 272K; a later turn routed to a 1M model switches the same limits to 1M. The initial 1M registration is only a startup placeholder before a session target can be identified.

## Settings

| setting | use |
| --- | --- |
| `capabilitySource` | Choose `"ramp"` or `"aa"`. |
| `modelFilter` | Include or exclude providers/models by substring. |
| `modeModels` | Pin exact endpoints for `low`, `medium`, `high`, or `ultra`. |
| `modelOverrides` | Adjust cost or metadata for known/private/local models. |
| `willingness` | Control affordable same-mode upgrades after a capability mode is selected. |
| `cacheAware` | Keep warm prompt caches when switching is not worth it. Enabled by default. |
| `quota` | Skip cooled-down plans after rate-limit headers or `429`. Enabled by default. |
| `classifier` | Tune or explicitly disable the bounded LLM classifier. Use `"off"` to disable. |
| `classifierModel` | Opt in to the classifier by pinning a specific provider/model or variant in your pool. Use an exact id, not `low`/`medium`/`high`/`ultra`. |
| `weights` | Language-neutral difficulty-scoring weights. Advanced. |
| `log` | Append routing decisions to `.pi/router.log`. |

Useful override fields:

| field | meaning |
| --- | --- |
| `costCoef` | Cost multiplier. |
| `costCoefHours` | Local-hour multipliers. |
| `canonical` | Name shown in `/auto`. |
| `costTier` | Cost-only classification: `cheap`, `standard`, `premium`, or `unknown`. |
| `capabilityMode` | Override the capability mode: `low`, `medium`, `high`, or `ultra`. |
| `profiles` | `deep`, `fast`, `coder`, `balanced`, `vision`, `frontier`. |
| `frontier` | Whether the model can appear in the frontier display/pool. |
| `benchmarkEffort` | Pi-normalized effort (`minimal`, `low`, `medium`, `high`, `xhigh`) backing a manual metric row. |
| `priceBlended`, `intelligence`, `scores`, `tps` | Raw metrics for models without benchmark data. |

Quota state is stored at `~/.pi/agent/quota-state.json`. Providers without remaining-quota headers only cool down after a real `429`.

## Core API

Other Pi extensions can resolve a model without an `ExtensionContext`:

```ts
import { resolveRouteModel } from "pi-model-auto/core";

const selection = resolveRouteModel({
  models: availableModels,
  hint: "high", // routing hint: low | medium | high | ultra | auto | provider/model
  context,
});
```

The core API loads user-level `model-router.json` and quota state by default. It never reads project config because that requires a trust decision from the host. Pass `cfg` to supply an explicit configuration or `filterQuota: false` to disable persisted cooldown filtering.

## Develop

```bash
npm run build
npm run typecheck
npm test
```

Maintainers: see [RELEASING.md](RELEASING.md) for the publish flow.
