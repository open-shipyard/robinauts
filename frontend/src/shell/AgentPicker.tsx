// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * Which agent the next conversation is with (`docs/specs/agents.md`).
 *
 * It shows on an empty chat and nowhere else: once a conversation exists,
 * the agent is a fact about it rather than a choice. Hidden when the
 * deployment has one agent, because there is nothing to pick.
 *
 * The choice is remembered per browser, and checked against what the
 * deployment still offers: an agent removed from the configuration is not
 * one this picker will quietly keep selecting.
 */
import { useEffect, useState } from "react";

import { request } from "../api/client";
import type { components } from "../api/schema";
import { remember, remembered } from "./storage";

export type Agent = components["schemas"]["AgentSummary"];

export const AGENT_KEY = "agent";

/** What this deployment offers, as far as the one call has got. */
export type Agents =
  | { status: "loading" }
  | { status: "ready"; items: Agent[] }
  | { status: "failed"; detail: string };

/**
 * The agents, asked for once.
 *
 * Called by the shell rather than by the picker, because the picker lives
 * inside the empty chat, which is remounted every time "New chat" is
 * pressed. Fetching from there would mean a call per click for a list that
 * only changes when somebody edits the configuration and restarts the
 * server.
 */
export function useAgents(): Agents {
  const [agents, setAgents] = useState<Agents>({ status: "loading" });
  useEffect(() => {
    const dropped = new AbortController();
    request("get", "/api/agents", { signal: dropped.signal }).then(
      (answer) => {
        setAgents({ status: "ready", items: answer.items });
      },
      (failure: unknown) => {
        // An abort is this component going away, not a failure to show.
        if (dropped.signal.aborted) return;
        setAgents({
          status: "failed",
          detail: failure instanceof Error ? failure.message : String(failure),
        });
      },
    );
    return () => {
      dropped.abort();
    };
  }, []);
  return agents;
}

/** The remembered agent if it is still offered, otherwise the first one. */
function chosenFrom(items: Agent[], kept: string | null): string | null {
  const first = items[0];
  if (first === undefined) return null;
  return items.some((agent) => agent.id === kept) && kept !== null
    ? kept
    : first.id;
}

/**
 * Which agent a first message would go to, and how to change it.
 *
 * **Held above the picker**, because it is not only the picker's business:
 * the chat needs it to begin a conversation (`src/chat/index.ts`), and the
 * picker is what the chat shows above its box. It is the shell that has both
 * of them in view, so the shell holds the choice.
 *
 * `null` while the agents have not arrived, and where the deployment has
 * none -- which is a deployment with nobody to talk to, not a choice nobody
 * has made yet.
 */
export function useChosenAgent(
  agents: Agents,
): [string | null, (id: string) => void] {
  const [kept, setKept] = useState<string | null>(() => remembered(AGENT_KEY));
  const chosen =
    agents.status === "ready" ? chosenFrom(agents.items, kept) : null;
  return [
    chosen,
    (id: string) => {
      setKept(id);
      remember(AGENT_KEY, id);
    },
  ];
}

export function AgentPicker({
  agents,
  chosen,
  onChoose,
}: {
  agents: Agents;
  chosen: string | null;
  onChoose: (id: string) => void;
}) {
  if (agents.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading the agents…</p>;
  }
  if (agents.status === "failed") {
    return (
      <p role="alert" className="text-sm text-bad">
        The agents could not be loaded: {agents.detail}
      </p>
    );
  }
  if (agents.items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2">
        <select
          aria-label="Agent"
          disabled
          className="rounded-ui border border-edge bg-paper px-2 py-1 text-ink"
        >
          <option>No agent</option>
        </select>
        <p role="alert" className="text-sm text-muted-foreground">
          This deployment has no agent configured, so there is nobody to talk
          to. Whoever runs it adds one to the configuration file.
        </p>
      </div>
    );
  }
  // One agent is not a choice: it is simply who you are talking to.
  if (agents.items.length === 1) return null;

  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      Agent
      <select
        value={chosen ?? ""}
        onChange={(event) => {
          onChoose(event.target.value);
        }}
        className="rounded-ui border border-edge bg-paper px-2 py-1 text-ink"
      >
        {agents.items.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {agent.title}
          </option>
        ))}
      </select>
    </label>
  );
}
