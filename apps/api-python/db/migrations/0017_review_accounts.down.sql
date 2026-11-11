-- Reverse 0017: drop the review logins' code digests, api.ops_review_account_create and the demo flag; `db routines` of the release before restores identity.matching_code and api.ops_seed_demo without them.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.ops_review_account_create(text, text, text, text, text, text, timestamptz);

DROP TABLE identity.review_accounts;

ALTER TABLE tenancy.organizations DROP COLUMN demo;
