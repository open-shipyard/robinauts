# robinauts
Conversational agents that play fair

## Try it on this machine

    demo/start.sh          # and demo/stop.sh to take it down again

One command: a throwaway PostgreSQL, the interface built from source, and the
server, with no sign-in and nothing reachable from another machine. It needs
`uv`, Node.js and one model provider key — `OPENROUTER_API_KEY` or
`ANTHROPIC_API_KEY`. [demo/README.md](demo/README.md) is the whole of it.
It is for looking at, and it is not a deployment.

## Deploy

One wheel and its locked dependencies, one PostgreSQL, and a
TLS-terminating reverse proxy.
[docs/deployment.md](docs/deployment.md) is the guide: prerequisites, the
wheel, the database, the configuration file, registering the redirect URI
with Google and Okta, a systemd unit, nginx and Caddy, and a table of what
each start-up refusal means.
