# Third-party code and assets in the tree

Everything in the repository that was not written for it: vendored code,
copied components, fonts, icons, images, fixtures, sample data. Each line
states what it is, where it lives, where it came from, and its licence. The
full licence texts are in [LICENSES/](../../LICENSES/).

Dependencies installed by a package manager are not listed here; they are
governed by [DEPENDENCIES.md](../../DEPENDENCIES.md).

| what | where | source | licence |
|---|---|---|---|
| assistant-ui's styled chat components: the thread with its composer, messages, scroll, branch picker and action bar, the Markdown text, the tooltip icon button, the follow-up suggestions, the file and image parts, the reasoning and tool components, and the copy-to-clipboard hook — eleven files | `frontend/src/chat/assistant-ui/vendor/components/assistant-ui/`, `.../hooks/` | [assistant-ui](https://github.com/assistant-ui/assistant-ui), commit `92d16d77a684cff61e6812c0803ea698a8db8b2f`, through the registry at `https://r.assistant-ui.com/` | MIT, Copyright (c) 2025 AgentbaseAI Inc. ([text](../../frontend/src/chat/assistant-ui/vendor/LICENSE)) |
| the five shadcn/ui components those import: button, skeleton, tooltip, textarea, collapsible | `frontend/src/chat/assistant-ui/vendor/components/ui/` | [shadcn/ui](https://github.com/shadcn-ui/ui), commit `98a1fe67b439324ddc857f47fbdce056600a4329`, through the registry at `https://ui.shadcn.com/r/styles/new-york-v4/` | MIT, Copyright (c) 2023 shadcn ([text](../../frontend/src/chat/assistant-ui/vendor/LICENSE.shadcn-ui)) |

Both were copied on 2026-09-22 under
[ADR 0001](../adr/0001-chat-ui-assistant-ui-with-tailwind.md). The
seventeenth file in that directory, `vendor/lib/utils.ts`, is **not**
third-party and is not listed above: it is written here, under this project's
own licence, in place of the registry's `utils` item. What was copied, what
was changed in it and how to re-sync are in
[`frontend/src/chat/assistant-ui/vendor/README.md`](../../frontend/src/chat/assistant-ui/vendor/README.md),
and the copy itself is an entry in [`ip-clearance.md`](ip-clearance.md).
