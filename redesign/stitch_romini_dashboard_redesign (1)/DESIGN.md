---
name: Warm Nordic Companion
colors:
  surface: '#fff8f4'
  surface-dim: '#e0d9d4'
  surface-bright: '#fff8f4'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#faf2ed'
  surface-container: '#f4ece7'
  surface-container-high: '#eee7e2'
  surface-container-highest: '#e8e1dc'
  on-surface: '#1e1b18'
  on-surface-variant: '#554336'
  inverse-surface: '#33302d'
  inverse-on-surface: '#f7efea'
  outline: '#887364'
  outline-variant: '#dbc2b0'
  surface-tint: '#904d00'
  primary: '#8d4b00'
  on-primary: '#ffffff'
  primary-container: '#b15f00'
  on-primary-container: '#fffbff'
  inverse-primary: '#ffb77d'
  secondary: '#4e6358'
  on-secondary: '#ffffff'
  secondary-container: '#d1e8da'
  on-secondary-container: '#54695e'
  tertiary: '#984229'
  on-tertiary: '#ffffff'
  tertiary-container: '#b7593f'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdcc3'
  primary-fixed-dim: '#ffb77d'
  on-primary-fixed: '#2f1500'
  on-primary-fixed-variant: '#6e3900'
  secondary-fixed: '#d1e8da'
  secondary-fixed-dim: '#b5ccbf'
  on-secondary-fixed: '#0b1f17'
  on-secondary-fixed-variant: '#374b41'
  tertiary-fixed: '#ffdbd1'
  tertiary-fixed-dim: '#ffb5a0'
  on-tertiary-fixed: '#3b0900'
  on-tertiary-fixed-variant: '#7c2d17'
  background: '#fff8f4'
  on-background: '#1e1b18'
  surface-variant: '#e8e1dc'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  title-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 22px
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-mobile: 0.75rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system embodies a Scandinavian-modern, tactile design language engineered for thoughtful parents managing a screen-free NFC audio experience. The emotional response evokes calm reassurance, domestic warmth, and crafted precision—reminiscent of curated wooden toys, premium Nordic audio hardware, and architectural stationery.

The style sits at the intersection of **Tactile Modernism** and **Soft Minimalism**. It rejects chaotic gamification in favor of domestic serenity: spacious layouts, velvety off-white canvas surfaces, grounded typography, and physical-metaphor widgets that mimic tangible knobs, battery meters, and audio tags. Delight is introduced through subtle micro-interactions, soft physical pill badges, figurine avatars, and playful accent tones that honor childhood wonder without visual clutter.

## Colors

The palette draws directly from Nordic interior palettes: bleached birch, clay ceramics, dried sage, and warm amber resin.

### Palette Architecture
- **Primary (`#D97706` / Warm Amber)**: Reserved for active audio playback, primary action triggers, volume highlights, and NFC link validation. Emits warmth without the urgency of warning orange.
- **Secondary (`#5B7065` / Calm Sage)**: Represents healthy hardware telemetry, system connectivity (Wi-Fi, NFC idle), and serene night-mode/sleep routines.
- **Tertiary (`#C26247` / Soft Terracotta)**: Used for secondary media interactions, tag category groupings (audiobooks, bedtime stories), and ambient warnings.
- **Neutral (`#2B2825` / Deep Charcoal & Warm Oat)**: 
  - Canvas Surface: `#F9F7F2` (Warm Oat / Porcelain).
  - Elevated Container: `#FFFFFF` (Pure Chalk White).
  - Subtle Wells & Recesses: `#F2EEE7` (Soft Birch Dust).
  - Borders: `#E5DFD5` (Soft Warm Sand).
  - Body Text: `#2B2825` (Crisp Deep Slate-Charcoal, preserving warmth over harsh pure black).
  - Subdued Text: `#78736B` (Muted Lichen Sand).

### Functional Accents
- **Indigo Accent (`#4E5D78`)**: Employed exclusively for technical settings, firmware updates, and cloud sync status.
- **Battery/Power States**: Dynamic shifts from `#5B7065` (nominal >25%) to `#D97706` (low 10-25%) to `#C26247` (critical <10%).

## Typography

The type scale is driven entirely by **Plus Jakarta Sans**, offering geometric clarity softened with humanized curves. It conveys Scandinavian furniture catalog precision while remaining legible from a distance on mobile displays.

- **Display & Headlines**: Generously tracked inward (`-0.02em`) to ground dashboard section overviews and device names.
- **Numbers & Metrics**: Tabular figures (`tnum`) must be enforced on hardware telemetry counters (battery percentages, decibel volume caps, playback durations).
- **Labels & Micro-copy**: Uppercase treatments are restricted strictly to micro telemetry tags (`label-sm`), styled with subtle letter spacing for effortless scanning.

## Layout & Spacing

The layout is built upon an 8pt modular grid structured inside a constrained fluid container:

- **Desktop & Tablet Web (>= 768px)**: 12-column dynamic fluid grid with a maximum content width of `1240px`, flanked by `margin: 2rem` and `gutter: 1.25rem`. The parent dashboard features a modular split: a persistent left rail (hardware telemetry and current physical figurine dock) and a main content deck (audio libraries, parental volume guards, sleep timers).
- **Mobile Handheld (< 768px)**: 4-column layout with `margin-mobile: 1rem` and `gutter-mobile: 0.75rem`. Dense telemetry collapses into a horizontal tactile carousel anchored beneath the header.
- **Rhythm & Hierarchy**: Card-to-card grouping utilizes `space-md` (16px), while distinct thematic domains (e.g., Device Health vs. Audio Tag Library) separate via `space-xl` (40px). Internal card padding strictly commands `space-lg` (24px) on desktop and `space-md` (16px) on mobile screens.

## Elevation & Depth

Visual hierarchy rejects harsh drop shadows and neon glows in favor of **Tonal Layers with Ambient Tactile Shadows**:

1. **Canvas (Base level 0)**: Background `#F9F7F2`. Completely flat, velvety, grounding the viewport.
2. **Structural Cards & Panels (Level 1)**: Pure white `#FFFFFF` surface bounded by a soft ghost border (`1px solid #E5DFD5`). Ambient elevation is delivered using a multi-stop warm-tinted shadow: `0 2px 4px rgba(43, 40, 37, 0.02), 0 8px 24px rgba(43, 40, 37, 0.05)`.
3. **Interactive & Floating Controls (Level 2)**: Used for active media playback sliders, floating pause buttons, and dragged NFC assignment cards: `0 4px 8px rgba(43, 40, 37, 0.04), 0 16px 32px rgba(43, 40, 37, 0.08)`.
4. **Recessed Wells / Slotted Surfaces**: Utilized for audio scrubber tracks, hardware toggle slots, and telemetry wells: background `#F2EEE7`, `box-shadow: inset 0 1px 3px rgba(43, 40, 37, 0.06)`, with no external border. This creates a tactile, physical "milled wood" or stamped matte plastic effect.

## Shapes

The form language is organic yet disciplined, pairing generous corner smoothing with structural balance.

- **Primary Cards & Telemetry Pods**: Set to `rounded-lg` (16px / `1rem`), providing a soft, touchable presence.
- **Secondary Containers & Inset Wells**: Set to standard `rounded` (8px / `0.5rem`).
- **Pills & Status Badges**: Full geometric capsule (`rounded-full` / 9999px) for figurine association tags, audio genres, battery health pills, and live playback states.
- **Physical Dial & Avatar Targets**: Circular geometry (aspect ratio 1:1) paired with inset tactile borders for NFC figurine physical representations.

## Components

### Buttons
- **Primary Action**: Amber fill (`#D97706`), bold charcoal-white text (`#FFFFFF`), `rounded-lg` (12-16px) or full pill. Smooth tactile press transform (`translate-y-[1px]` and shadow compression on active state).
- **Secondary / Soft Action**: Birch sand fill (`#F2EEE7`), charcoal text (`#2B2825`), border `1px solid #E5DFD5`. Hover transitions to `#EAE4D9`.
- **Destructive / Limit Alert**: Terracotta wash background (`rgba(194, 98, 71, 0.1)`), terracotta text (`#C26247`), border `1px solid rgba(194, 98, 71, 0.2)`.

### Hardware Telemetry Widgets
- **Battery & UPS**: Pill container housing a multi-segment fill meter (green/amber/terracotta depending on percentage). Displays real-time charging glyph and estimated battery hours remaining using `label-sm`.
- **Wi-Fi & NFC Status**: Soft pill badges with a 6px breathing status dot (`#5B7065` for connected, `#D97706` for NFC actively scanning, `#C26247` for offline).
- **Parental Decibel Guard (Volume Limit)**: A physical slider track recessed with inner shadow, featuring calibrated tick marks at 60dB, 70dB, 75dB, and 85dB (recommended safe child threshold). Capped limits are visibly locked with a brass lock badge.

### Figurine Avatar Badges & NFC Cards
- **Figurine Avatar Pod**: Circular badge (48px or 64px) with a dual ring: an outer 2px border in `#E5DFD5` and an inner soft ceramic background (`#FAF7F2`) displaying the figurine illustration or photo. When currently docked on the physical device, it displays an animated amber ambient ripple.
- **Audio Track Cards**: White card base (`#FFFFFF`) with 16px radius. Displays track/album artwork, title in `title-sm`, narrator/creator in `body-sm`, and an integrated SVG soundwave scrubber.
- **Waveform Scrubber**: Recessed birch track (`#F2EEE7`) where unplayed audio bars sit at 30% opacity, and played bars turn solid warm amber (`#D97706`) with smooth draggable scrub handles.

### Form Inputs, Toggles & Checkboxes
- **Toggles (Bedtime Lock, NFC Tap Sounds)**: Physical capsule switches. Recessed birch trough (48px × 28px) with a floating chalk-white circular nub that casts a light tactile drop shadow. Active state shifts background to `#5B7065` (Sage) or `#D97706` (Amber).
- **Input Fields (Track rename, Device Wi-Fi setup)**: Clean chalk-white background with a `1px solid #E5DFD5` border, transitioning on focus to a `2px solid #D97706` ring with subtle amber glow (`rgba(217, 119, 6, 0.15)`).
- **Chips & Filter Pills**: 32px height, full pill radius. Inactive chips use `#FFFFFF` with `#E5DFD5` borders. Selected chips turn solid `#2B2825` with off-white text (`#F9F7F2`), anchoring parents to their active view.