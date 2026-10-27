# TU/e Postdoc Association — website

Example website for the TU/e Postdoc Association (PDA). A single self-contained
`index.html` (no build step, no framework), ready to host on GitHub Pages.

## What is in it

- **Hero** with the PDA mission and a "next event" card
- **About**: the three pillars (Connect / Grow / Be heard) and the mission quote from tue.nl
- **Events**: upcoming / past tabs
- **Best Paper Award** feature band (facts from the 2026 edition on tue.nl)
- **Board**: the eight current board members
- **Join**: membership form (same fields as the tue.nl form — no backend yet)
- **Resources**: onboarding, career & funding, wellbeing
- **Footer / contact**: email, LinkedIn group, Instagram, X, PostdocNL

Palette and type follow the TU/e house style (red `#C72125`, navy `#0E2470`,
Lato body). Urbanist stands in for Gilroy (TU/e's heading font, which is not
freely licensed). Dark mode follows the visitor's system setting.

## Placeholders to replace before going live

| Where | What |
|---|---|
| Board | Add photos (`<div class="avatar"><img src="..."></div>`) and Femke Verheggen's department |
| Resources | Links marked `https://www.tue.nl/en/` need the real TU/e page URLs |
| Join form | Either point the button to the existing tue.nl application form, or connect the form to a backend (Formspree, Microsoft Forms embed, Google Forms) |

## Deploying on GitHub Pages

1. Create a GitHub organisation for the PDA (e.g. `tue-pda`) or use a personal account.
2. Create a repository named `<org>.github.io` (site served at `https://<org>.github.io/`)
   or any name (served at `https://<org>.github.io/<repo>/`).
3. Push this folder:
   ```sh
   cd tue-pda-website
   git init
   git add .
   git commit -m "PDA website"
   git branch -M main
   git remote add origin git@github.com:<org>/<repo>.git
   git push -u origin main
   ```
4. In the repository: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, branch `main`, folder `/ (root)`.
5. The site is live within a minute. A custom domain (e.g. `pda.tue.nl`, if TU/e ICT agrees, or `tuepda.nl`) can be added under the same Pages settings with a CNAME record.

## Editing

Everything lives in `index.html`. Content is plain HTML; styling is in the
`<style>` block at the top, with colours defined once as CSS variables in `:root`.
To add an event, copy one `<li class="event">…</li>` block in the Upcoming list.
