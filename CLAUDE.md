# EdgeCDSS — read before any work

1. Read docs/WORK_ORDER.md (the order of record) and docs/REFERENCE.md (one-line meaning and status of every item) before starting anything. If they disagree, the work order wins; fix REFERENCE.md first.
2. Every PR that changes an item's status, adds or removes a model tag, changes a Makefile command, or records a finding also updates docs/REFERENCE.md in the same PR.
3. Global rules in docs/WORK_ORDER.md apply to every change: one bug per PR, failing test committed first, replay with 0 newly released, never loosen a gate, never commit .env or keys, signing is the owner's act.
4. Stop for owner review at the end of every item. Do not merge.
