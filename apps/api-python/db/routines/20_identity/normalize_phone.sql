-- identity.normalize_phone(p_input text) RETURNS text
-- Purpose: a Kenyan mobile number as +254XXXXXXXXX from the 12-, 10- and 9-digit forms (every character that is not a decimal digit stripped, as .NET's \D; a decimal digit outside 0-9, any Unicode Nd character of the explicit list below (Unicode 15.1), refused); NULL when it does not normalise.
-- Callers: identity.lock_account, api.ops_provision_user.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.normalize_phone(p_input text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_input IS NULL OR p_input ~ '[\u0660-\u0669\u06F0-\u06F9\u07C0-\u07C9\u0966-\u096F\u09E6-\u09EF\u0A66-\u0A6F\u0AE6-\u0AEF\u0B66-\u0B6F\u0BE6-\u0BEF\u0C66-\u0C6F\u0CE6-\u0CEF\u0D66-\u0D6F\u0DE6-\u0DEF\u0E50-\u0E59\u0ED0-\u0ED9\u0F20-\u0F29\u1040-\u1049\u1090-\u1099\u17E0-\u17E9\u1810-\u1819\u1946-\u194F\u19D0-\u19D9\u1A80-\u1A89\u1A90-\u1A99\u1B50-\u1B59\u1BB0-\u1BB9\u1C40-\u1C49\u1C50-\u1C59\uA620-\uA629\uA8D0-\uA8D9\uA900-\uA909\uA9D0-\uA9D9\uA9F0-\uA9F9\uAA50-\uAA59\uABF0-\uABF9\uFF10-\uFF19\U000104A0-\U000104A9\U00010D30-\U00010D39\U00011066-\U0001106F\U000110F0-\U000110F9\U00011136-\U0001113F\U000111D0-\U000111D9\U000112F0-\U000112F9\U00011450-\U00011459\U000114D0-\U000114D9\U00011650-\U00011659\U000116C0-\U000116C9\U00011730-\U00011739\U000118E0-\U000118E9\U00011950-\U00011959\U00011C50-\U00011C59\U00011D50-\U00011D59\U00011DA0-\U00011DA9\U00011F50-\U00011F59\U00016A60-\U00016A69\U00016AC0-\U00016AC9\U00016B50-\U00016B59\U0001D7CE-\U0001D7FF\U0001E140-\U0001E149\U0001E2F0-\U0001E2F9\U0001E4F0-\U0001E4F9\U0001E950-\U0001E959\U0001FBF0-\U0001FBF9]' THEN NULL
           WHEN digits.d ~ '^254[17][0-9]{8}$' THEN '+' || digits.d
           WHEN digits.d ~ '^0[17][0-9]{8}$' THEN '+254' || substr(digits.d, 2)
           WHEN digits.d ~ '^[17][0-9]{8}$' THEN '+254' || digits.d
         END
  FROM (SELECT regexp_replace(coalesce(p_input, ''), '[^0-9]', '', 'g') AS d) AS digits;
$$;

REVOKE ALL ON FUNCTION identity.normalize_phone(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.normalize_phone(text) TO xcode_api_executor;
