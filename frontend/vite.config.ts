// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
//
// The gates on what may end up in the bundle. The rules they enforce are in
// ../docs/contributing/js-dependencies.md; the policy behind them is
// ../DEPENDENCIES.md.
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { gzipSync } from "node:zlib";

import react from "@vitejs/plugin-react";
import license from "rollup-plugin-license";
import type { Dependency } from "rollup-plugin-license";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

// The licence policy, read from DEPENDENCIES.md by the gate that also applies
// it to the installed tree. Importing it is what keeps the bundle's allowed
// list and the tree's from being two lists (scripts/check-licences.mjs).
import { isAllowed } from "./scripts/check-licences.mjs";

/**
 * The stylesheet languages, and the ones that are CSS Modules.
 *
 * Vite 8.3.0's own `CSS_LANGS_RE` and `cssModuleRE`, copied, so that what is
 * refused below is exactly what Vite would have compiled.
 */
const CSS_LANGS = /\.(css|less|sass|scss|styl|stylus|pcss|postcss|sss)(?:$|\?)/;
const CSS_MODULE =
  /\.module\.(css|less|sass|scss|styl|stylus|pcss|postcss|sss)(?:$|\?)/;

/**
 * Everything shipped, gzipped, must fit in this.
 *
 * Provisional. docs/specs/frontend.md leaves the real number open until a
 * bundle with the chat in it exists: neorc's 500 KB does not fit a chat UI
 * with Markdown and syntax highlighting. Until then the budget is set
 * generously, so that it catches a dependency that is an order of magnitude
 * too big and nothing else. It is tightened, once, when step 21 lands.
 */
const SIZE_BUDGET_BYTES = 800 * 1024;

const here = import.meta.dirname;

/**
 * What ends up in the bundle, one line per package, committed and compared
 * with the build: a new line here is what a reviewer looks at. The build
 * writes it; it is never edited by hand.
 *
 * **What it sees, and what it does not.** rollup-plugin-license reads
 * rollup's module graph, so it lists every package a *module* was imported
 * from. A package reached only through a stylesheet -- `@import "pkg"`,
 * `url(pkg/x.png)`, or a package stylesheet's own imports -- is in the bundle
 * and is **not** in this list. `scripts/check-licences.mjs` still holds it to
 * the allowed list, because it holds every package the lockfile pins, so
 * nothing outside the policy can be installed at all; what is missing is the
 * record, and the one case the tree gate cannot catch is a package scoped
 * development-only that reaches the bundle through CSS.
 *
 * Reviewing a change that adds a CSS `@import` or `url()` of a package means
 * checking that target by hand. ../DEPENDENCIES.md says so, and a scanner
 * that agrees with Vite's own resolver is future work.
 */
const BUNDLED_PACKAGES = resolve(here, "bundled-packages.txt");

/**
 * Whether the build compares the committed list instead of rewriting it.
 * CI sets CI; scripts/check-frontend.sh sets CHECK_BUNDLED. A plain
 * `npm run build` rewrites the file, which is how a new bundled package
 * gets into a diff.
 */
const CHECK_BUNDLED =
  process.env.CHECK_BUNDLED === "1" || process.env.CI === "true";

/**
 * What the browser would download, gzipped.
 *
 * `THIRD_PARTY_LICENSES.txt` is not part of it: it is written into `dist/`
 * for the wheel to carry (docs/oss-checklist.md), no page ever fetches it,
 * and counting it would mean the budget tightened every time a dependency
 * was added -- twice over.
 */
function gzippedSize(dir: string): number {
  let total = 0;
  for (const name of readdirSync(dir)) {
    if (name === "THIRD_PARTY_LICENSES.txt") continue;
    const path = join(dir, name);
    total += statSync(path).isDirectory()
      ? gzippedSize(path)
      : gzipSync(readFileSync(path)).length;
  }
  return total;
}

/**
 * What a stylesheet may be, which is very little.
 *
 * Three refusals, and no resolver: each one is a rule about a file's name,
 * which is the only thing about a stylesheet this build can judge without
 * following a specifier the way Vite would. That is deliberate --
 * ../DEPENDENCIES.md says what a stylesheet can still smuggle past the
 * bundle's record, and what a reviewer therefore has to read by hand.
 *
 * **No CSS Modules.** `composes: x from "pkg/y.css"` and `@value x from
 * "..."` are module references that postcss-modules resolves on its own, so
 * rollup never sees a module for them at all. Vite has no switch to turn
 * them off, so the build refuses the file.
 *
 * **Plain CSS only.** `.scss`, `.less`, `.pcss` and the rest are languages
 * this project does not write, and a preprocessor is one more thing between
 * what is written and what ships.
 *
 * **No `<style>` in `index.html`.** It would need `unsafe-inline` in the
 * Content-Security-Policy to run at all (docs/specs/frontend.md).
 */
export function refuseStylesheets(): Plugin {
  return {
    name: "robinauts-stylesheet-rules",
    apply: "build",
    transform(_code, id) {
      // `?inline`, `?raw`, `?used` and the rest are Vite's; the file is what
      // is in front of the first question mark.
      const path = (id.split("?")[0] ?? "").replace(/^\0/, "");
      if (CSS_MODULE.test(id)) {
        throw new Error(
          `${path} is a CSS Module. Their cross-file references ` +
            "(`composes ... from`, `@value ... from`) are resolved by " +
            "postcss-modules, so rollup never sees a module for them and the " +
            "bundle's record cannot name what they reach. This build refuses " +
            "CSS Modules wherever they come from, a dependency's included: " +
            "pick a dependency that ships plain CSS.",
        );
      }
      // Vite hands a `<style>` block over as `index.html?html-proxy&inline-css
      // &index=0.css`, whose *path* is the page. It is refused for being
      // inline, not for being HTML, so it is named before the rule below.
      if (/[?&]html-proxy\b/.test(id) && /[?&]inline-css\b/.test(id)) {
        throw new Error(inlineStyleRefusal(path));
      }
      if (!CSS_LANGS.test(id)) return null;
      if (!path.endsWith(".css")) {
        throw new Error(
          `${path} is a stylesheet in a language this project does not use. ` +
            "It writes plain CSS, and Tailwind on top of it. Write .css.",
        );
      }
      return null;
    },
  };
}

/**
 * `index.html` carries no stylesheet, and may not.
 *
 * A `<style>` block would need `unsafe-inline` in the Content-Security-Policy
 * to run at all (docs/specs/frontend.md), and reading one properly would mean
 * an HTML parser this project has no other use for. The project's CSS lives
 * in `src/`, so the answer is that there is none to read.
 */
function inlineStyleRefusal(page: string): string {
  return (
    `${page} has a <style> block. The Content-Security-Policy this is served ` +
    "under allows no inline stylesheet, and the licence gate reads files, not " +
    "markup. Put the CSS in src/ and import it."
  );
}

export function refuseInlineStyles(page: string): void {
  if (!existsSync(page)) return;
  // HTML comments first: a `<style` inside one is not a stylesheet.
  const html = readFileSync(page, "utf8").replace(/<!--[\s\S]*?-->/g, "");
  if (/<style\b/i.test(html)) throw new Error(inlineStyleRefusal(page));
}

export function sizeBudget(
  built = resolve(here, "dist"),
  budget = SIZE_BUDGET_BYTES,
): Plugin {
  return {
    name: "robinauts-size-budget",
    apply: "build",
    closeBundle() {
      // A build that failed wrote nothing, and a budget complaining about a
      // directory that is not there would bury the error that matters.
      if (!existsSync(built)) return;
      const size = gzippedSize(built);
      if (size > budget) {
        throw new Error(
          `the built assets are ${size} bytes gzipped, over the budget of ` +
            `${budget}: see docs/contributing/js-dependencies.md`,
        );
      }
    },
  };
}

/**
 * The list as it should be, and either written or compared.
 *
 * Split from the gathering above so that a test can drive both sides of it
 * without a build: what the file says is the whole of the record, and the
 * compare is the whole of the check.
 */
export function bundledPackagesFrom(
  lines: Iterable<string>,
  { check = CHECK_BUNDLED, file = BUNDLED_PACKAGES } = {},
): string {
  // No trailing newline: rollup-plugin-license trims what a template returns
  // before writing it, and what is compared below has to be, byte for byte,
  // what the build would have put on disk.
  const written = [
    "# Packages in the built bundle, written by the build.",
    "# A change here is reviewed: see docs/contributing/js-dependencies.md.",
    ...[...new Set(lines)].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)),
  ].join("\n");
  if (!check) return written;
  let committed: string;
  try {
    committed = readFileSync(file, "utf8");
  } catch {
    committed = "";
  }
  if (committed !== written) {
    throw new Error(
      "bundled-packages.txt differs from what the build wrote. Run " +
        "`npm run build` without CHECK_BUNDLED, commit the file, and have " +
        "the new package reviewed: docs/contributing/js-dependencies.md.",
    );
  }
  // Returning what is already there makes the write that follows a no-op.
  return written;
}

function bundledPackages(dependencies: Dependency[]): string {
  refuseInlineStyles(resolve(here, "index.html"));
  return bundledPackagesFrom(
    dependencies.map((d) => `${d.name} ${d.version} ${d.license}`),
  );
}

// The dev server against a local `robinauts start`. One target, one set of
// settings: a run's events arrive as server-sent events, and an intermediary
// that buffers or times out turns a live answer into a batch of text at the
// end of it.
const BACKEND = "http://127.0.0.1:8000";
const proxy = {
  target: BACKEND,
  changeOrigin: false,
  // Nothing may sit on the stream: no compression to fill a buffer with, and
  // no deadline for a run that takes minutes.
  headers: { "accept-encoding": "identity" },
  timeout: 0,
  proxyTimeout: 0,
};

export default defineConfig({
  // Relative asset paths, so the built files work under any prefix, /ui/
  // included, without being rebuilt for it.
  base: "./",
  plugins: [react(), refuseStylesheets(), sizeBudget()],
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
  server: {
    proxy: {
      "/api": proxy,
      "/auth": proxy,
      "/health": proxy,
      "/openapi.json": proxy,
    },
  },
  // A worker is a second rollup build with a bundle of its own, so the licence
  // gate has to be registered for it separately or it ships ungated. It emits
  // no record: see the note on BUNDLED_PACKAGES.
  worker: {
    // The stylesheet rules too: a worker is a separate rollup build, and
    // would otherwise be the one place a CSS Module could still be written.
    plugins: () => [
      refuseStylesheets(),
      license({
        thirdParty: {
          allow: {
            test: (dependency) => isAllowed(dependency.license ?? ""),
            failOnUnlicensed: true,
            failOnViolation: true,
          },
          // Gated, not recorded: an output here would fight the one below
          // over the same files.
          output: [],
        },
      }),
    ],
  },
  build: {
    rollupOptions: {
      plugins: [
        license({
          thirdParty: {
            allow: {
              // The allowed list, and SPDX's AND/OR with it, from the gate.
              // A bundled package is never excepted: this is the list or
              // nothing (../DEPENDENCIES.md).
              test: (dependency) => isAllowed(dependency.license ?? ""),
              failOnUnlicensed: true,
              failOnViolation: true,
            },
            output: [
              // The wheel carries this file and lists it in license-files
              // (docs/oss-checklist.md); step 22 puts it there.
              { file: resolve(here, "dist/THIRD_PARTY_LICENSES.txt") },
              { file: BUNDLED_PACKAGES, template: bundledPackages },
            ],
          },
        }),
      ],
    },
  },
});
