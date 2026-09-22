// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The lint rule that confines assistant-ui, tested for firing.
 *
 * `npm run lint` proves only that no file in the tree breaks the rule, which
 * is also what it would print if the rule matched nothing at all. This runs
 * ESLint over files that do not exist, with the real configuration, and asks
 * which of them it refuses. A change that quietly stopped the seam from
 * matching -- a renamed directory, a name dropped from the list, a pattern
 * syntax that changed under us -- fails here (ADR 0001,
 * docs/specs/open-source.md "Checks").
 */
import { readFileSync } from "node:fs";

import { ESLint } from "eslint";
import { expect, test } from "vitest";

/** The two rules that together make up the seam. */
const SEAM = ["no-restricted-imports", "no-restricted-syntax"];

/**
 * Whether the seam refuses this file, were it to exist.
 *
 * The paths are relative to the working directory, which is the root of this
 * package: the configuration ESLint finds is the one CI runs, not a copy.
 */
async function complains(path: string, code: string): Promise<string[]> {
  const eslint = new ESLint();
  const results = await eslint.lintText(code, { filePath: path });
  const messages = results.flatMap((result) => result.messages);
  expect(
    messages.filter((message) => message.fatal),
    `${path} did not parse`,
  ).toEqual([]);
  return messages.map((message) => message.ruleId ?? "");
}

/** What a refusal has to say for itself, beside being a refusal. */
interface Expected {
  /** Which of the two rules is meant to fire. */
  rule?: string;
  /** A fragment of the message, so a test proves its own pattern fired. */
  says?: string;
}

/**
 * Whether the seam refuses this file, and -- when it is told what to expect
 * -- that it is refused for the reason the test is about.
 *
 * Without the second argument a test proves only that something refused the
 * file, and several of these rules overlap: a spelling refused by the plain
 * -path rule would look like a seam rule doing its job. With it, each test
 * names the pattern it is there to prove.
 */
async function refuses(
  path: string,
  code: string,
  expected: Expected = {},
): Promise<boolean> {
  const eslint = new ESLint();
  const results = await eslint.lintText(code, { filePath: path });
  const messages = results.flatMap((result) => result.messages);
  expect(
    messages.filter((message) => message.fatal),
    `${path} did not parse`,
  ).toEqual([]);
  const seam = messages.filter((message) =>
    SEAM.includes(message.ruleId ?? ""),
  );
  if (expected.rule !== undefined || expected.says !== undefined) {
    const matching = seam.filter(
      (message) =>
        (expected.rule === undefined || message.ruleId === expected.rule) &&
        (expected.says === undefined ||
          message.message.includes(expected.says)),
    );
    expect(
      matching.length,
      `${code}\nwas refused by: ${seam
        .map((message) => `${message.ruleId ?? ""}: ${message.message}`)
        .join("\n")}`,
    ).toBeGreaterThan(0);
  }
  return seam.length > 0;
}

const SHELL = "src/shell/panel.tsx";
const SEAM_FILE = "src/chat/index.ts";
const INSIDE = "src/chat/assistant-ui/runtime.ts";
const BESIDE = "src/chat/history/list.ts";
const DEEPER = "src/chat/history/rows/row.ts";

test("the shell may not import the assistant-ui packages", async () => {
  expect(
    await refuses(SHELL, 'import "@assistant-ui/react";', {
      rule: "no-restricted-imports",
      says: "may be imported only under src/chat/assistant-ui/",
    }),
  ).toBe(true);
  expect(
    await refuses(SHELL, 'import type { T } from "@assistant-ui/react";'),
  ).toBe(true);
});

test("assistant-cloud is named too, subpaths and all", async () => {
  // It arrives as a dependency of @assistant-ui/react and is never
  // configured (ADR 0001). Drop it from the list in eslint.config.js and
  // this is the test that goes red.
  expect(await refuses(SHELL, 'import "assistant-cloud";')).toBe(true);
  expect(await refuses(SHELL, 'import "assistant-cloud/auth";')).toBe(true);
});

test("re-exporting is importing", async () => {
  expect(await refuses(SHELL, 'export * from "@assistant-ui/react";')).toBe(
    true,
  );
  expect(
    await refuses(
      SHELL,
      'export { Thread } from "../chat/assistant-ui/runtime";',
    ),
  ).toBe(true);
});

test("import() is importing", async () => {
  expect(await refuses(SHELL, 'void import("@assistant-ui/react");')).toBe(
    true,
  );
  expect(
    await refuses(SHELL, 'void import("../chat/assistant-ui/runtime");'),
  ).toBe(true);
});

test("a template literal is a specifier too", async () => {
  expect(await refuses(SHELL, "void import(`@assistant-ui/react`);")).toBe(
    true,
  );
  expect(
    await refuses(SHELL, "void import(`../chat/assistant-ui/runtime`);"),
  ).toBe(true);
  expect(await refuses(SHELL, "void import(`../chat`);")).toBe(false);
});

test("case is not a way round it", async () => {
  // no-restricted-imports ignores case; the esquery selectors carry the same
  // `i` flag, so import() cannot be spelt past the rule either.
  expect(await refuses(SHELL, 'import "@ASSISTANT-UI/react";')).toBe(true);
  expect(await refuses(SHELL, 'void import("@ASSISTANT-UI/react");')).toBe(
    true,
  );
  expect(await refuses(SHELL, "void import(`@Assistant-UI/react`);")).toBe(
    true,
  );
});

test("a specifier that cannot be read cannot be cleared", async () => {
  // Nothing here judges what a variable will hold, so none of these is let
  // through on the grounds that it did not match.
  expect(
    await refuses(SHELL, "declare const w: string;\nvoid import(w);"),
  ).toBe(true);
  expect(await refuses(SHELL, 'void import("@assistant" + "-ui/react");')).toBe(
    true,
  );
  expect(
    await refuses(
      SHELL,
      "declare const b: string;\nvoid import(`${b}/react`);",
    ),
  ).toBe(true);
  expect(
    await refuses(SHELL, 'void import.meta.glob("../chat/**/*.ts");'),
  ).toBe(true);
  expect(await refuses(SHELL, 'void import.meta.globEager("./*.ts");')).toBe(
    true,
  );
});

test("require is not part of this package", async () => {
  expect(
    await refuses(SHELL, 'const x = require("@assistant-ui/react");'),
  ).toBe(true);
  expect(await refuses(SHELL, 'const x = require("react");')).toBe(true);
  // Inside the implementation too: the seam is off there, this is not.
  expect(
    await refuses(INSIDE, 'const x = require("@assistant-ui/react");'),
  ).toBe(true);
});

test("the shell may not reach behind the seam, extension or none", async () => {
  expect(await refuses(SHELL, 'import "../chat/assistant-ui/runtime";')).toBe(
    true,
  );
  expect(
    await refuses(SHELL, 'import "../chat/assistant-ui/runtime.js";'),
  ).toBe(true);
  expect(await refuses(SHELL, 'import "../chat/assistant-ui";')).toBe(true);
});

test("a path is not its spelling", async () => {
  // Every one of these reaches src/chat/assistant-ui/. The rule reads a path
  // segment, so none of them is a way round it -- and the plain-specifier
  // rule refuses the odd spellings besides.
  // The plainly-written ones must be refused *by the seam rule*; the rest
  // are refused for being a second spelling of a path, which is a rule of its
  // own and is proved below.
  const behind = {
    rule: "no-restricted-imports",
    says: "behind the seam",
  };
  for (const specifier of [
    "../chat/assistant-ui/runtime",
    "/src/chat/assistant-ui/runtime",
    "../chat/assistant-ui/runtime.js",
    "../chat/assistant-ui/runtime.mjs",
    "../chat/ASSISTANT-UI/runtime",
  ]) {
    expect(
      await refuses(SHELL, `import "${specifier}";`, behind),
      specifier,
    ).toBe(true);
  }
  for (const specifier of [
    "../chat/history/../assistant-ui/runtime",
    "..//assistant-ui/runtime",
    "./../chat/assistant-ui/runtime",
    "../chat/./assistant-ui/runtime",
    "../chat/assistant-ui/",
  ]) {
    expect(await refuses(SHELL, `import "${specifier}";`), specifier).toBe(
      true,
    );
  }
});

test("a specifier is written plainly, or not at all", async () => {
  // These reach nothing behind the seam; they are refused for being a second
  // spelling of a path, which is what makes the rules above readable.
  const plainly = {
    rule: "no-restricted-imports",
    says: "write the path plainly",
  };
  for (const specifier of [
    ".//index",
    "./a/./b",
    "./a/../b",
    "./a/",
    "react/",
    "../chat//index",
  ]) {
    expect(
      await refuses(SHELL, `import "${specifier}";`, plainly),
      specifier,
    ).toBe(true);
  }
  expect(await refuses(SHELL, 'import "../chat/index";')).toBe(false);
  expect(await refuses(SHELL, 'import "../../api/client";')).toBe(false);
});

test("a package is imported by its name", async () => {
  const byPath = {
    rule: "no-restricted-imports",
    says: "import a package by its name",
  };
  expect(
    await refuses(SHELL, 'import "../../node_modules/react";', byPath),
  ).toBe(true);
  expect(
    await refuses(SHELL, 'import "/node_modules/react/index.js";', byPath),
  ).toBe(true);
  expect(
    await refuses(INSIDE, 'import "../../../node_modules/react";', byPath),
  ).toBe(true);
  expect(await refuses(SHELL, 'import "react";')).toBe(false);
});

test("a file beside the implementation may not reach sideways into it", async () => {
  // src/chat/ will hold more than the seam and the implementation; one level
  // up and two, the relative path is still the implementation.
  expect(await refuses(BESIDE, 'import "../assistant-ui/runtime";')).toBe(true);
  expect(await refuses(DEEPER, 'import "../../assistant-ui/runtime";')).toBe(
    true,
  );
  expect(await refuses(BESIDE, "void import(`../assistant-ui/runtime`);")).toBe(
    true,
  );
  expect(await refuses(BESIDE, 'import "../index";')).toBe(false);
});

test("a module reference in a URL is a module reference", async () => {
  // new Worker(new URL(...)) is how a bundler is told to build a second
  // bundle out of a file no import rule ever sees. It is read like import():
  // a string, a template, and anything that cannot be read at all.
  const url = (specifier: string) =>
    `void new Worker(new URL(${specifier}, import.meta.url));`;
  expect(await refuses(SHELL, url('"../chat/assistant-ui/w.ts"'))).toBe(true);
  expect(await refuses(SHELL, url("`../chat/assistant-ui/w.ts`"))).toBe(true);
  expect(
    await refuses(SHELL, url('"../chat/history/../assistant-ui/w.ts"')),
  ).toBe(true);
  expect(await refuses(SHELL, "declare const w: string;\n" + url("w"))).toBe(
    true,
  );
  expect(
    await refuses(SHELL, "declare const b: string;\n" + url("`${b}/w.ts`")),
  ).toBe(true);
  expect(await refuses(SHELL, url('"./w.ts"'))).toBe(false);
  // An ordinary URL is left alone: it names no module.
  expect(
    await refuses(SHELL, "declare const h: string;\nvoid new URL(h);"),
  ).toBe(false);
  // And inside the implementation, a worker may be built any way at all.
  expect(await refuses(INSIDE, "declare const w: string;\n" + url("w"))).toBe(
    false,
  );
});

test("an ordinary URL is not a module reference", async () => {
  // Only `new URL(x, import.meta.url)` names a module. These three are
  // browser code that happens to share a constructor, and steps 18 to 21 are
  // full of them; a rule that refused them would be a rule people turn off.
  for (const code of [
    'void new URL("/api/runs", location.origin);',
    'void new URL("https://example.test/x");',
    "declare const base: string;\nvoid new URL(`${base}/runs`);",
    "declare const href: string;\nvoid new URL(href);",
    'void new URL("../chat/assistant-ui/w.ts", location.origin);',
  ]) {
    expect(await complains(SHELL, code), code).toEqual([]);
    expect(await complains("src/test/harness.ts", code), code).toEqual([]);
  }
});

test("a specifier uses forward slashes", async () => {
  const slashes = { says: "forward slashes" };
  // String.raw so that what ESLint parses is plain to read: the specifier in
  // each of these holds one backslash between each segment.
  expect(
    await refuses(SHELL, String.raw`import "..\\chat\\index";`, slashes),
  ).toBe(true);
  expect(
    await refuses(
      SHELL,
      String.raw`void import("..\\chat\\assistant-ui\\x");`,
      slashes,
    ),
  ).toBe(true);
});

test("import.meta.resolve is refused with import.meta.glob", async () => {
  expect(
    await refuses(SHELL, 'void import.meta.resolve("../chat/index");'),
  ).toBe(true);
});

test("Node's globals are not in a browser", async () => {
  expect(await complains(SHELL, 'void Buffer.from("x");')).toContain(
    "no-restricted-globals",
  );
  expect(await complains(SHELL, "void process.env;")).toContain(
    "no-restricted-globals",
  );
  expect(await complains(SHELL, "void __dirname;")).toContain(
    "no-restricted-globals",
  );
  // The checks that drive tools do run in Node, and say so by living here.
  expect(
    await complains("src/test/harness.ts", "void process.env;"),
  ).not.toContain("no-restricted-globals");
});

test("the seam itself is what the shell imports", async () => {
  expect(await refuses(SHELL, 'import "../chat";')).toBe(false);
  expect(await refuses(SHELL, 'import { Chat } from "../chat/index";')).toBe(
    false,
  );
});

test("the seam's interface may reach its own implementation", async () => {
  expect(await refuses(SEAM_FILE, 'import "./assistant-ui/runtime";')).toBe(
    false,
  );
  expect(
    await refuses(SEAM_FILE, 'void import("./assistant-ui/runtime");'),
  ).toBe(false);
  // By that one name, and by no other path that arrives at the same place.
  expect(
    await refuses(SEAM_FILE, 'import "../chat/assistant-ui/runtime";'),
  ).toBe(true);
  expect(
    await refuses(SEAM_FILE, 'import "./history/../assistant-ui/runtime";'),
  ).toBe(true);
});

test("the seam's interface may not name the packages", async () => {
  // Its types mention nothing from assistant-ui: that is what makes the
  // implementation behind it replaceable (ADR 0001, "The discard test").
  expect(await refuses(SEAM_FILE, 'import "@assistant-ui/react";')).toBe(true);
  expect(await refuses(SEAM_FILE, 'void import("@assistant-ui/react");')).toBe(
    true,
  );
});

test("the implementation may import assistant-ui, which is the point", async () => {
  expect(
    await refuses(
      INSIDE,
      'import "@assistant-ui/react";\nimport "./vendor/thread";\nvoid import("assistant-cloud");',
    ),
  ).toBe(false);
  // And it is the one place a specifier may be worked out at run time.
  expect(
    await refuses(INSIDE, "declare const w: string;\nvoid import(w);"),
  ).toBe(false);
});

test("nothing renames a path behind the seam's back", async () => {
  // An alias is a second name for a directory, and a rule that reads
  // specifiers reads the name it was given. `package.json` may declare
  // `imports`, and a tsconfig may declare `paths`; neither does, and a
  // reviewer seeing one here should ask what it points at.
  const read = (path: string) =>
    JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;

  expect(read("package.json").imports).toBeUndefined();

  // And the build resolves no alias of its own: `resolve.alias` would rename
  // a directory for the bundler and for nobody else.
  const config = readFileSync("vite.config.ts", "utf8");
  expect(config).not.toMatch(/\balias\b/);
  expect(config).not.toMatch(/\bdedupe\b/);

  for (const name of [
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.tools.json",
  ]) {
    const options = (read(name).compilerOptions ?? {}) as Record<
      string,
      unknown
    >;
    const paths = (options.paths ?? {}) as Record<string, string[]>;
    for (const [alias, targets] of Object.entries(paths)) {
      for (const target of targets) {
        expect(target, `${name} maps ${alias}`).not.toMatch(
          /chat\/assistant-ui/,
        );
      }
    }
  }
});
