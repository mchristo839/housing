# Better Websites with Claude Code — Setup Guide

A plain-language walkthrough for getting Claude Code to build consistent, premium, non-generic websites. Based on the design.md + skills workflow.

---

## The idea in one minute

Three files do the work:

- **DESIGN.md** is the recipe. Your colours, fonts, spacing, and motion rules. Claude reads it every time so every page matches.
- **Skills** are the ingredients. Reusable prompts for specific jobs (the standard build process, sharpening copy, adding a standout effect).
- **references/** holds the finished dish. Example pages you admire, so Claude has a quality bar to match.

Wire those up once and Claude stops producing generic "vibecoded" pages and starts producing consistent ones that look designed.

The starter kit (`claude-code-design-kit`) already contains all of these. `DESIGN.md` ships blank on purpose. The first time you ask Claude to build, it interviews you about the look and colours, then fills `DESIGN.md` in from your answers. No inherited taste, your direction from the start.

---

## Step 1 — Make sure Claude Code is installed

If you already use Claude Code, skip this.

If not, install it (you need Node.js first), then sign in:

```
npm install -g @anthropic-ai/claude-code
claude
```

The official install page is at https://docs.claude.com/en/docs/claude-code/overview if you hit any snag.

---

## Step 2 — Drop the kit into your website project

Unzip `claude-code-design-kit`. Inside you will find:

```
CLAUDE.md                  <- the rules Claude reads every session
DESIGN.md                  <- your design system (the recipe)
references/                <- example pages you want to match
.claude/skills/            <- the skills
   design-intake/          <- asks you about the look, then fills DESIGN.md
   web-design-system/
   copywriting/
   special-effects/
```

Copy all of these into the root folder of your website project (the folder you open Claude Code in). The `.claude` folder starts with a dot, so it may be hidden. In your file viewer turn on "show hidden files" if you do not see it.

If you want these available in **every** project instead of one, copy `CLAUDE.md` and the `skills` folder into your personal `~/.claude/` folder. For now, project-level is simpler.

---

## Step 3 — Let it ask you about the look

`DESIGN.md` starts blank. You do not fill it in by hand (though you can). Instead, the first time you ask Claude Code to build, it runs the `design-intake` skill and asks you a short set of questions, mostly multiple choice:

- The overall vibe (minimal and premium, bold and energetic, warm and friendly, technical and precise, editorial and elegant).
- A site or brand it should feel like.
- Light or dark.
- Your brand colours, or whether it should pick a palette for you.
- The type feeling.
- Anything to avoid.

Answer in a sentence or two. If you would rather it just decide, say "you choose" and it picks sensible defaults. It then fills in `DESIGN.md` (real colours, fonts, vibe), shows you a summary, and waits for your thumbs up before building.

To kick it off, just say:

> Set up the design for my site.

or simply ask it to build a page and it will run the intake first because `DESIGN.md` is still blank.

Tip: do not over-specify. Give it a strong direction and let it work within that. If you nail down every pixel, every page comes out identical.

To change the look later, say "redo the design, I want it [warmer / darker / more editorial]" and it runs the intake again.

---

## Step 4 — Add at least one reference

Open the site you want your output to feel like. Save the page (or take a full screenshot) and put it in the `references/` folder. Even one good example sharply raises quality, because Claude has a real target instead of guessing.

Collect more over time. That folder becomes your design "second brain."

---

## Step 5 — Build a page

Open Claude Code in your project folder and ask, for example:

> Build a landing page for [your product]. It is [one sentence on what it does and who it is for]. Use the web-design-system skill, follow DESIGN.md, and match the quality of references/hero-reference.html.

Claude will run the intake first if the look is not set yet, then read DESIGN.md, follow the workflow, run the anti-generic checklist, and report what it built.

---

## Step 6 — Iterate, do not restart

This is the habit that separates a one-shot toy from a real page. Give short, specific notes and let Claude make one focused change each time:

- "Tighten the headline tracking."
- "Hero feels flat. Use the special-effects skill, subtle animated background, on-brand colours."
- "Sharpen the copy in the features section. Use the copywriting skill."
- "More whitespace between sections."
- "Make the mobile hero as strong as desktop."

Expect dozens of small passes, not one big prompt. That is normal and it is where the quality comes from.

---

## Step 7 — Remix into other formats (later)

Once a page is good, reuse the same DESIGN.md to spin up matching pieces:

- "Make a mobile version of this page."
- "Turn the hero into a slide deck cover using the same design system."
- "Build a pricing page that matches."

Because they all read the same DESIGN.md, they stay consistent instead of drifting.

---

## The skills, in plain terms

- **design-intake** — asks you about the look and colours, then writes `DESIGN.md`. Runs automatically before your first build, or whenever you want to change the look.
- **web-design-system** — the default. The proper process for building any page from your system. It runs the quality checklist before calling anything done.
- **copywriting** — point it at any text to make it specific and confident instead of vague.
- **special-effects** — your standout moment. One WebGL background, 3D element, or animated accent per page. Used sparingly, this is what makes a page memorable.

You add your own skills the same way: make a folder in `.claude/skills/`, add a `SKILL.md` with a name and description at the top, then write the instructions. Build up a library and that becomes your edge.

---

## Quick reference

| You want to... | Say this |
|----------------|----------|
| Set the look first | "Set up the design for my site" |
| Build a page | "Build [page], follow DESIGN.md, use the web-design-system skill" |
| Fix vague text | "Use the copywriting skill on this section" |
| Add a wow moment | "Use the special-effects skill on the hero, keep it on-brand" |
| Stay consistent | (Automatic, as long as DESIGN.md and CLAUDE.md are in the folder) |
| Make a variant | "Make a mobile/pricing/slide version using the same design system" |
| Change the whole look | "Redo the design, I want it [warmer / darker / more editorial]" |

---

## The one rule worth remembering

You make the decisions, Claude moves the pixels. Keep a strong DESIGN.md, collect references you admire, iterate in small steps, and the output stops looking like everyone else's.
