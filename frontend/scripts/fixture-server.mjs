// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * A built `dist/` served with fixture answers, for looking at the shell.
 *
 * A development tool. It is not in the bundle, not in the wheel and not part
 * of any check: it exists so that a person -- or a browser driven by one --
 * can see the interface in a state the backend would take a database and a
 * sign-in to produce. It answers exactly the two routes this step's code
 * calls, and refuses everything else.
 *
 *     npm run build
 *     node scripts/fixture-server.mjs signed-in 5173
 *
 * The scene is the first argument: `signed-in`, `one-agent`, `no-agents`,
 * `local` or `signed-out`. It binds loopback only.
 *
 * A failed sign-in is the `signed-out` scene at the hash the backend
 * redirects to: `http://127.0.0.1:5173/#/sign-in?error=not_allowed`.
 */
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";
import process from "node:process";

const DIST = resolve(import.meta.dirname, "..", "dist");

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  provider: "google",
  name: "Ada Lovelace",
  email: "ada@example.test",
};

const PROVIDERS = [
  { id: "google", title: "Google" },
  { id: "okta", title: "Okta" },
];

const AGENTS = [
  { id: "helper", title: "Helper", engine: "langgraph" },
  { id: "researcher", title: "Researcher", engine: "pydantic-ai" },
];

/** @type {Record<string, {session: unknown, agents: unknown[]}>} */
const SCENES = {
  "signed-in": {
    session: {
      sign_in: true,
      local_development: false,
      providers: PROVIDERS,
      user: USER,
    },
    agents: AGENTS,
  },
  "one-agent": {
    session: {
      sign_in: true,
      local_development: false,
      providers: PROVIDERS,
      user: USER,
    },
    agents: AGENTS.slice(0, 1),
  },
  "no-agents": {
    session: {
      sign_in: true,
      local_development: false,
      providers: PROVIDERS,
      user: USER,
    },
    agents: [],
  },
  local: {
    session: {
      sign_in: false,
      local_development: true,
      providers: [],
      user: {
        id: "00000000-0000-0000-0000-000000000000",
        provider: "!local",
        name: "Local developer",
        email: null,
      },
    },
    agents: AGENTS,
  },
  "signed-out": {
    session: {
      sign_in: true,
      local_development: false,
      providers: PROVIDERS,
      user: null,
    },
    agents: [],
  },
};

/**
 * What a built file is served as. Nothing else is servable.
 *
 * @type {Record<string, string>}
 */
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".ico": "image/x-icon",
};

const scene = process.argv[2] ?? "signed-in";
const port = Number(process.argv[3] ?? "5173");
const fixture = SCENES[scene];
if (fixture === undefined) {
  console.error(`no such scene: ${scene}. One of ${Object.keys(SCENES)}`);
  process.exit(2);
}

/**
 * @param {import("node:http").ServerResponse} response
 * @param {number} status
 * @param {unknown} body
 */
function json(response, status, body) {
  const text = JSON.stringify(body);
  response.writeHead(status, {
    "content-type": "application/json",
    "cache-control": "no-store",
  });
  response.end(text);
}

const server = createServer((request, response) => {
  const path = (request.url ?? "/").split("?")[0] ?? "/";
  if (path === "/auth/session") {
    json(response, 200, fixture.session);
    return;
  }
  if (path === "/api/agents") {
    json(response, 200, { items: fixture.agents });
    return;
  }
  if (path === "/auth/logout") {
    response.writeHead(204).end();
    return;
  }
  // Anything else is a built file, and `normalize` is what keeps `..` from
  // reaching outside dist/. A tool this small still does not get to serve
  // the whole disk.
  const wanted = normalize(join(DIST, path === "/" ? "/index.html" : path));
  // The separator matters: `dist-secrets/` starts with `dist` and is not
  // inside it.
  if (wanted !== DIST && !wanted.startsWith(DIST + sep)) {
    json(response, 403, { error: "outside", detail: path });
    return;
  }
  const type = TYPES[extname(wanted)];
  readFile(wanted).then(
    (bytes) => {
      response.writeHead(200, {
        "content-type": type ?? "application/octet-stream",
      });
      response.end(bytes);
    },
    () => {
      json(response, 404, { error: "not_found", detail: path });
    },
  );
});

server.listen(port, "127.0.0.1", () => {
  console.log(`${scene} on http://127.0.0.1:${port}/ from ${DIST}`);
});
