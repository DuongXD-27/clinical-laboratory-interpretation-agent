------------------------------------------------------------
# VMEC Clinical Liquid Glass — Visual Contract
------------------------------------------------------------

## 1. DESIGN DIRECTION

Clinical Calm
×
Liquid Glass
×
Restrained Holographic Glow

The interface must remain a healthcare product first.

Never become:
- cyberpunk
- neon
- gaming UI
- sci-fi HUD
- generic AI dashboard

------------------------------------------------------------
## 2. MATERIAL HIERARCHY

LEVEL 1 — BUBBLE / LIQUID GLASS

Allowed mainly for:
- primary page hero
- major summary surface
- app chrome
- active navigation
- selected interactive surfaces
- Quick Actions

Use sparingly.

LEVEL 2 — SOFT CLINICAL OPAQUE

Required mainly for:
- report/history rows
- medical values
- OCR review
- dense clinical data
- forms requiring high readability
- Doctor queue rows

May use:
- soft radius
- subtle border
- restrained shadow

Must not look like a different design system.

LEVEL 3 — SEMANTIC MEDICAL UI

Includes:
- NORMAL
- HIGH
- LOW
- CRITICAL
- UNKNOWN
- verification/review status

Medical semantics must remain stable and independent from decorative
glass/holographic treatment.

------------------------------------------------------------
## 3. GLASS EDGE RULE

A glass object should normally expose:

ONE perceived physical edge.

Use:
- specular highlight
- localized refraction
- subtle cool shadow
- non-uniform edge lighting

Avoid:
- obvious cyan perimeter
- multiple visible rings
- rainbow outlines
- neon glow

The edge should feel like material catching light,
not a CSS border.

------------------------------------------------------------
## 4. HOLOGRAPHIC RULE

Holographic accent is DECORATIVE ONLY.

Allowed:
- active navigation
- AI/interactive surface
- hero reflection
- Quick Action hover/focus
- brand atmospheric light

Never use holographic styling to represent:

NORMAL
HIGH
LOW
CRITICAL
UNKNOWN
verification state

CRITICAL must never be rainbow/holographic.

------------------------------------------------------------
## 5. PATIENT CONTENT RAIL

All Patient pages must share a consistent left content rail / gutter.

Different content widths are allowed.

STANDARD WIDTH:
- Dashboard
- Profile
- reading-oriented content

WIDE WORKSPACE:
- Analysis
- History
- Trends

RULE:

Different max-width is acceptable.

Randomly different left alignment is NOT acceptable.

Page heading and primary content must visibly belong to the same shell
grid system across routes.

------------------------------------------------------------
## 6. PATIENT / DOCTOR DENSITY

Patient:
- spacious
- reassuring
- lower density

Doctor:
- compact
- operational
- higher information density

Both use the same:
- design tokens
- material language
- typography
- icon family
- glass rules

Do not reuse identical page composition blindly.

------------------------------------------------------------
## 7. MEDICAL DATA PROTECTION

Keep predominantly opaque:

- critical cards
- abnormal cards
- reference ranges
- analyte values
- report rows
- OCR data tables
- citations
- Doctor queue rows

Glass is not a medical semantic.

------------------------------------------------------------
## 8. MOTION

Allowed:
150–220ms restrained interaction.

Never:
- pulsing critical status
- flashing medical warning
- continuous holographic animation
- animated medical gradients

Always respect prefers-reduced-motion.

------------------------------------------------------------
## 9. FALLBACK

If gradients, blur, shadow or backdrop-filter disappear:

- hierarchy must remain understandable
- text must remain readable
- medical meaning must remain unchanged

------------------------------------------------------------
## 10. FUTURE TIP RULE

Before modifying a Patient or Doctor UI page:

read this Visual Contract first.

If a TIP conflicts with this document:

STOP and report the conflict.

Do not silently invent a new design language.
