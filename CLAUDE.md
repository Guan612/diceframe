# Architecture & Engineering Entry Point

Before modifying the repository, read the documents relevant to the task:

1. Architecture source of truth:
   - [docs/ARCHITECTURE_CN.md](docs/ARCHITECTURE_CN.md)
   - [docs/ARCHITECTURE_EN.md](docs/ARCHITECTURE_EN.md)
2. Engineering change rules:
   - [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md)
3. For permissions, persistence, migrations, multiplayer, rules, or other high-risk contracts:
   - [docs/testing-contracts.md](docs/testing-contracts.md)
4. For existing long-lived architecture decisions:
   - [docs/adr/](docs/adr/)

Key principles:

- The current architecture is a source of truth, not an immutable roadmap.
- Large refactors, module splits, migrations, and intentional breaking changes are allowed when affected contracts are handled explicitly.
- Keep translated display text separate from canonical identity.
- Locale must not accidentally change mechanics.
- Keep compatibility in explicit compatibility/adapter boundaries instead of scattering legacy branches through normal runtime code.
- Specific rulesets should not leak back into the generic engine.
- Migration correctness is more important than migration completeness; fail closed when safe conversion cannot be proven.
- Bundled/system templates must not unconditionally overwrite user data.
- AI-assisted changes must verify real repository fields and APIs instead of inventing them.
