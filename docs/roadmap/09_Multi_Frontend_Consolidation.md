# 09: Multi-Frontend Consolidation

## Overview
Unifying the diverse AlaskaIntel applications (Aviation, Radar, Globe, Wall, Ad Engine) under a single data and design architecture.

## Vision
One data core to rule them all. Users should feel like they are moving between different views of the same "Alaska OS".

## Planned Features
- **Shared Data Core**: Every frontend pulls from the `datagit.alaskaintel.com` edge proxy.
- **Unified Design System**: A shared component library (in `packages/ui`) enforcing the AlaskaIntel "Glassmorphism" aesthetic.
- **Cross-App Navigation**: The "Next Layer" switcher to route users based on situational needs (e.g., from Signal Wall to Aviation Map).
- **Global Auth/Identity**: Shared local-first identity across all subdomains.

## Milestones
- [ ] Migrate all frontends to use the `data-proxy` worker.
- [ ] Centralize CSS tokens and common React components.
- [ ] Implement the "OS Switcher" navigation menu.
