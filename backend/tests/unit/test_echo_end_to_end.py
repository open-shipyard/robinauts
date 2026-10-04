# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The web app over the echo engine and the in-memory store, driven the way the browser does."""

from __future__ import annotations

from test_web_turns import client, events

from aio import asyncio_test


@asyncio_test
async def test_a_conversation_from_the_first_message_to_its_deletion() -> None:
    async with client() as http:
        session = (await http.get("/auth/session")).json()
        assert session["sign_in"] is False
        assert session["user"]["provider"] == "!local"
        agents = (await http.get("/api/agents")).json()["items"]
        assert [a["id"] for a in agents] == ["echo"]
        models = (await http.get("/api/models")).json()["items"]
        assert [m["id"] for m in models] == ["echo"]

        started = await http.post("/api/turns", json={"agent_id": "echo", "text": "hello"})
        assert events(started.text)[-1]["type"] == "RUN_FINISHED"
        cid = started.headers["x-robinauts-conversation-id"]

        listed = (await http.get("/api/conversations")).json()["items"]
        assert [c["id"] for c in listed] == [cid]

        opened = (await http.get(f"/api/conversations/{cid}")).json()
        question, answer = opened["messages"]
        assert question["parts"] == [{"kind": "text", "text": "hello"}]
        call, result, text = answer["parts"]
        assert (call["kind"], call["name"], call["arguments"]) == (
            "tool_call",
            "echo",
            {"text": "hello"},
        )
        assert result == {
            "kind": "tool_result",
            "call_id": call["call_id"],
            "text": "hello",
            "is_error": False,
        }
        assert text == {"kind": "text", "text": "The tool said: hello"}

        again = await http.post(
            f"/api/conversations/{cid}/turns", json={"text": "again", "parent_id": answer["id"]}
        )
        assert events(again.text)[-1]["type"] == "RUN_FINISHED"
        rid = again.headers["x-robinauts-run-id"]
        replayed = events(
            (await http.get(f"/api/conversations/{cid}/runs/{rid}/events?after=0")).text
        )
        assert replayed[0]["type"] == "RUN_STARTED"
        assert replayed[-1]["type"] == "RUN_FINISHED"
        said = "".join(e["delta"] for e in replayed if e["type"] == "TEXT_MESSAGE_CONTENT")
        assert said == "The tool said: again"
        opened = (await http.get(f"/api/conversations/{cid}")).json()
        assert [m["role"] for m in opened["messages"]] == ["user", "assistant"] * 2

        renamed = await http.patch(f"/api/conversations/{cid}", json={"title": "Echoes"})
        assert renamed.json()["title"] == "Echoes"
        assert (await http.delete(f"/api/conversations/{cid}")).status_code == 204
        assert (await http.get("/api/conversations")).json()["items"] == []


@asyncio_test
async def test_a_failed_turn_keeps_what_it_did_and_the_next_one_replies_under_it() -> None:
    async with client() as http:
        started = await http.post("/api/turns", json={"agent_id": "echo", "text": "hello"})
        cid = started.headers["x-robinauts-conversation-id"]
        answer = (await http.get(f"/api/conversations/{cid}")).json()["messages"][1]

        poisoned = await http.post(
            f"/api/conversations/{cid}/turns", json={"text": "poison", "parent_id": answer["id"]}
        )
        assert events(poisoned.text)[-1]["type"] == "RUN_ERROR"
        rid = poisoned.headers["x-robinauts-run-id"]
        opened = (await http.get(f"/api/conversations/{cid}")).json()
        failed = opened["messages"][3]
        assert failed["failed"] is True
        assert [(p["kind"], p.get("is_error")) for p in failed["parts"]] == [
            ("tool_call", None),
            ("tool_result", True),
        ]
        ended = opened["ended_badly"]
        assert (ended["run_id"], ended["state"]) == (rid, "failed")
        assert set(ended) == {"run_id", "state", "ended_at"}  # not the operator's error

        again = await http.post(
            f"/api/conversations/{cid}/turns", json={"text": "again", "parent_id": failed["id"]}
        )
        assert events(again.text)[-1]["type"] == "RUN_FINISHED"
        opened = (await http.get(f"/api/conversations/{cid}")).json()
        assert [m["failed"] for m in opened["messages"]] == [
            False,
            False,
            False,
            True,
            False,
            False,
        ]
        assert opened["ended_badly"] is None
        # Continued from the first answer's checkpoint: echo remembers that turn and this one.
        call = opened["messages"][-1]["parts"][0]
        assert call["call_id"] == "call-2"
        # And told what it missed: the failed exchange, then the new message.
        prompt = call["arguments"]["text"]
        assert "Message: poison" in prompt
        assert "-> error: the message is poisoned" in prompt
        assert prompt.endswith("The user's new message:\n\nagain")


@asyncio_test
async def test_a_retry_answers_the_question_again_and_tells_the_model_what_failed() -> None:
    async with client() as http:
        started = await http.post("/api/turns", json={"agent_id": "echo", "text": "hello"})
        cid = started.headers["x-robinauts-conversation-id"]
        answer = (await http.get(f"/api/conversations/{cid}")).json()["messages"][1]
        poisoned = await http.post(
            f"/api/conversations/{cid}/turns", json={"text": "poison", "parent_id": answer["id"]}
        )
        assert events(poisoned.text)[-1]["type"] == "RUN_ERROR"
        failed = (await http.get(f"/api/conversations/{cid}")).json()["messages"][3]

        not_failed = await http.post(
            f"/api/conversations/{cid}/turns", json={"retry": answer["id"]}
        )
        assert not_failed.status_code == 404

        # Retried as often as wanted: echo fails "poison" every time.
        for _ in range(2):
            retried = await http.post(
                f"/api/conversations/{cid}/turns", json={"retry": failed["id"]}
            )
            assert events(retried.text)[-1]["type"] == "RUN_ERROR"
            opened = (await http.get(f"/api/conversations/{cid}")).json()
            question, again = opened["messages"][2:]
            assert again["id"] != failed["id"]  # a fresh answer to the same question
            assert (question["parts"][0]["text"], again["failed"]) == ("poison", True)
            call = again["parts"][0]
            assert call["call_id"] == "call-2"  # from the first answer's checkpoint
            prompt = call["arguments"]["text"]
            assert prompt.startswith("poison\n")
            assert "-> error: the message is poisoned" in prompt
            assert "pressed the retry button" in prompt
            failed = again
