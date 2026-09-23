# robinauts
Conversational agents that play fair

## Deploy

One wheel and its locked dependencies, one PostgreSQL, and a
TLS-terminating reverse proxy.
[docs/deployment.md](docs/deployment.md) is the guide: prerequisites, the
wheel, the database, the configuration file, registering the redirect URI
with Google and Okta, a systemd unit, nginx and Caddy, and a table of what
each start-up refusal means.
