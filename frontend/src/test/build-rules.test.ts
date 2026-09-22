// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The rules the build itself carries, tested on their own.
 *
 * They are what is left of a longer attempt: a scanner that read stylesheets
 * and followed what they reached was written and then dropped, because it
 * never agreed with Vite's own resolver (see ../../DEPENDENCIES.md, which
 * states the limit that leaves). What remains needs no resolver -- each rule
 * judges a file's name, or a file the build has already written.
 */
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import {
  bundledPackagesFrom,
  refuseInlineStyles,
  refuseStylesheets,
  sizeBudget,
} from "../../vite.config";

const scratches: string[] = [];
const scratch = () => {
  const where = mkdtempSync(join(tmpdir(), "robinauts-build-"));
  scratches.push(where);
  return where;
};
afterEach(() => {
  for (const where of scratches.splice(0)) {
    rmSync(where, { recursive: true, force: true });
  }
});

describe("what the build refuses outright", () => {
  /** The plugin's transform hook, called as rollup would call it. */
  const transform = (id: string) => {
    const plugin = refuseStylesheets() as {
      transform: (code: string, id: string) => unknown;
    };
    return () => plugin.transform("", id);
  };

  test("a CSS Module, in any language and from anywhere", () => {
    for (const id of [
      "/x/src/a.module.css",
      "/x/src/a.module.scss",
      "/x/node_modules/some-ui/dist/a.module.css?used",
    ]) {
      expect(transform(id), id).toThrow(/a dependency's included/);
    }
  });

  test("a stylesheet in a language this project does not write", () => {
    for (const id of [
      "/x/src/a.scss",
      "/x/src/a.pcss",
      "/x/src/a.sss?inline",
    ]) {
      expect(transform(id), id).toThrow(/language this project does not use/);
    }
  });

  test("a <style> block, which Vite hands over as a page", () => {
    // Its id's path is index.html, so the language rule would name it wrongly
    // if the inline rule did not come first.
    expect(
      transform("/x/index.html?html-proxy&inline-css&index=0.css"),
    ).toThrow(/<style> block/);
  });

  test("and nothing else", () => {
    for (const id of ["/x/src/a.css", "/x/src/main.tsx", "\0virtual:thing"]) {
      expect(transform(id), id).not.toThrow();
    }
  });

  test("a <style> in index.html, read from the file", () => {
    const root = scratch();
    writeFileSync(
      join(root, "clean.html"),
      '<head><!-- <style>@import "pkg";</style> --></head>',
    );
    writeFileSync(
      join(root, "dirty.html"),
      '<head><style type="text/css">.a { color: red }</style></head>',
    );
    expect(() => refuseInlineStyles(join(root, "missing.html"))).not.toThrow();
    expect(() => refuseInlineStyles(join(root, "clean.html"))).not.toThrow();
    expect(() => refuseInlineStyles(join(root, "dirty.html"))).toThrow(
      /<style> block/,
    );
  });
});

describe("the bundle's size and its record", () => {
  test("the budget reads what a browser would download, and no more", () => {
    const dist = scratch();
    writeFileSync(join(dist, "app.js"), "x".repeat(4096));
    // Big enough to break any budget, and not part of one: the wheel carries
    // it and no page fetches it.
    writeFileSync(join(dist, "THIRD_PARTY_LICENSES.txt"), "y".repeat(200000));

    const run = (budget: number) => {
      const plugin = sizeBudget(dist, budget) as { closeBundle: () => void };
      return () => plugin.closeBundle();
    };
    // Between the two: over the budget if the licence file were counted, and
    // under it if only what a browser downloads is. It is the second.
    expect(run(2000)).not.toThrow();
    expect(run(8)).toThrow(/over the budget of 8/);
  });

  test("a build that wrote nothing is not a build over its budget", () => {
    // The real error is the one that stopped the build; a budget complaining
    // about a missing directory would bury it.
    const plugin = sizeBudget(join(scratch(), "never-written"), 1) as {
      closeBundle: () => void;
    };
    expect(() => plugin.closeBundle()).not.toThrow();
  });

  test("the record is written, or compared and refused", () => {
    const file = join(scratch(), "bundled-packages.txt");
    const lines = ["b 2.0.0 ISC", "a 1.0.0 MIT", "a 1.0.0 MIT"];

    const written = bundledPackagesFrom(lines, { check: false, file });
    // Sorted, de-duplicated, and with no trailing newline: what is compared
    // has to be what the build would have put on disk.
    expect(written.split("\n").slice(2)).toEqual([
      "a 1.0.0 MIT",
      "b 2.0.0 ISC",
    ]);
    expect(written.endsWith("\n")).toBe(false);

    expect(() => bundledPackagesFrom(lines, { check: true, file })).toThrow(
      /differs from what the build wrote/,
    );
    writeFileSync(file, written);
    expect(bundledPackagesFrom(lines, { check: true, file })).toBe(written);
    expect(() =>
      bundledPackagesFrom([...lines, "c 3.0.0 MIT"], { check: true, file }),
    ).toThrow(/differs from what the build wrote/);
  });
});

describe("where the plugins are registered", () => {
  test("the page build and the worker build both carry the gates", async () => {
    // A worker is a second rollup build: its modules are gated only if the
    // licence plugin is in its own list, and nothing else would say so.
    const config = (await import("../../vite.config")).default as {
      plugins: { name?: string }[];
      worker: { plugins: () => { name?: string }[] };
      build: { rollupOptions: { plugins: { name?: string }[] } };
    };
    const named = (plugins: { name?: string }[]) =>
      plugins.map((one) => one?.name);

    expect(named(config.plugins.flat())).toContain(
      "robinauts-stylesheet-rules",
    );
    expect(named(config.build.rollupOptions.plugins)).toContain(
      "rollup-plugin-license",
    );
    const worker = named(config.worker.plugins());
    expect(worker).toContain("robinauts-stylesheet-rules");
    expect(worker).toContain("rollup-plugin-license");
  });
});
