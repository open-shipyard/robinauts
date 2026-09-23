// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { json, refusal, stubFetch, type Call } from "../test/api";
import {
  conversation,
  id,
  madeBy,
  message,
  opened,
  RUN,
} from "../test/conversations";
import { ConversationView } from "./ConversationView";

const TREE = [
  message("root", null, "user", "What is a robin?"),
  message("answer-a", "root", "assistant", "A bird.", madeBy()),
  message("answer-c", "root", "assistant", "Another answer.", madeBy()),
  message("follow-up", "answer-a", "user", "What does it eat?"),
  message(
    "answer-b",
    "follow-up",
    "assistant",
    "Worms.",
    madeBy("helper", "pydantic-ai"),
  ),
];

/** Render it, and let the one call arrive. */
async function view(
  answer: (call: Call) => Response,
  title?: string,
  onReread?: () => void,
) {
  const fetch = stubFetch(answer);
  const drawn = render(
    <ConversationView
      id={id(1)}
      {...(title === undefined ? {} : { title })}
      {...(onReread === undefined ? {} : { onReread })}
    />,
  );
  await waitFor(() => {
    expect(screen.queryByText("Loading the conversation…")).toBeNull();
  });
  return { ...drawn, fetch };
}

const said = () =>
  screen.getAllByRole("listitem").map((one) => one.textContent);

test("the title is the first line of the view, and the branch is under it", async () => {
  await view(() => json(opened(conversation(1, "Robins"), TREE, "answer-b")));

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Robins");
  // The leaf's ancestry, in the order it was said -- and not the sibling
  // branch, which came with the answer but is not what is open.
  expect(said()).toHaveLength(4);
  expect(said().join(" ")).toContain("Worms.");
  expect(said().join(" ")).not.toContain("Another answer.");
  expect(screen.getByText("What is a robin?")).toBeVisible();
});

test("each message says who said it, when, and what produced it", async () => {
  await view(() => json(opened(conversation(1, "Robins"), TREE, "answer-b")));

  expect(screen.getAllByText("You")).toHaveLength(2);
  expect(screen.getAllByText("Assistant")).toHaveLength(2);
  // The machine-readable time is the stored one, whatever this browser
  // writes beside it.
  const times = screen.getAllByText(
    (_, element) => element?.tagName === "TIME",
  );
  expect(times[0]).toHaveAttribute("datetime", "2026-09-02T09:30:00Z");
  // The agent and the engine of the answer, shown small.
  expect(screen.getByText("helper · pydantic-ai")).toBeVisible();
});

test("a conversation with nothing in it says so", async () => {
  await view(() => json(opened(conversation(1, "Empty"), [], null)));
  expect(screen.getByText("Nothing has been said in it yet.")).toBeVisible();
});

test("the panel's title is what the heading shows once it is renamed", async () => {
  // The panel is where renaming happens; the heading must not go on saying
  // what the conversation was called when it was opened.
  await view(
    () => json(opened(conversation(1, "Before"), TREE, "answer-b")),
    "After",
  );
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("After");
});

test("a run in flight says so and can be stopped", async () => {
  let cancelled = false;
  const { fetch } = await view((call) => {
    if (call.method === "POST") {
      cancelled = true;
      return json({
        id: RUN,
        state: "cancelled",
        started_at: "2026-09-02T09:29:00Z",
        ended_at: "2026-09-02T09:31:00Z",
      });
    }
    return json(
      opened(
        conversation(1, "Robins"),
        TREE,
        "answer-b",
        cancelled
          ? {
              ended_badly: {
                run_id: RUN,
                state: "cancelled",
                ended_at: "2026-09-02T09:31:00Z",
              },
            }
          : { run_id: RUN, resume: { after: 3, follows: "answer-b" } },
      ),
    );
  });

  expect(screen.getByRole("status")).toHaveTextContent("Answering…");

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  });

  expect(
    fetch.mock.calls.filter(
      ([url, init]) =>
        init?.method === "POST" &&
        String(url) === `/api/conversations/${id(1)}/runs/${RUN}/cancel`,
    ),
  ).toHaveLength(1);
  // The state of the run is the server's to report, so it is asked again.
  await waitFor(() => {
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
  });
  expect(screen.getByRole("status")).toHaveTextContent(
    "The last answer was stopped before it was finished.",
  );
});

test("a cancel that is refused is said, and the run is still going", async () => {
  await view((call) =>
    call.method === "POST"
      ? refusal(409, "IllegalTransitionError", "the run has already ended")
      : json(
          opened(conversation(1, "Robins"), TREE, "answer-b", {
            run_id: RUN,
            resume: { after: 3, follows: "answer-b" },
          }),
        ),
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "The answer was not stopped: the run has already ended",
  );
  expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
});

test("a run that ended badly is a sentence, one per state", async () => {
  for (const [state, says] of [
    ["failed", "something went wrong"],
    ["interrupted", "interrupted when the server stopped"],
  ] as const) {
    const { unmount } = await view(() =>
      json(
        opened(conversation(1, "Robins"), TREE, "answer-b", {
          ended_badly: {
            run_id: RUN,
            state,
            ended_at: "2026-09-02T09:31:00Z",
          },
        }),
      ),
    );
    expect(screen.getByRole("status")).toHaveTextContent(says);
    unmount();
  }
});

test("a conversation that is not here says so, with a way onwards", async () => {
  await view(() =>
    refusal(404, "NotFoundError", "there is nothing here of that id"),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "This conversation is not here",
  );
  expect(
    screen.getByRole("link", { name: "Start a new chat" }),
  ).toHaveAttribute("href", "#/");
});

test("any other refusal says what the server said", async () => {
  await view(() =>
    refusal(500, "InternalError", "the request could not be served"),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "This conversation could not be opened: the request could not be served",
  );
});

test("rereading the conversation asks for the panel's list again too", async () => {
  // Otherwise the heading and the row it came from would be two readings of
  // one conversation, taken at different moments.
  const reread = vi.fn();
  await view(
    (call) =>
      call.method === "POST"
        ? json({
            id: RUN,
            state: "cancelled",
            started_at: null,
            ended_at: "2026-09-02T09:31:00Z",
          })
        : json(
            opened(conversation(1, "Robins"), TREE, "answer-b", {
              run_id: RUN,
              resume: { after: 3, follows: "answer-b" },
            }),
          ),
    undefined,
    reread,
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  });
  expect(reread).toHaveBeenCalledTimes(1);
});
