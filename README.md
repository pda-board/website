# TU/e Postdoc Association — website

Example website for the TU/e Postdoc Association (PDA). A single self-contained
`index.html` (no build step, no framework), ready to host on GitHub Pages.

## What is in it

- **Hero** with the PDA mission and a "next event" card
- **About**: the three pillars (Connect / Grow / Be heard) and the mission quote from tue.nl
- **Events**: upcoming / past tabs
- **Best Paper Award** feature band (facts from the 2026 edition on tue.nl)
- **Board**: the eight current board members, with photos
- **Join**: perks, and a button to the membership form on tue.nl
- **Resources**: onboarding, career & funding, wellbeing
- **Footer / contact**: email, LinkedIn group, Instagram, PostdocNL

The logo (`img/logo*.png`, plus `favicon.png` and the link-preview image `og-card.png`) is the PDA logo from tue.nl. Calendar files for events live in `cal/`.

Palette and type follow the TU/e house style (red `#C72125`, navy `#0E2470`,
Lato body). Urbanist stands in for Gilroy (TU/e's heading font, which is not
freely licensed). Dark mode follows the visitor's system setting.

## Board photos

Photos live in `img/board/` as 480×480 JPEGs, named after the person
(`firstname-lastname.jpg`). Most come from the TU/e research portal; Femke
Verheggen's is from her LinkedIn profile.

## Featuring the next event

The navy section `#next-event` (right below the hero) is the spotlight for the
next event: flyer on the right, details on the left. To feature a new event,
update that section, the "Next up" card in the hero, and the event's row under
Events › Upcoming. When registration opens, replace the "Registration opens
soon" note with `<a class="btn btn-onnavy" href="FORM-URL">Register</a>`.
Flyer QR codes point to `.../website/#next-event`, so printed flyers keep
working when the form link changes.

## Flyers

Each flyer is an HTML page in `flyers/` (e.g. `flyers/glow-walk-2026.html`),
rendered with headless Chrome:

```sh
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# 300 dpi A4 image (2481 x 3509); turn it into the print PDF with any image-to-PDF tool
"$CHROME" --headless=new --hide-scrollbars --allow-file-access-from-files \
  --force-device-scale-factor=3.125 --virtual-time-budget=8000 --window-size=794,1123 \
  --screenshot=flyer.png flyers/glow-walk-2026.html
```

Print the PDF built from that image rather than Chrome's own "print to PDF":
the neon glows do not survive as vectors. Web copies live in `img/flyers/`.

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
