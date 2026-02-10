# Agent Guidelines

## Workflow Orchestration (ALL AGENTS MUST FOLLOW)

### 1. Skill Discovery (Do Once at Session Start)
- Before starting your first task, search for relevant skills: npx skills find <query>
- Use 2-3 targeted queries based on YOUR role and the project's tech stack
- Install useful skills: npx skills add <owner/repo@skill> -g -y
- Skills provide specialized domain knowledge (frameworks, best practices, patterns)
- Browse https://skills.sh/ for the full catalog
- Only do this once per session, not before every task

### 2. Web Research (Do Once at Session Start)
- Before starting your first task, use WebSearch or subagents to research best practices for YOUR role and the project's tech stack
- Run 2-3 targeted web searches (e.g. 'FastAPI best practices 2026', 'React testing patterns', 'Python security checklist')
- Focus on: current best practices, common pitfalls, recommended libraries, architecture patterns
- Summarize key findings in tasks/todo.md under a ## [YourName] Research Findings heading
- Use findings to inform your skill installation and implementation approach
- Only do this once per session, not before every task

### 3. Plan Then Execute (NO Plan Mode)
- NEVER use EnterPlanMode or AskUserQuestion - you are running unattended and these will block forever
- For non-trivial tasks (3+ steps): write your plan to tasks/todo.md, then IMMEDIATELY execute it
- If something goes sideways, STOP, update your plan in tasks/todo.md, then continue executing
- Write detailed specs upfront to reduce ambiguity, but always follow through with implementation
- You are fully autonomous - plan internally, decide, and act without waiting for approval

### 4. Spawn Teams (Parallel Subagents)
- You are a team lead, not a solo developer. Use the Task tool aggressively to parallelize work
- Break each task into independent subtasks and launch multiple subagents IN PARALLEL (single message, multiple Task tool calls)
- Use subagents for: research, writing tests, implementing independent modules, code exploration, builds
- Run background agents for long-running tasks while you continue other work
- Only do sequential work when there are true dependencies between subtasks
- Goal: maximize throughput by keeping multiple agents working simultaneously

### 5. Self-Improvement Loop
- After ANY correction or failed attempt: update tasks/lessons.md with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Read tasks/lessons.md at session start - learn from past mistakes before writing code

### 6. Verification Before Done
- NEVER mark a task [x] without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: Would a staff engineer approve this?
- Run tests, check logs, demonstrate correctness
- If it does not pass verification, it stays [ ]

### 7. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask - is there a more elegant way?
- If a fix feels hacky: Knowing everything I know now, implement the elegant solution
- Skip this for simple, obvious fixes - do not over-engineer
- Challenge your own work before presenting it

### 8. Autonomous Bug Fixing
- When given a bug report or encountering a bug: just fix it. Do not ask for hand-holding
- Point at logs, errors, failing tests then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Core Principles
- Simplicity First: Make every change as simple as possible. Impact minimal code.
- No Laziness: Find root causes. No temporary fixes. Senior developer standards.
- Minimal Impact: Changes should only touch what is necessary. Avoid introducing bugs.

## Task Management Protocol
1. Plan First: Write plan to tasks/todo.md with checkable items (NEVER use EnterPlanMode - you are unattended)
2. Execute Immediately: After writing the plan, start implementing right away. Do not wait for approval.
3. Spawn Teams: Launch parallel subagents for independent subtasks to maximize throughput
4. Track Progress: Mark items complete as you go in tasks/TASKS.md
5. Explain Changes: High-level summary in logs/activity.log at each step
6. Document Results: Add review notes to tasks/todo.md
7. Capture Lessons: Update tasks/lessons.md after corrections or discoveries

## Signal Protocol
- backend-ready.signal - Claude-1 creates when core APIs/logic work
- frontend-ready.signal - Claude-2 creates when UI connects to backend
- tests-passing.signal - Claude-3 creates when all tests pass
- phase-complete.signal - Claude-4 creates when all agents report done

## Heartbeat Protocol
Update .claude/heartbeats/{your-name}.heartbeat regularly so the supervisor knows you are alive.

## Handoff Protocol
If context is filling up or you are getting slow:
1. Write current state to .claude/handoffs/{your-name}.md
2. Include: what is done, current task, next steps, blockers
3. Exit cleanly - the agent-loop will restart you with the handoff

## Project Patterns
(Reusable patterns discovered during development - agents add here as they learn)

## Conventions
(Coding conventions and standards for this project)

## Gotchas
(Things to watch out for - agents add here when they hit surprises)
