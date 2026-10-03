using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class NormalizeSecurityPolicy : Migration
    {
        // Earlier versions accepted a lockout after one try and a pause of up to 1440 minutes. Every stored value is
        // brought to the nearest one the current bounds allow, so the checks below can be added. Frozen as written:
        // later bounds need a migration of their own. Plain CASE, so it runs on SQL Server and on SQLite alike.
        public const string ClampSql = """
            UPDATE [SecurityPolicies] SET
                [PasswordMinLength] = CASE WHEN [PasswordMinLength] < 12 THEN 12 WHEN [PasswordMinLength] > 128 THEN 128 ELSE [PasswordMinLength] END,
                [PasswordHistory] = CASE WHEN [PasswordHistory] < 0 THEN 0 WHEN [PasswordHistory] > 24 THEN 24 ELSE [PasswordHistory] END,
                [PinLength] = CASE WHEN [PinLength] < 4 THEN 4 WHEN [PinLength] > 8 THEN 8 ELSE [PinLength] END,
                [LockoutThreshold] = CASE WHEN [LockoutThreshold] < 3 THEN 3 WHEN [LockoutThreshold] > 10 THEN 10 ELSE [LockoutThreshold] END,
                [LockoutMinutes] = CASE WHEN [LockoutMinutes] < 1 THEN 1 WHEN [LockoutMinutes] > 60 THEN 60 ELSE [LockoutMinutes] END,
                [AccessTokenMinutes] = CASE WHEN [AccessTokenMinutes] < 1 THEN 1 WHEN [AccessTokenMinutes] > 15 THEN 15 ELSE [AccessTokenMinutes] END,
                [RefreshTokenDays] = CASE WHEN [RefreshTokenDays] < 1 THEN 1 WHEN [RefreshTokenDays] > 90 THEN 90 ELSE [RefreshTokenDays] END,
                [IdleUnlockSeconds] = CASE WHEN [IdleUnlockSeconds] < 30 THEN 30 WHEN [IdleUnlockSeconds] > 3600 THEN 3600 ELSE [IdleUnlockSeconds] END
            """;

        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql(ClampSql);

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_AccessTokenMinutes",
                table: "SecurityPolicies",
                sql: "[AccessTokenMinutes] BETWEEN 1 AND 15");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_IdleUnlockSeconds",
                table: "SecurityPolicies",
                sql: "[IdleUnlockSeconds] BETWEEN 30 AND 3600");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_LockoutMinutes",
                table: "SecurityPolicies",
                sql: "[LockoutMinutes] BETWEEN 1 AND 60");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_LockoutThreshold",
                table: "SecurityPolicies",
                sql: "[LockoutThreshold] BETWEEN 3 AND 10");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_PasswordHistory",
                table: "SecurityPolicies",
                sql: "[PasswordHistory] BETWEEN 0 AND 24");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_PasswordMinLength",
                table: "SecurityPolicies",
                sql: "[PasswordMinLength] BETWEEN 12 AND 128");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_PinLength",
                table: "SecurityPolicies",
                sql: "[PinLength] BETWEEN 4 AND 8");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SecurityPolicies_RefreshTokenDays",
                table: "SecurityPolicies",
                sql: "[RefreshTokenDays] BETWEEN 1 AND 90");
        }

        // Removes the checks. The clamped values stay as they are: the out-of-range originals are not kept anywhere.
        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_AccessTokenMinutes",
                table: "SecurityPolicies");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_IdleUnlockSeconds",
                table: "SecurityPolicies");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_LockoutMinutes",
                table: "SecurityPolicies");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_LockoutThreshold",
                table: "SecurityPolicies");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_PasswordHistory",
                table: "SecurityPolicies");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_PasswordMinLength",
                table: "SecurityPolicies");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_PinLength",
                table: "SecurityPolicies");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SecurityPolicies_RefreshTokenDays",
                table: "SecurityPolicies");
        }
    }
}
