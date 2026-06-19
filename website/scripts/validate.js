"use strict";

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pages = ["index.html", "docs.html", "blog.html", "pricing.html"];
const requiredAssets = ["styles.css", "nav.js", "favicon.svg", "robots.txt", "sitemap.xml", "assets/hero-wave.png"];
const forbiddenPatterns = [
  /Sign\s*In/i,
  /console\.log\s*\(/,
  /href\s*=\s*["']#["']/,
];

let failed = false;

function fail(message) {
  console.error(`FAIL: ${message}`);
  failed = true;
}

function pass(message) {
  console.log(`OK: ${message}`);
}

for (const asset of requiredAssets) {
  const assetPath = path.join(root, asset);
  if (!fs.existsSync(assetPath)) {
    fail(`Missing asset: ${asset}`);
  } else {
    pass(`Asset exists: ${asset}`);
  }
}

for (const page of pages) {
  const pagePath = path.join(root, page);
  if (!fs.existsSync(pagePath)) {
    fail(`Missing page: ${page}`);
    continue;
  }

  const html = fs.readFileSync(pagePath, "utf8");
  pass(`Page readable: ${page}`);

  for (const pattern of forbiddenPatterns) {
    if (pattern.test(html)) {
      fail(`${page} contains forbidden pattern: ${pattern}`);
    }
  }

  if (!html.includes('rel="canonical"')) {
    fail(`${page} missing canonical URL`);
  }

  if (!html.includes('property="og:title"')) {
    fail(`${page} missing Open Graph tags`);
  }

  if (!html.includes('class="skip-link"')) {
    fail(`${page} missing skip link`);
  }

  const hrefMatches = [...html.matchAll(/(?:href|src)\s*=\s*["']([^"']+)["']/g)];
  for (const [, target] of hrefMatches) {
    if (/^(https?:|mailto:|#)/.test(target)) {
      continue;
    }
    const normalized = target.split("#")[0].split("?")[0];
    if (!normalized) {
      continue;
    }
    const resolved = path.join(root, normalized);
    if (!fs.existsSync(resolved)) {
      fail(`${page} links to missing file: ${target}`);
    }
  }
}

if (failed) {
  process.exit(1);
}

console.log("\nAll website validation checks passed.");
