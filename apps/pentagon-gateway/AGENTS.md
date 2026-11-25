# Pentagon Gateway conventions

Follow the repository [engineering instructions](../../AGENTS.md) and the
[development conventions](README.md#development) for this app. The checked-in
ESLint and Prettier configurations apply to source, tests, and tool configuration.

Run `npm ci` for development tools, then `npm run check` before committing a change.
Use `npm run lint:fix` and `npm run format` to apply mechanical fixes; review the
diff and rerun the checks. Keep runtime dependencies confined to Node's standard
library and preserve the gateway/broker/relay boundaries described in the README.

For shared readability and module design decisions, resolve the coding root using
the repository's discovery procedure and read
`common/engineering/references/readability-and-boundaries.md`. Local lint rules
are the executable style baseline; passing them does not establish that a module
has a clear responsibility or that approval and recovery behavior is correct.
