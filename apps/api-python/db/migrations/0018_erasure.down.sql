-- Reverse 0018: drop the shared-account check, the review-login delete, the history rewrite and its helper, the erasure checks and erased_at, and make email and phone_number required again. An erased account has neither, so the reversal refuses while one exists; erased details cannot be brought back.

SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM identity.users WHERE erased_at IS NOT NULL) THEN
    RAISE EXCEPTION 'identity.users holds erased accounts; 0018 cannot be reversed';
  END IF;
END;
$$;

DROP FUNCTION IF EXISTS tenancy.belongs_elsewhere(uuid, uuid);
DROP FUNCTION IF EXISTS identity.erase_review_login(uuid);
DROP FUNCTION IF EXISTS tenancy.erase_person_history(uuid, uuid);
DROP FUNCTION IF EXISTS tenancy.erased_snapshot(text);

ALTER TABLE identity.users
  DROP CONSTRAINT ck_users_erased_removed,
  DROP CONSTRAINT ck_users_erased_phone_number,
  DROP CONSTRAINT ck_users_erased_email,
  ALTER COLUMN phone_number SET NOT NULL,
  ALTER COLUMN email SET NOT NULL,
  DROP COLUMN erased_at;
