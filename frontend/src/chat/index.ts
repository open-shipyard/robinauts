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
 * Empty until step 21, which brings the chat itself.
 */

/**
 * A conversation, as the rest of the application refers to one: the id the
 * backend gave it, and nothing a chat library chose.
 */
export type ConversationId = string;
