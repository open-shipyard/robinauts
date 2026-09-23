// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * A built `dist/` served with fixture answers, for looking at the shell.
 *
 * A development tool. It is not in the bundle, not in the wheel and not part
 * of any check: it exists so that a person -- or a browser driven by one --
 * can see the interface in a state the backend would take a database and a
 * sign-in to produce. It answers exactly the routes the code here calls, and
 * refuses everything else.
 *
 *     npm run build
 *     node scripts/fixture-server.mjs signed-in 5173
 *
 * The scene is the first argument: `signed-in`, `one-agent`, `no-agents`,
 * `local`, `signed-out`, `history` or `conversation`. It binds loopback only.
 *
 * A failed sign-in is the `signed-out` scene at the hash the backend
 * redirects to: `http://127.0.0.1:5173/#/sign-in?error=not_allowed`.
 *
 * **Which conversation is open is the hash**, so `history` and `conversation`
 * differ in what they list rather than in what they serve: `history` has
 * enough conversations to page through, `conversation` the three a
 * conversation can be in --
 * `#/c/c0000000-0000-4000-8000-000000000001` (a branch),
 * `…002` (a run in flight) and `…003` (a run that ended badly).
 *
 * Renaming, deleting and cancelling really change what this serves, so the
 * states after them can be looked at too. Nothing is written to disk: a
 * restart is a fresh set of fixtures.
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

const SIGNED_IN = {
  sign_in: true,
  local_development: false,
  providers: PROVIDERS,
  user: USER,
};

const RUN = "99999999-9999-4999-8999-999999999999";

/**
 * What an answer records (`ProvenanceView`).
 *
 * @typedef {{agent: string, engine: string, model: string, run_id: string}} Provenance
 */

/**
 * One message of a conversation's tree (`MessageView`).
 *
 * @typedef {{
 *   id: string,
 *   parent_id: string | null,
 *   role: string,
 *   channel: string,
 *   created_at: string,
 *   parts: {kind: string, text: string}[],
 *   provenance: Provenance | null,
 * }} Message
 */

/**
 * A conversation opened, without the summary (`OpenedConversationResponse`).
 *
 * @typedef {{
 *   messages: Message[],
 *   leaf_id: string | null,
 *   run_id: string | null,
 *   resume: {after: number, follows: string | null} | null,
 *   ended_badly: {run_id: string, state: string, ended_at: string} | null,
 * }} Tree
 */

/**
 * A conversation's id, in the shape the router insists on.
 *
 * @param {number} n
 */
const conversationId = (n) =>
  `c0000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

/**
 * One conversation as the panel lists it.
 *
 * `updated_at` counts backwards from the first, because a listing is most
 * recently updated first and a panel where every row says the same time
 * would hide that.
 *
 * @param {number} n
 * @param {string} title
 */
const summary = (n, title) => ({
  id: conversationId(n),
  title,
  agent: "helper",
  created_at: "2026-09-18T09:00:00Z",
  updated_at: new Date(Date.parse("2026-09-21T16:00:00Z") - n * 3600_000)
    .toISOString()
    .replace(".000", ""),
  active_leaf_id: null,
});

/**
 * @param {string} id
 * @param {string | null} parent
 * @param {string} role
 * @param {string} text
 * @param {Provenance | null} provenance
 * @returns {Message}
 */
const message = (id, parent, role, text, provenance = null) => ({
  id,
  parent_id: parent,
  role,
  channel: "web",
  created_at: "2026-09-21T15:40:00Z",
  parts: [{ kind: "text", text }],
  provenance,
});

const MADE_BY = {
  agent: "helper",
  engine: "langgraph",
  model: "claude-sonnet",
  run_id: RUN,
};

/** The titles, in the order the listing hands them out. */
const TITLES = [
  "Why do robins sing before dawn?",
  "Reading a wheel's metadata",
  "An answer that stopped halfway",
  "Migrating a schema without migrations",
  "Server-sent events behind a proxy",
  "Choosing between two engines",
  "What a licence gate can and cannot see",
  "Notes on the panel's focus trap",
];

/**
 * A conversation's messages and the state of its last run, by id.
 *
 * The first three are the states a conversation can be in; the rest are one
 * exchange each, so that the panel has something to page through.
 *
 * @param {number} n
 * @returns {Tree}
 */
function tree(n) {
  const first = message(
    `${conversationId(n)}-1`,
    null,
    "user",
    TITLES[n - 1] ?? "A question",
  );
  const answer = message(
    `${conversationId(n)}-2`,
    first.id,
    "assistant",
    "Short answer: yes. The longer one is that it depends on what the\nquestion is really about, and this is a fixture rather than a model.",
    MADE_BY,
  );
  if (n === 1) {
    const follow = message(
      `${conversationId(n)}-3`,
      answer.id,
      "user",
      "And what about the ones that sing at night?",
    );
    const last = message(
      `${conversationId(n)}-4`,
      follow.id,
      "assistant",
      "Street lighting, mostly. A robin will sing under a lamp post at two\nin the morning and be perfectly sincere about it.",
      { ...MADE_BY, engine: "pydantic-ai" },
    );
    // A regeneration of the first answer, so the tree really has a branch
    // beside the one that is shown.
    const beside = message(
      `${conversationId(n)}-2b`,
      first.id,
      "assistant",
      "Another answer to the same question, on the branch beside this one.",
      MADE_BY,
    );
    return {
      messages: [first, answer, beside, follow, last],
      leaf_id: last.id,
      run_id: null,
      resume: null,
      ended_badly: null,
    };
  }
  if (n === 2) {
    return {
      messages: [first],
      leaf_id: first.id,
      run_id: RUN,
      resume: { after: 4, follows: first.id },
      ended_badly: null,
    };
  }
  if (n === 3) {
    return {
      messages: [first],
      leaf_id: first.id,
      run_id: null,
      resume: null,
      ended_badly: {
        run_id: RUN,
        state: "interrupted",
        ended_at: "2026-09-21T15:41:00Z",
      },
    };
  }
  return {
    messages: [first, answer],
    leaf_id: answer.id,
    run_id: null,
    resume: null,
    ended_badly: null,
  };
}

/**
 * @type {Record<string, {
 *   session: unknown,
 *   agents: unknown[],
 *   conversations?: number,
 * }>}
 */
const SCENES = {
  "signed-in": {
    session: SIGNED_IN,
    agents: AGENTS,
  },
  history: {
    session: SIGNED_IN,
    agents: AGENTS,
    conversations: TITLES.length,
  },
  conversation: {
    session: SIGNED_IN,
    agents: AGENTS,
    conversations: 3,
  },
  "one-agent": {
    session: SIGNED_IN,
    agents: AGENTS.slice(0, 1),
  },
  "no-agents": {
    session: SIGNED_IN,
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
 * The conversations this run is serving, and what they hold.
 *
 * Mutable: a rename, a delete and a cancel really change them, so what the
 * interface looks like after one can be looked at. It lives for as long as
 * the process does and is written nowhere.
 */
const listed = Array.from({ length: fixture.conversations ?? 0 }, (_, index) =>
  summary(index + 1, TITLES[index] ?? `Conversation ${index + 1}`),
);
/** @type {Map<string, Tree>} */
const trees = new Map(listed.map((one, index) => [one.id, tree(index + 1)]));

/**
 * How many a page holds, whatever was asked for.
 *
 * The interface asks for thirty. Answering with five is what makes "Load
 * more" something to look at without inventing thirty-one conversations.
 */
const PAGE = 5;

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

/**
 * The API's one shape for a refusal (`api/errors.py`).
 *
 * @param {import("node:http").ServerResponse} response
 * @param {number} status
 * @param {string} error
 * @param {string} detail
 */
function refuse(response, status, error, detail) {
  json(response, status, { error, detail });
}

/**
 * The body of a write, as JSON; `null` if there was none or it was not.
 *
 * @param {import("node:http").IncomingMessage} request
 * @returns {Promise<Record<string, unknown> | null>}
 */
function body(request) {
  return new Promise((done) => {
    /** @type {Buffer[]} */
    const chunks = [];
    request.on("data", (/** @type {Buffer} */ chunk) =>
      chunks.push(Buffer.from(chunk)),
    );
    request.on("end", () => {
      try {
        done(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        done(null);
      }
    });
  });
}

const UUID = "[0-9a-fA-F-]{36}";
const ONE = new RegExp(`^/api/conversations/(${UUID})$`);
const CANCEL = new RegExp(
  `^/api/conversations/(${UUID})/runs/(${UUID})/cancel$`,
);

/**
 * The conversation routes, as far as the interface uses them.
 *
 * Returns whether it answered, so that the file server below is only reached
 * by what is really a file.
 *
 * @param {import("node:http").IncomingMessage} request
 * @param {import("node:http").ServerResponse} response
 * @param {string} path
 * @param {URLSearchParams} query
 * @returns {Promise<boolean>}
 */
async function conversations(request, response, path, query) {
  const method = request.method ?? "GET";
  if (path === "/api/conversations" && method === "GET") {
    const cursor = query.get("cursor");
    const from = cursor === null ? 0 : Number(cursor);
    const items = listed.slice(from, from + PAGE);
    const next = from + PAGE;
    json(response, 200, {
      items,
      next_cursor: next < listed.length ? String(next) : null,
    });
    return true;
  }
  const one = ONE.exec(path);
  if (one !== null) {
    const id = one[1] ?? "";
    const index = listed.findIndex((each) => each.id === id);
    const held = trees.get(id);
    if (index === -1 || held === undefined) {
      // One that is not there and one that is somebody else's answer alike.
      refuse(
        response,
        404,
        "NotFoundError",
        "there is nothing here of that id",
      );
      return true;
    }
    const found = listed[index];
    if (found === undefined) return true;
    if (method === "GET") {
      json(response, 200, { conversation: found, ...held });
      return true;
    }
    if (method === "PATCH") {
      const asked = await body(request);
      const title = typeof asked?.title === "string" ? asked.title.trim() : "";
      if (title === "") {
        refuse(
          response,
          422,
          "InvalidValueError",
          "a title is one line with something on it",
        );
        return true;
      }
      const renamed = { ...found, title };
      listed[index] = renamed;
      json(response, 200, renamed);
      return true;
    }
    if (method === "DELETE") {
      if (held.run_id !== null) {
        // A conversation with a run going is not deleted
        // (docs/specs/conversations.md, "Deletion").
        refuse(
          response,
          409,
          "RunAlreadyActiveError",
          `run ${held.run_id} is running in conversation ${id}; cancel it or wait for it`,
        );
        return true;
      }
      listed.splice(index, 1);
      trees.delete(id);
      response.writeHead(204).end();
      return true;
    }
  }
  const cancel = CANCEL.exec(path);
  if (cancel !== null && method === "POST") {
    const id = cancel[1] ?? "";
    const held = trees.get(id);
    if (held === undefined || held.run_id !== cancel[2]) {
      refuse(
        response,
        404,
        "NotFoundError",
        "there is nothing here of that id",
      );
      return true;
    }
    const run = held.run_id;
    trees.set(id, {
      ...held,
      run_id: null,
      resume: null,
      ended_badly: {
        run_id: run,
        state: "cancelled",
        ended_at: "2026-09-21T16:05:00Z",
      },
    });
    json(response, 200, {
      id: run,
      state: "cancelled",
      started_at: "2026-09-21T16:00:00Z",
      ended_at: "2026-09-21T16:05:00Z",
    });
    return true;
  }
  return false;
}

const server = createServer((request, response) => {
  const asked = new URL(request.url ?? "/", "http://127.0.0.1");
  const path = asked.pathname;
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
  if (path.startsWith("/api/conversations")) {
    void conversations(request, response, path, asked.searchParams).then(
      (answered) => {
        if (!answered) {
          refuse(response, 404, "NotFoundError", "no such route here");
        }
      },
    );
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
