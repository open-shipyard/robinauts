# Testing Strategy


## E2E


### Master e2e journeys

Master e2e journeys should exercise all the main user flows, the paths they will follow on a daily basis and should prevent regressions in the main functionality. That is the most important contract with users.

Master e2e journeys intentionally avoid tricky cases or bugs only reachable through unlikely, less frequent user paths. That kind of cases may need more frequent updates as the implementation changes and the main goal of master e2e journeys is to provide a stable almost quiet test suite that does not change with little implementation details.

### Special e2e

They cover less frequent cases that deserve special attention and do not fit master journeys because of lower relevance, low likelihood to occur, or they are complex in a way that introducing them in master journey would make the master too hard to reason about.

## API tests

They always use a real Postgres DB and the same fake HTTP server as of e2e.
All API tests share one server and one database per run. Each test therefore uses only the conversations it creates.

The only difference is that they skip the browser. They exercise API behavior that the UI cannot trigger or cannot show.

They should be added only for hardening the HTTP API against defective clients or key behavior of the API not visible from the UI.
If a specific behavior can be asserted from the UI, then the right test is e2e.

Valid use cases include, e.g., asserting that the API exposes no secrets, keys, upstream error messages or stack traces, even when the UI does not show them.

## Unit tests

Unit tests are reserved for pure functions and stateless logic that pytest can test alone, without a database, a server or the network.

Same as other test categories, these will use parametrized tests, and can benefit of having such parameters as list or dicts with (input1, input2, expected_output).

Flows should be reachable from such parametrized tests without patching or forcing the internals.

The main use case for this test category is reaching maximum branch coverage on intricate logic on pure, stateless units. For all the other cases, e2e and API tests should be preferred.

## Adapters Free

They focus on a single adapter, run against the real dependency (such as PostgreSQL) or a local stand-in that speaks the same protocol. Goal is to ensure that component is fully usable and functional, disregarding its usage in the application. It should ensure all the surface exposed by the adapter is honored.

## Adapters Metered

Same as above, but they call paid providers and cost money. They run only ad hoc, by hand, and never in a build. They assert the shape of an answer, not its content, because model output varies.

## Fast

All the other categories are placements. Each behavior gets its test in exactly one of them, and they overlap as little as possible.

Fast tests are an extra layer that overlaps the others on purpose. They run the same code again, in process, with pytest and mocks. They are cheap and run first. They catch evident issues early.

A behavior still gets its test in one of the other categories. Its fast test is an addition.

Fast tests aim for close to 80% coverage and the main assertions. Their size in lines of code stays contained.

## Order of execution

Builds run the categories from the cheapest to the most expensive. The fastest tests then fail first:

1. Fast
2. Unit tests
3. Adapters free
4. API tests
5. E2E

Adapters metered never run in a build.
