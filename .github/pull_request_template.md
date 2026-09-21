<!-- Title format: <type>(<scope>): <summary>  — e.g. feat(cli): dry-run prints bundle hash -->

## Summary
<!-- 2–5 bullets -->
- Problem:
- Why it matters:
- What changed:
- What did NOT change (scope boundary):

## Change type
<!-- Check all that apply -->
- [ ] Bug fix
- [ ] Feature
- [ ] Refactor (required for the fix)
- [ ] Docs
- [ ] Security hardening
- [ ] Chore / infra

## Scope
- [ ] MCP server (Choice / Noul / Score)
- [ ] CLI (`jev` binary)
- [ ] Slash commands
- [ ] Hooks
- [ ] Packaging / install
- [ ] CI / infra
- [ ] Docs

## Linked issue
<!-- e.g. Closes #5 -->
Closes #

## Root cause (bug fixes only)
<!-- Why did this happen? Write `N/A` for non-bug PRs. -->

## Test plan
<!-- Smallest reliable coverage. Write `N/A` if no test added and explain why. -->
- Target test file:
- Scenario locked in:

## User-visible / behavior changes
<!-- Include defaults, config keys, envelope shape. Write `None` if none. -->
None

## Security impact
- New permissions / capabilities? (Yes/No)
- Secrets / tokens handling changed? (Yes/No)
- New or changed network calls? (Yes/No)
- Command / tool execution surface changed? (Yes/No)
- Data access scope changed? (Yes/No)

<!-- Explain risk + mitigation for any Yes. -->

## Repro + verification
**Environment**
- OS:
- Python:
- Install method:

**Steps**
1.
2.

**Expected**
-

**Actual**
-

## Evidence
<!-- Attach at least one -->
- [ ] Failing test / log before + passing after
- [ ] `jev --dry-run` envelope snippet
- [ ] Screenshot / recording
- [ ] Perf numbers (if relevant)

## Human verification
<!-- What YOU verified locally, not just CI. -->
- Verified scenarios:
- Edge cases checked:
- What you did NOT verify:

## Compatibility / migration
- Backward compatible? (Yes/No)
- Config / env changes? (Yes/No)
- Migration needed? (Yes/No)
- If yes, exact upgrade steps:

## Risks and mitigations
<!-- Real risks only. Write `None` if none. -->
- Risk:
  - Mitigation:
