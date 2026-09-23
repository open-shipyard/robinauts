// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The chat seam (ADR 0001).
 *
 * This module is the only thing about the chat that the rest of the
 * application may import. assistant-ui lives under `src/chat/assistant-ui/`,
 * which does not exist yet, and nothing outside that directory may name it or
 * its packages; `eslint.config.js` refuses an import that tries.
 *
 * What goes here is a small interface this project owns -- in essence a
 * `<Chat>` taking a conversation id and callbacks -- whose types mention
 * nothing from assistant-ui. Deleting `src/chat/assistant-ui/` and the
 * `@assistant-ui/*` packages must leave exactly one thing broken: the
 * implementation behind this file.
 *
 * **Types only, until step 21 brings the chat itself.** What is written here
 * is what the application will hand a `<Chat>` and what it needs back from
 * one; nothing in it names, or could name, a chat library. The shell, the
 * router and the history already use these names, so the seam is the one
 * vocabulary the two sides share rather than something invented on the day
 * the implementation lands.
 */

/**
 * A conversation, as the rest of the application refers to one: the id the
 * backend gave it, and nothing a chat library chose.
 */
export type ConversationId = string;

/**
 * An agent, as the configuration names it and the picker offers it
 * (`docs/specs/agents.md`).
 *
 * The id alone: which model an agent runs, what its prompt says and who its
 * vendor is are the operator's, and none of it reaches the browser.
 */
export type AgentId = string;

/**
 * What the chat is given, and the one thing it says back.
 *
 * `conversationId` is `null` on the empty chat -- the application opens on
 * one, ready for a first message (`docs/specs/frontend.md`) -- and the id of
 * the conversation being read otherwise. `agentId` is the agent a first
 * message will start the conversation with, which is a choice only while
 * there is no conversation: after that the agent is a fact about it
 * (`docs/specs/conversations.md`). It is `null` when the deployment has told
 * us no agents, or has not told us yet.
 *
 * `onConversationStarted` is the one thing the chat cannot decide for the
 * application: a first message creates a conversation
 * (`POST /api/turns`, `docs/specs/wire.md`), and the interface then has a
 * conversation to be on -- a route to go to and a row for the panel. The
 * chat reports the id; what to do about it is the application's.
 */
export interface ChatProps {
  conversationId: ConversationId | null;
  agentId: AgentId | null;
  onConversationStarted: (id: ConversationId) => void;
}
