# Database implementation contract

The authoritative planned tables/indexes are in docs/SPEC.md. No migrations exist yet.
Production needs durable cloud PostgreSQL 16, encrypted access and backups. GitLab's postgres service is disposable test infrastructure only. Do not import a real historical dataset into CI service storage.
Future tests must verify unique source IDs, idempotent upserts, raw snapshot checksums, resume after crash, transaction boundaries and absence of duplicate renewals on recomputation.
