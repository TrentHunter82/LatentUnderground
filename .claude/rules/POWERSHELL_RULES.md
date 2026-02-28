# PowerShell Rules

Rules for all `.ps1` scripts. Read before writing or modifying any PowerShell file.

## No Dead Code

1. **Never add dead code or stub features**: Every function, parameter, switch case, and code path must be functional and tested. Do not add placeholder logic, commented-out features, or unreachable branches "for later."

2. **New features must work immediately**: If a feature is added to a script, it must be fully implemented and usable in the same commit. No `# TODO: implement` blocks. No parameters that are accepted but ignored.

3. **Complementary features only when justified**: Non-core features may only be added if they directly support a core feature's functionality. They must still be fully working — "complementary" is not an excuse for incomplete code.

4. **Remove unused code paths aggressively**: If a refactor makes a function, parameter, or branch unreachable, delete it. Don't leave it behind with a comment.

5. **No speculative parameters or switches**: Don't add `-Verbose`, `-DryRun`, `-Format`, or other parameters unless the current task requires them. Add them when they're needed, not before.
