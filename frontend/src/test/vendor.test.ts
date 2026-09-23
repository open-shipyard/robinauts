// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The vendored copy, held to what is written down about it.
 *
 * `src/chat/assistant-ui/vendor/` is somebody else's source, copied in under
 * the rules of ADR 0001: a README that says what came from where, upstream's
 * licence beside it, and no reach into this project's own code. None of that
 * is something a compiler notices, and all of it rots quietly -- a file added
 * in a re-sync and left out of the list, a licence replaced by the wrong
 * one, an import of `../../../shell/` that makes the copy part of the
 * application. So it is a test.
 *
 * What the lint rules already prove is not repeated here: `eslint.config.js`
 * refuses an import of this directory from outside the seam, and
 * `seam-rule.test.ts` proves that rule still fires.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { describe, expect, test } from "vitest";

const FRONTEND = resolve(import.meta.dirname, "..", "..");
const VENDOR = join(FRONTEND, "src", "chat", "assistant-ui", "vendor");

/**
 * The files in the directory that are not source at all: the two licence
 * texts and the record. `lib/utils.ts` is ours too, but it is source and it
 * stands in for a registry item, so it is in the table below with the rest
 * and is held to the same rules about what it may import.
 */
const OURS = ["LICENSE", "LICENSE.shadcn-ui", "README.md"];

/** What a vendored file may name, beside a relative path inside `vendor/`. */
const PACKAGES = [
  "@assistant-ui/react",
  "@assistant-ui/react-markdown",
  "class-variance-authority",
  "clsx",
  "lucide-react",
  "radix-ui",
  "react",
  "react-dom",
  "remark-gfm",
  "tailwind-merge",
];

/** Every file under a directory, as paths relative to it, sorted. */
function walk(where: string, base = where): string[] {
  return readdirSync(where)
    .flatMap((name) => {
      const path = join(where, name);
      return statSync(path).isDirectory()
        ? walk(path, base)
        : [relative(base, path).replaceAll("\\", "/")];
    })
    .sort();
}

const copied = walk(VENDOR).filter((path) => !OURS.includes(path));

const readme = readFileSync(join(VENDOR, "README.md"), "utf8");

/** One section of the README, by its heading, up to the next one. */
function section(heading: string): string {
  const opening = `## ${heading}\n`;
  const from = readme.indexOf(opening);
  if (from === -1) throw new Error(`the README has no "${opening.trim()}"`);
  const rest = readme.slice(from + opening.length);
  const to = rest.indexOf("\n## ");
  return to === -1 ? rest : rest.slice(0, to);
}

/**
 * The paths the README's table of copied files names.
 *
 * The first cell of every row of that one table. Read from its section rather
 * than from the whole file, because the vetting table further down has
 * backquoted package names in its first cell and would otherwise be read as
 * a list of files.
 */
const listed = [
  ...section("What was copied").matchAll(/^\|\s*`([^`]+)`\s*\|/gm),
]
  .map((row) => row[1] ?? "")
  .sort();

describe("the list of copied files", () => {
  test("names every file in the directory", () => {
    expect(listed).toEqual(copied);
  });

  test("covers the whole directory, ours apart", () => {
    expect(walk(VENDOR).filter((path) => OURS.includes(path))).toEqual(OURS);
  });
});

describe("upstream's licences", () => {
  const licences = {
    LICENSE: "Copyright (c) 2025 AgentbaseAI Inc.",
    "LICENSE.shadcn-ui": "Copyright (c) 2023 shadcn",
  };
  const text = (file: string) => readFileSync(join(VENDOR, file), "utf8");
  const body = (file: string) => text(file).split("\n").slice(3).join("\n");

  for (const [file, copyright] of Object.entries(licences)) {
    test(`${file} is the MIT text, with the recorded copyright`, () => {
      expect(text(file).split("\n").slice(0, 3)).toEqual([
        "MIT License",
        "",
        copyright,
      ]);
      expect(body(file)).toContain(
        "Permission is hereby granted, free of charge",
      );
      expect(body(file)).toContain("without restriction");
      expect(body(file)).toContain('THE SOFTWARE IS PROVIDED "AS IS"');
    });

    test(`${file} is quoted in the README`, () => {
      expect(readme).toContain(file);
    });
  }

  test("both are the same MIT text under different copyright", () => {
    expect(body("LICENSE")).toEqual(body("LICENSE.shadcn-ui"));
  });
});

/**
 * Every module specifier in a file: `import`, `import type`, `export ... from`
 * and a side-effect `import "..."`.
 *
 * Read from the start of a line, which is where a statement begins in a file
 * Prettier has formatted, and only up to the first `;`. Anchoring it is what
 * keeps `side = "bottom"` in the middle of an `export const` from reading as
 * a module.
 */
function specifiers(source: string): string[] {
  return [
    ...source.matchAll(/^import\s+["']([^"']+)["']/gm),
    ...source.matchAll(/^(?:import|export)\b[^;]*?\bfrom\s+["']([^"']+)["']/gm),
  ].map((match) => match[1] ?? "");
}

/** The package a bare specifier names, scope included. */
function packageOf(specifier: string): string {
  const parts = specifier.split("/");
  return specifier.startsWith("@")
    ? parts.slice(0, 2).join("/")
    : (parts[0] ?? "");
}

describe("what the copied files import", () => {
  const sources = copied.filter((path) => /\.tsx?$/.test(path));

  test("is a file this directory has, or a package on the list", () => {
    const strays: string[] = [];
    for (const path of sources) {
      for (const specifier of specifiers(
        readFileSync(join(VENDOR, path), "utf8"),
      )) {
        if (!specifier.startsWith(".")) {
          if (!PACKAGES.includes(packageOf(specifier))) {
            strays.push(`${path}: ${specifier}`);
          }
          continue;
        }
        // A relative path may not leave the directory, and has to reach a
        // file that is in it: a re-sync that drops one fails here.
        const reached = relative(
          VENDOR,
          resolve(join(VENDOR, path), "..", specifier),
        ).replaceAll("\\", "/");
        const found = ["", ".ts", ".tsx"].some((extension) =>
          copied.includes(`${reached}${extension}`),
        );
        if (reached.startsWith("..") || !found) {
          strays.push(`${path}: ${specifier}`);
        }
      }
    }
    expect(strays).toEqual([]);
  });

  test("reaches nothing of this application's own", () => {
    const ours = readdirSync(join(FRONTEND, "src"), { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && entry.name !== "chat")
      .map((entry) => entry.name);
    // The directories the shell is written in really are there; a test that
    // looked for nothing would pass for the wrong reason.
    expect(ours).toContain("shell");
    for (const path of sources) {
      const source = readFileSync(join(VENDOR, path), "utf8");
      for (const specifier of specifiers(source)) {
        for (const name of ours) {
          expect(specifier.split("/")).not.toContain(name);
        }
      }
    }
  });
});

test("nothing outside the seam names the vendored copy", () => {
  const strays = walk(join(FRONTEND, "src"))
    .filter((path) => /\.tsx?$/.test(path))
    .filter((path) => !path.startsWith("chat/assistant-ui/"))
    .filter((path) => !path.startsWith("test/"))
    .filter((path) =>
      specifiers(readFileSync(join(FRONTEND, "src", path), "utf8")).some(
        (specifier) => specifier.split("/").includes("vendor"),
      ),
    );
  expect(strays).toEqual([]);
});
