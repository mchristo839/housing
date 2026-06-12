# DESIGN.md — Design System

> STATUS: FILLED IN — updated 2026-06-12, accent set to red (with Fraunces type).
> Source of truth for how every page looks and feels.
> Project: **Find a Housing Provider** (findahousingprovider.vercel.app) — a paid
> postcode-search tool for property developers and landlords to find supported-living
> and social-housing providers commissioned in their area.

---

## 1. Brand feel
- **Adjectives:** professional, editorial, confident, commercial, trustworthy.
- **Feels like:** a specialist data publication for the property sector (think FT-meets-proptech),
  **not** a care-sector charity site and **not** a generic SaaS template.
- **Audience:** property developers, landlords, estate agents — commercially-minded, time-poor,
  allergic to fluff. Copy and design must both read "we know this sector."
- **Hard nos:** care-worker stock photography, soft "caring" pastels, purple-to-pink gradients,
  generic centred-headline hero, template/website-builder default look, emoji in UI copy.

---

## 2. Colour system

| Role | Value | Notes |
|------|-------|-------|
| Background | `#FFFFFF` | pure white, page base |
| Surface | `#FFFFFF` | cards, raised areas |
| Surface alt | `#FCF7F7` | warm blush tint — alternating section bands |
| Text primary | `#1A1418` | near-black with warm undertone |
| Text muted | `#5A4E51` | secondary text, labels |
| **Accent** | `#C8102E` | **red** — does ALL the heavy lifting |
| Accent hover | `#DA1A38` | brighter red for interactive states |
| Accent soft | `#FBEAEC` | red-tinted backgrounds, chips, upsell card |
| Border | `#F2DFE1` | warm hairline dividers, card borders |
| Focus ring | `#E0314B` | 2px, always visible (`:focus-visible` global) |

Supporting (used only for status semantics, never decoration):
- Verified badge green: text `#1B5E20` on `#E8F5E9`, border `#A5D6A7`
- Listed chip grey: text `#5D6770` on `#F1F3F5`
- Error red: `#9D2F2F`

**Rules:** one accent (red) does the heavy lifting. Solid red panels with white
text are the signature high-emphasis surface (price bar, stats card, "you" role card,
featured pricing tier). Shadows are red-tinted (`rgba(200,16,46,…)`), never grey-blue.

---

## 3. Typography

| Role | Font | Weight | Size / Tracking |
|------|------|--------|-----------------|
| Display / hero h1 | **Fraunces** (serif) | 600 | clamp(2.3–3.4rem), -0.015em, line-height 1.08 |
| Section headings (h2) | **Fraunces** | 600 | clamp(1.7–2.3rem), -0.01em |
| Paywall count headline | **Fraunces** | 600 | clamp(1.6–2.3rem) |
| Sub-headings (h3), card titles | Inter | 700 | 1.0–1.3rem, -0.01em |
| Body | Inter | 400 | 1rem, line-height 1.6–1.65 |
| Labels / eyebrows | Inter | 600–700 | .72–.75rem, uppercase, +0.08em tracking |
| Numbers (prices, stats) | Inter + `tnum` | 700–800 | tabular figures, tight tracking |

**Rules:** exactly two families. Fraunces = editorial headlines only (h1/h2 + paywall count).
Inter = everything else. The red italic `.em` span inside the hero h1 is a signature
move — keep it. Emphasised keywords inside Fraunces headings may be italic + accent colour.

Loaded via: rsms.me/inter + Google Fonts Fraunces (opsz 9..144, weights 500–700, display=swap).

---

## 4. Spacing and layout
- Spacing scale (CSS vars): 4, 8, 12, 16, 24, 32, 40, 48, 64, 96 px. Use `var(--s*)`, do not invent values.
- Max content width 1200px (`--maxw`), centred. Narrow text sections use `.narrow-wrap` at 880px.
- Section rhythm: `--s64` vertical padding per section, 1px `--border` top divider,
  alternating `#FFFFFF` / `--surface-alt` bands.
- Corner radius: 10px base (`--r`); cards 12–14px; hero search-card & stats card 18px; pills 999px.

---

## 5. Motion and animation
- Entrances: fade + small rise, 400–600ms, easing `cubic-bezier(0.16, 1, 0.3, 1)` (`--ease`).
- Hero skyline: two parallax layers drifting at 90s/60s, red at 22%/35% opacity.
- Card hovers: translateY(-3px) + red-tinted shadow (role cards, teaser cards).
- `prefers-reduced-motion: reduce` is honoured globally (see styles.css) — keep it working.
- Signature moment per page = ONE: home page already has the skyline drift + deal-flow diagram.
  Do not add competing effects.

---

## 6. Component rules
- **Buttons:** `.btn-primary` solid red → white text; on red surfaces invert
  (white bg, red text). `.btn-secondary` outline. All have hover + `:focus-visible` ring.
- **Search card:** white, 18px radius, red-tinted elevation shadow, 2px red border
  on the input. This is the conversion centrepiece — never bury it below the fold.
- **Solid red panels** (price bar, hero stats card, role-card.you, featured pricing tier):
  white text at 800 weight for numbers, `rgba(255,255,255,.8)` for sub-labels.
- **Cards:** 1px `--border` + soft red shadow on hover; never heavy border AND heavy shadow.
- **Badges:** ✓ Verified (green), Listed (grey) — semantic only, defined in §2.
- **Checklists:** red `✓` glyph via `::before`, never emoji.
- **Diagrams:** inline SVG using CSS vars (`var(--accent)` etc.) so they re-theme automatically.
  The deal-flow diagram (4 nodes + rent-return banner) is the canonical example.
- **Inputs:** visible focus ring (`--accent-soft` glow), comfortable padding.

---

## 7. Page inventory (keep consistent)
- **Home:** hero (search card + stats card + skyline) → role cards + deal-flow diagram →
  what's-in-your-list cards → 3 steps → why-valuable → small developers → lease vs AST →
  what's included → pricing (3 tiers, middle featured red) → FAQ (details/summary) → closing CTA.
- **Paywall:** eyebrow scope chip → Fraunces count headline → tier list → £12 upsell card →
  red price bar → notify signup (surface-alt + red) → LHA teaser table.
- **Results:** trust banner → filter sidebar → tiered provider cards with badges.
- Guides/About/Resources: text pages on the same tokens.

---

## 8. Anti-generic checklist (self-check before done)
- [ ] No purple/pink gradient hero.
- [ ] Headline is specific to the product, not "The future of X."
- [ ] At least one signature visual moment a template would not have
      (home: skyline drift + deal-flow diagram + red stats card).
- [ ] Palette stayed within §2 — one red accent, semantic green/grey only on badges.
- [ ] Fraunces on h1/h2 only; Inter everywhere else; no third font.
- [ ] Spacing used the scale.
- [ ] Every interactive element has a hover/focus state.
- [ ] `prefers-reduced-motion` still honoured.
- [ ] Mobile: hero-right hides <880px, grids collapse, diagram scrolls horizontally.
- [ ] Does not look like a website-builder default.
