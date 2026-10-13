# Walkie-Talkie Website

This directory is the entire public website — plain static HTML/CSS/JS with
self-hosted fonts. It is what Vercel serves (see `vercel.json` at the repo
root: `outputDirectory: "site"`).

## Structure

```
site/
├── index.html            Landing page
├── download.html         Downloads (T&C modal before any download)
├── 403/404/500/503.html  Error pages (Vercel auto-serves 404.html)
├── docs/                 Public documentation pages (HTML)
└── assets/
    ├── css/              style.css + fonts.css
    ├── fonts/            Outfit + IBM Plex Mono (self-hosted)
    └── img/              logos and favicon
```

## Local preview

```bash
cd site
python3 -m http.server 8080
# open http://localhost:8080
```

## Deploy

The Vercel project should import the repository root — `vercel.json` points
the deployment at this directory. Every push to `main` redeploys.

The internal developer docs (architecture, decisions, protocols, testing)
are plain Markdown at the repository root in `docs/` — they are **not** part
of the deployed website.
