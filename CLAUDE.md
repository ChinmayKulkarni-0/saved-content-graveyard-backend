# Conductor Commands

## Commands

| Say | I Do |
|-----|------|
| `Conductor: write tests` | `touch agentic-workflow/.write-tests` |
| `Conductor: write tests:scope [what]` | `echo "[what]" > agentic-workflow/.write-tests` |
| `Conductor: run tests` | `touch agentic-workflow/.run-tests` |
| `Conductor: ux-review` | `touch agentic-workflow/.review-ux` |
| `Conductor: ux-review:scope [what]` | `echo "[what]" > agentic-workflow/.review-ux` |
| `Conductor: code-review` | `touch agentic-workflow/.review-code` |
| `Conductor: code-review:scope [what]` | `echo "[what]" > agentic-workflow/.review-code` |
| `Conductor: security-review` | `touch agentic-workflow/.review-security` |
| `Conductor: security-review:scope [what]` | `echo "[what]" > agentic-workflow/.review-security` |
| `Conductor: spec-check` | `touch agentic-workflow/.spec-check` |
| `Conductor: spec-check:scope [what]` | `echo "[what]" > agentic-workflow/.spec-check` |
| `Conductor: fix all` | `touch agentic-workflow/.auto-fix` |
| `Conductor: fix:scope [what]` | `echo "[what]" > agentic-workflow/.auto-fix` |

See agentic-workflow/.agents/ for agent configurations.

Use `:scope` commands for large codebases to focus agents on specific features/files.
