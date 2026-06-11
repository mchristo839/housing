# DESIGN.md — Design System

> STATUS: FILLED IN. Source of truth for how every page looks and feels.
> Project: **Find a Housing Provider** (findahousingprovider.co.uk) — a B2B tool
> for landlords to find care & supported-housing providers seeking properties in their area.

---

## 1. Brand feel
- **Adjectives:** professional, trustworthy, precise, commercial.
- **Feels like:** a modern proptech / commercial-property tool (think a clean B2B SaaS), **not** a care-sector charity site.
- **Hard nos:** care-worker stock photography, soft "caring" pastels, purple-to-pink gradients, generic centred-headline hero, template/website-builder default look.

---

## 2. Colour system

| Role | Value | Notes |
|------|-------|-------|
| Background | `#FAFAF8` | warm off-white, page base |
| Surface | `#FFFFFF` | cards, raised areas |
| Surface alt | `#F2F4F1` | subtle fills, sidebar, input rows |
| Text primary | `#1A2B28` | near-black slate |
| Text muted | `#5A6B66` | secondary text, labels |
| Accent | `#0F5C4E` | deep teal-green — does the heavy lifting |
| Accent hover | `#147560` | brighter teal-green for interactive states |
| Accent soft | `#E3EFEB` | accent-tinted backgrounds, active chips |
| Border | `#E6E8E4` | hairline dividers, card borders |
| Focus ring | `#147560` | 2px, always visible |

Rules:
- One accent colour (`#0F5C4E`) does the heavy lifting. No second accent.
- No flat purple-to-pink gradient. Backgrounds stay neutral; colour comes from the accent on CTAs, links, active states, and contract-credibility signals.

---

## 3. Typography

| Role | Font | Weight | Size / Tracking |
|------|------|--------|-----------------|
| Display / hero | Inter | 700 | clamp(2.4rem, 5vw, 3.6rem), tracking -0.02em |
| Headings | Inter | 600 | tracking -0.01em |
| Body | Inter | 400 | line-height 1.6 |
| Mono / labels | Inter | 600 | 0.75rem, uppercase, tracking 0.08em |

Rules:
- One family: **Inter** (variable). Weights carry the hierarchy.
- Font smoothing on (`-webkit-font-smoothing: antialiased`).
- Tabular numbers for employee counts / contract counts (`font-variant-numeric: tabular-nums`).

---

## 4. Spacing and layout
- Spacing scale: `4, 8, 12, 16, 24, 32, 48, 64, 96, 128` px. Use these only.
- Generous whitespace; when unsure, add more.
- Max content width `1200px`, centred. Results layout: filter sidebar `280px` + results column.
- Consistent vertical rhythm between sections (`64–96px` desktop, `48px` mobile).

---

## 5. Motion and animation
- Entrances: fade + small upward move (8–16px), 400–500ms, easing `cubic-bezier(0.16, 1, 0.3, 1)`.
- Results cards reveal staggered (~40ms apart, cap the stagger).
- Hover states on everything interactive (cards lift 2px + border → accent).
- No big WebGL hero needed; the signature moment is the postcode-resolve transition into ranked results.
- Always respect `prefers-reduced-motion`.

---

## 6. Component rules
- **Buttons:** primary = accent fill, white text, hover → accent-hover + 1px lift. Secondary = surface with border, hover → accent border + accent text.
- **Cards:** 1px border (`#E6E8E4`) + very soft shadow on hover only. Radius `10px` everywhere.
- **Inputs:** large postcode input, visible 2px focus ring (`#147560`), comfortable padding (16px).
- **Badges/chips:** area + sector tags use `Surface alt` fill; active filter chips use `Accent soft`. Contract count is the one accent-coloured credibility signal.
- Consistency beats novelty. The about page must feel like the homepage.

---

## 7. Anti-generic checklist (self-check before done)
- [ ] No purple/pink gradient hero.
- [ ] Headline is specific ("Find care & housing providers seeking properties in your area"), not "The future of X."
- [ ] Signature moment: the postcode → resolved-council → ranked-results reveal.
- [ ] Palette stayed within the colours above (one accent).
- [ ] Spacing used the scale.
- [ ] Every interactive element has hover + focus state.
- [ ] No care-sector stock imagery. Reads as a B2B property tool.
- [ ] Mobile hero and results as considered as desktop.
