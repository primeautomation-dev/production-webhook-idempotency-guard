Webhook Processing Guard

Production-safe reference implementation for handling webhooks in at-least-once delivery systems.

Focuses on idempotency, concurrency, and crash recovery — the real reasons webhook code fails in production.

Problem

Webhook providers (Stripe, PayPal, Twilio, Shopify) deliver events at least once.

In real systems this causes:

Duplicate charges

Duplicate emails

Race conditions under concurrent delivery

Ambiguous state after process crashes

Naive solutions (check-then-process, unique constraints, transactions) break under retry + concurrency + crash combinations.

Core Idea

Use a three-state model with an explicit crash boundary:

PENDING – reserved, not started

PROCESSING – side effect may be executing (crash-safe marker)

COMPLETE / FAILED – terminal states

PROCESSING is written before executing side effects, making crashes detectable and recoverable.

Guarantees

This system guarantees:

Exactly-once business effect per webhook

Safe handling of retries

Safe handling of concurrent deliveries

Crash detection via durable state

Cached responses for completed webhooks

Non-Goals

This project does not aim to:

Roll back external side effects

Enforce cross-webhook ordering

Be a full framework or SaaS

Hide trade-offs or edge cases

Project Structure
src/webhook_guard/
├── guard.py   # core algorithm
├── store.py   # persistence boundary
├── lock.py    # distributed locking
├── models.py  # domain types

tests/
├── test_duplicate.py
└── test_concurrent.py


Small, reviewable, and focused on production failure modes.

Who This Is For

Backend / Integration Engineers

Payments & subscription systems

Event-driven architectures

Hiring teams evaluating production experience

Purpose of This Repo

Not a drop-in library.

This is a reference implementation demonstrating how to think about:

failure boundaries

idempotency

concurrency

crash recovery

The goal is to show production reasoning, not framework polish.
