# CLAUDE.md — Project memory for Claude Code

Claude reads this file at the start of every session. It sets the rules for how this project is built.

## Ask about the look first
- Before building any UI, check `DESIGN.md`. If its status says "NOT FILLED IN YET" or its fields read "to be set," DO NOT start building.
- Instead, run the `design-intake` skill: ask me about the vibe, colours, and type, then fill in `DESIGN.md` from my answers and confirm it with me.
- Only build pages once `DESIGN.md` is filled in and I have approved it.
- If I later ask to change the look, colours, or branding, run `design-intake` again.

## Always do this
- Read `DESIGN.md` before writing or changing any UI. Treat it as the source of truth for colours, type, spacing, and motion.
- When a reference page exists in `references/`, study it first and match its quality and structure, without copying it one-to-one.
- Keep the design consistent across every page and section. The fourth page should feel like the first page. Do not let the style drift.

## How to build (the workflow)
1. **Intake.** If the look is not set yet, ask first (see above).
2. **Reference.** Look at `DESIGN.md` and any file in `references/`.
3. **Generate.** Build the page or section using that system.
4. **Inspect.** Run the anti-generic checklist at the bottom of `DESIGN.md`. Fix anything that fails.
5. **Iterate.** Expect many small refinements. After each of my notes, make the smallest change that satisfies it. Do not redesign unless I ask.
6. **Remix only when I say so.** Turning a page into a new medium (slides, mobile variant, promo) is a remix. Default to iteration.

## Skills available in this project
- `design-intake` — asks me about the look and colours, then writes `DESIGN.md`. Runs before the first build.
- `web-design-system` — the standard process for building a page from `DESIGN.md`.
- `copywriting` — tighten and sharpen any text on the page.
- `special-effects` — add a signature moment (WebGL background, 3D element, animated accent). Use sparingly, usually once per page.

Invoke a skill by name, for example: "use the special-effects skill for the hero."

## Hard rules
- No purple-to-pink gradients. No generic centred-headline-plus-two-buttons hero.
- One accent colour. Stick to the spacing scale in `DESIGN.md`.
- Every interactive element needs a hover and focus state.
- Respect `prefers-reduced-motion`.
- Mobile must look as considered as desktop, not an afterthought.

## My working style
- I prefer terse, incremental changes. Short instruction, you make one focused change, repeat.
- Ask questions as multiple choice with options where you can, not open-ended.
- Give me the change, not a long explanation, unless I ask why.
- When you finish a build, list what you changed in a few bullets so I can scan it.
