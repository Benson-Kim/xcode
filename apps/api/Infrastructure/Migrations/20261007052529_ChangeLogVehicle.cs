using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class ChangeLogVehicle : Migration
    {
        // Rows logged before the column existed take their vehicle from the entity: the vehicle itself for vehicle and
        // investment changes, the record's vehicle for revenue (records are never deleted). EF cannot do this, because
        // change-log rows are write-once. Frozen as written, and plain SQL, so it runs on SQL Server and on SQLite alike.
        public const string BackfillVehiclesSql = """
            UPDATE [OrganizationSettingsVersion] SET [VehicleId] = [EntityId]
            WHERE [VehicleId] IS NULL AND [Section] IN ('vehicles', 'investment')
            """;

        public const string BackfillRevenueSql = """
            UPDATE [OrganizationSettingsVersion] SET [VehicleId] = (
                SELECT [r].[VehicleId] FROM [RevenueRecords] AS [r]
                WHERE [r].[OrganizationId] = [OrganizationSettingsVersion].[OrganizationId] AND [r].[Id] = [OrganizationSettingsVersion].[EntityId])
            WHERE [VehicleId] IS NULL AND [Section] = 'revenue' AND EXISTS (
                SELECT 1 FROM [RevenueRecords] AS [r]
                WHERE [r].[OrganizationId] = [OrganizationSettingsVersion].[OrganizationId] AND [r].[Id] = [OrganizationSettingsVersion].[EntityId])
            """;

        // Each statement only touches rows still unset, and a row it touches is set, so the loop ends and can be rerun.
        public static string Batched(string update) => $"""
            WHILE 1 = 1
            BEGIN
                {update.Replace("UPDATE [OrganizationSettingsVersion]", "UPDATE TOP (5000) [OrganizationSettingsVersion]")};
                IF @@ROWCOUNT = 0 BREAK;
            END
            """;

        public const string AddVehicleIdSql = """
            IF COL_LENGTH(N'[OrganizationSettingsVersion]', N'VehicleId') IS NULL
                ALTER TABLE [OrganizationSettingsVersion] ADD [VehicleId] uniqueidentifier NULL;
            """;

        // Online builds keep the change log writable, but only Enterprise (3), Azure SQL Database (5) and Managed
        // Instance (8) offer them.
        private static string CreateIndex(string name, string columns) => $"""
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE [name] = N'{name}' AND [object_id] = OBJECT_ID(N'[OrganizationSettingsVersion]'))
            BEGIN
                IF CAST(SERVERPROPERTY('EngineEdition') AS int) IN (3, 5, 8)
                    EXEC(N'CREATE INDEX [{name}] ON [OrganizationSettingsVersion] ({columns}) WITH (ONLINE = ON)');
                ELSE
                    CREATE INDEX [{name}] ON [OrganizationSettingsVersion] ({columns});
            END
            """;

        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // The first statement run outside a transaction commits this one before the migration is recorded, so a run
            // stopped after it starts again here: every step checks before it changes anything.
            migrationBuilder.Sql(AddVehicleIdSql);

            // Outside the migration's transaction, so each batch commits and locks stay short on a large change log.
            migrationBuilder.Sql(Batched(BackfillVehiclesSql), suppressTransaction: true);
            migrationBuilder.Sql(Batched(BackfillRevenueSql), suppressTransaction: true);

            migrationBuilder.Sql(CreateIndex("IX_OrganizationSettingsVersion_OrganizationId_OccurredAt",
                "[OrganizationId], [OccurredAt]"), suppressTransaction: true);
            migrationBuilder.Sql(CreateIndex("IX_OrganizationSettingsVersion_OrganizationId_Section_VehicleId",
                "[OrganizationId], [Section], [VehicleId]"), suppressTransaction: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_OrganizationSettingsVersion_OrganizationId_OccurredAt",
                table: "OrganizationSettingsVersion");

            migrationBuilder.DropIndex(
                name: "IX_OrganizationSettingsVersion_OrganizationId_Section_VehicleId",
                table: "OrganizationSettingsVersion");

            migrationBuilder.DropColumn(
                name: "VehicleId",
                table: "OrganizationSettingsVersion");
        }
    }
}
