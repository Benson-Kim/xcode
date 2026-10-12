-- Development-only passwords (equal to the role names, as .env.example).
-- Applied ONLY by the local docker-compose init and by the test harness; never in
-- staging or production, where passwords are set out of band (docs/03-database.md section 2).

ALTER ROLE xcode_owner PASSWORD 'xcode_owner';
ALTER ROLE xcode_app PASSWORD 'xcode_app';
ALTER ROLE xcode_operator PASSWORD 'xcode_operator';
ALTER ROLE xcode_readonly PASSWORD 'xcode_readonly';
