---
name: Sisi-TV Surveillance System
colors:
  surface: '#051424'
  surface-dim: '#051424'
  surface-bright: '#2c3a4c'
  surface-container-lowest: '#010f1f'
  surface-container-low: '#0d1c2d'
  surface-container: '#122131'
  surface-container-high: '#1c2b3c'
  surface-container-highest: '#273647'
  on-surface: '#d4e4fa'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#d4e4fa'
  inverse-on-surface: '#233143'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#ffb4aa'
  on-secondary: '#690003'
  secondary-container: '#c5020b'
  on-secondary-container: '#ffd2cc'
  tertiary: '#ececef'
  on-tertiary: '#2f3133'
  tertiary-container: '#d0d0d3'
  on-tertiary-container: '#57595b'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#ffdad5'
  secondary-fixed-dim: '#ffb4aa'
  on-secondary-fixed: '#410001'
  on-secondary-fixed-variant: '#930005'
  tertiary-fixed: '#e2e2e5'
  tertiary-fixed-dim: '#c6c6c9'
  on-tertiary-fixed: '#1a1c1e'
  on-tertiary-fixed-variant: '#454749'
  background: '#051424'
  on-background: '#d4e4fa'
  surface-variant: '#273647'
typography:
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
  headline-md:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  grid-margin: 1rem
  gutter: 0.75rem
  video-aspect-ratio: 16/9
  touch-target-min: 44px
---

## Brand & Style
The design system for Sisi-TV is built on the pillars of **reliability, precision, and vigilant intelligence**. It targets professional security personnel and tech-savvy homeowners who require immediate, low-latency visual feedback. 

The visual style is **Tech-Focused Minimalism with Tactical Overlays**. By utilizing a dark-mode-first approach, we minimize screen glare during night monitoring and maximize the "pop" of critical status indicators. The aesthetic borrows from command-center interfaces—utilizing clean lines, monospaced data highlights, and a clear hierarchy of urgency.

**Boy Sisi Integration:**
The mascot acts as the human interface for the technical system. He should appear in high-fidelity vector format for empty states (e.g., "No Cameras Connected"), onboarding walkthroughs, and proactive alert notifications. While the UI is technical, Boy Sisi provides a "friendly professional" touch, often appearing with a headset or tablet to symbolize active monitoring.

## Colors
This design system utilizes a high-contrast dark palette optimized for OLED screens and long-duration monitoring.

*   **Primary (Electric Cyan):** Used for "Live" indicators, active connection states, and primary action buttons. It represents the "pulse" of the system.
*   **Secondary (Alert Red):** Reserved exclusively for critical states: recording in progress, motion detection alerts, and system errors.
*   **Neutral/Backgrounds:** We use a deep charcoal (#0F1113) for the base canvas to reduce eye strain. Surface layers use #1A1C1E to create subtle depth.
*   **Technical Data:** A muted slate blue is used for non-critical metadata (timestamps, IP addresses) to ensure they are legible but do not distract from the video feed.

## Typography
The typography strategy prioritizes **instant scanability**. 

We use **Inter** for standard UI elements and body text due to its exceptional legibility at small sizes on mobile displays. For all technical data, including camera names, RTSP strings, IP addresses, and OSD (On-Screen Display) timestamps, we utilize **JetBrains Mono**. The monospaced nature of JetBrains Mono ensures that shifting numbers (like seconds in a clock) do not cause horizontal layout jitter, maintaining a stable visual environment for the viewer.

## Layout & Spacing
The layout follows a **Rigid Tactical Grid**. On mobile, the primary view is the "Multi-View Grid," which defaults to a 2x2 or list-based layout depending on the number of active feeds.

*   **Safe Zones:** All video feeds must have a 4px inner margin for status overlays (REC, Live, Camera Name) to ensure text does not touch the edge of the frame.
*   **Fluidity:** The layout is fluid within the viewport, but video containers must strictly maintain a 16:9 aspect ratio to prevent image distortion.
*   **Density:** The UI is "Compact-Professional," maximizing the screen real estate for video feeds while keeping controls (PTZ, Snapshot, Mic) tucked into a bottom-anchored horizontal tray or hidden behind a long-press.

## Elevation & Depth
In this dark-mode environment, we avoid traditional shadows which can appear muddy. Instead, we use **Tonal Layering and Border Glows**:

1.  **Level 0 (Base):** #0F1113 - The main background.
2.  **Level 1 (Cards/Feeds):** #1A1C1E - Used for camera feed containers.
3.  **Level 2 (Modals/Overlays):** #24272A - Used for settings menus and Boy Sisi's dialogue bubbles.
4.  **Active State:** Rather than raising an element, we apply a 1px solid Primary (Cyan) border to the active video feed to indicate focus.
5.  **Status Gloss:** For "Live" feeds, a very subtle backdrop blur (glassmorphism) is applied to the metadata labels over the video to ensure legibility regardless of the video content behind it.

## Shapes
To maintain a professional and "industrial hardware" feel, the system uses a **Soft (0.25rem)** roundedness level. 

Video feeds should have a subtle corner radius to feel like modern hardware monitors. Buttons and input fields follow the same 4px (0.25rem) rule. Boy Sisi’s character art and his dialogue bubbles are the only exceptions, allowed a higher roundedness (Rounded-lg, 1rem) to emphasize his role as the friendly, approachable assistant within a rigid technical framework.

## Components

*   **Monitoring Card:** A 16:9 container. Must include a top-left "LIVE" or "REC" badge and a bottom-left camera name overlay. When tapped, a cyan border activates.
*   **The "Sisi-Button":** A primary action button using the Primary Cyan color. It features a slight outer glow (cyan) to signify that the system is active and responsive.
*   **Status Badges:** Small, pill-shaped indicators. "REC" pulsates slowly in Alert Red. "ONLINE" is static Primary Cyan.
*   **PTZ Controller:** A custom 4-way directional component. It should feel tactile, with haptic feedback on every directional press.
*   **Boy Sisi Alerts:** A component consisting of the Boy Sisi avatar ({{DATA:IMAGE:IMAGE_2}}) paired with a Level 2 surface dialogue bubble. Used for motion alerts like "Boy Sisi noticed movement in the Garage."
*   **Data Inputs:** Dark fields with #24272A background and a 1px border that turns Cyan on focus. Monospaced font is mandatory for IP/Port inputs.