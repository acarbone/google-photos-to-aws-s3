# Connectors (MCP)

Inventory and governance for the plugins/connectors an autonomous loop (or a
human, during interactive verification) may use to reach outside the repo —
issue trackers, chat, cloud dashboards, shared docs. This is the
"connectors" building block from `spec/design/06_loop_engineering.md`.

This is a **pattern**, not a mandate: teams fill in their own entries. The
table below is seeded with this team's actual stack plus the connectors
already referenced in `docs/quality-and-verification.md` §8.

---

## Inventory

| Connector | Purpose | Access level | May be used by | Allowed at output tier |
|---|---|---|---|---|
| Slack MCP | Post findings, ask for review, receive triage requests | Write (post only; never delete/edit others' messages) | `explorer` (via `loop-triage`), `loop-verifier`, humans | A, B, C |
| GitLab MCP | Read issues/MRs/pipelines; open MRs; comment; update tickets | Read (all) + Write (MR/comment/ticket only — never merge, never force-push, never edit protected branch settings) | `explorer` (read), implementer (write, post-verifier only) | C for writes; A/B for reads |
| AWS CloudWatch MCP | Error rates, alarms, log queries for deployed changes | Read-only | `explorer`, `loop-verifier`, humans | A, B, C |
| AWS Cost Explorer MCP | Spend and anomaly detection (incl. the loops' own model spend) | Read-only | `explorer`, humans | A, B, C |
| Google Drive / Docs / Sheets / Slides MCP | Read specs and requirement docs; write recurring reports (status digests, cost reports) | Read + Write (documents the team designates; never Drive-wide delete or permission changes) | `explorer` (read), `loop-triage` (write to designated report docs) | A, B, C |
| Grafana MCP | Production error rates, traces, dashboards | Read-only | `explorer`, `loop-verifier`, humans | A, B, C |
| Octocode MCP | Cross-repo code search | Read-only | `explorer`, humans (planning phase) | A, B, C |
| `<your issue tracker>` | Backlog read, ticket updates | Read + Write (ticket only) | `explorer` (read), implementer (write) | C for writes |

Grafana MCP and Octocode MCP are the same connectors already referenced in
`docs/quality-and-verification.md` §8 for human-driven post-deployment and
cross-repo verification; here they gain an explicit access tier and are
available to loops under the same read-only constraint.

---

## Governance rules

1. **Read-only by default.** A connector is registered read-only until
   someone deliberately promotes it and records why.
2. **No credential is scoped wider than the loop's output tier.** A tier-A
   loop gets read-only tokens, full stop — the guardrail is the token, not
   the prompt.
3. **Destructive operations are never available to an unattended loop**: no
   merge, no force-push, no delete, no permission changes, no message
   deletion.
4. **Every connector write is traceable** to the `inbox.md` finding that
   caused it (governance rule 4 in `spec/design/06_loop_engineering.md`).
5. Cross-referenced from `docs/quality-and-verification.md` §8 and §11.

---

## Wiring guide

The table above states the principle. This section shows the pattern that
enforces it — so the guardrail is the credential set an agent can load, not
just an instruction it is expected to follow.

### One MCP server entry per access level, not one per service

The same service is registered **twice** under distinct names when it needs
both a read-only and a write-capable identity:

- `gitlab-ro` — read-only token, available to `explorer` and every tier-A
  loop.
- `gitlab-rw` — MR/comment scope only, available to the implementer in a
  tier-C loop.

A tier-A loop that cannot see `gitlab-rw` in its available server list
cannot be prompt-talked into using it — the boundary is structural, not
persuasive.

### Scope the token, not the instructions

Minimum credential per connector:

| Connector | Read identity (`-ro`) | Write identity (`-rw`) |
|---|---|---|
| GitLab | Project access token, `read_api` scope | Project access token, `api` scope, restricted to MR/comment endpoints where the platform supports it |
| AWS CloudWatch / Cost Explorer | IAM role limited to `cloudwatch:Get*`, `cloudwatch:Describe*`, `ce:GetCostAndUsage` | Not applicable — this connector is read-only at every tier |
| Slack | App with `chat:write` only | Same — no `chat:write.customize`, no message-delete scope, ever |
| Google Drive/Docs/Sheets | Service account shared into the specific folder / specific report Sheet only | Same account, write access limited to the designated report documents — never Drive-wide |

### Config sketch

Map each loop's declared output tier (in `loop.md`) to the server names it is
permitted to load:

```yaml
# Illustrative — actual MCP config format depends on the tool (Claude Code / Cursor)
servers:
  gitlab-ro:   { scope: read_api }
  gitlab-rw:   { scope: api, restrict: [merge_requests, notes] }
  cloudwatch-ro: { role: loop-readonly }
  slack-post:  { scope: chat:write }

# Tier → permitted servers, reviewed alongside the charter
tier_A: [gitlab-ro, cloudwatch-ro, slack-post]
tier_B: [gitlab-ro, cloudwatch-ro, slack-post]          # + local git, no connector promotion
tier_C: [gitlab-ro, gitlab-rw, cloudwatch-ro, slack-post]
```

Review this mapping together with `loop.md`'s "Output tier" field — a charter
edit that raises the tier is incomplete until the credential set is updated
to match.

### Secret handling

Tokens live in the environment or the team's secret store — **never** in
`loop.md`, never in a skill file, never in a finding. A finding that quotes a
credential is itself an incident: treat it as one and rotate the token
immediately.

### Rotation and revocation

Each entry names its owner and its expiry. A loop retired means its
write-tier token is revoked, not left dormant.

### Verification step

Before promoting a loop to tier B or C, confirm the read-only token actually
fails on a write call. An untested boundary is an assumed one.
