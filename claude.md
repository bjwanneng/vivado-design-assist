# 🤖 CLAUDE.md - Development Protocol


## ⚖️ Core Instructions (CRITICAL)
1. **Always Sync First**: At the start of every session, you MUST read `readme_first.md` to understand the current progress, state, and context.
2. **Task Decomposition**: Before coding any major feature, output a `/plan`. Break the task into small, atomic sub-tasks (max 15 mins per task).
3. **Incremental Execution**: Implement one sub-task at a time. Run tests immediately after. Do not move to the next task until the current one is verified.
4. **Mandatory Documentation**: After finishing a task or before ending a session, you MUST update `readme_first.md` with the latest status and next steps.
5. **No Blind Coding**: Use `ls` and `cat` to verify file contents before making assumptions about the existing codebase.

## 🎨 Coding Standards
- Style: Use TypeScript with functional patterns where possible.
- Error Handling: No silent failures. Use descriptive error messages or Result types.
- Testing: Every new feature requires a corresponding test file.


## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
` ` `text
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
` ` `