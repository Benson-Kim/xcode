using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

#pragma warning disable CA1814 // Prefer jagged arrays over multidimensional

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class ExpenseCatalogAndInvestment : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "Bucket",
                table: "RecurringVersion",
                type: "int",
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "ExpenseItemId",
                table: "RecurringVersion",
                type: "uniqueidentifier",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Month",
                table: "RecurringVersion",
                type: "int",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Note",
                table: "RecurringVersion",
                type: "nvarchar(200)",
                maxLength: 200,
                nullable: true);

            migrationBuilder.CreateTable(
                name: "ExpenseBucketLookup",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false),
                    Name = table.Column<string>(type: "nvarchar(max)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExpenseBucketLookup", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "VehicleInvestment",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    VehicleId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Date = table.Column<DateOnly>(type: "date", nullable: false),
                    Description = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    Amount = table.Column<decimal>(type: "decimal(14,2)", precision: 14, scale: 2, nullable: false),
                    RecordedBy = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    RecordedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_VehicleInvestment", x => new { x.OrganizationId, x.Id });
                    table.ForeignKey(
                        name: "FK_VehicleInvestment_FleetVehicle_OrganizationId_VehicleId",
                        columns: x => new { x.OrganizationId, x.VehicleId },
                        principalTable: "FleetVehicle",
                        principalColumns: new[] { "OrganizationId", "Id" },
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_VehicleInvestment_Memberships_OrganizationId_RecordedBy",
                        columns: x => new { x.OrganizationId, x.RecordedBy },
                        principalTable: "Memberships",
                        principalColumns: new[] { "OrganizationId", "UserId" },
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_VehicleInvestment_Organizations_OrganizationId",
                        column: x => x.OrganizationId,
                        principalTable: "Organizations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "ExpenseCategory",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Name = table.Column<string>(type: "nvarchar(100)", maxLength: 100, nullable: false),
                    NormalizedName = table.Column<string>(type: "nvarchar(100)", maxLength: 100, nullable: false),
                    Bucket = table.Column<int>(type: "int", nullable: false),
                    StoppedOn = table.Column<DateOnly>(type: "date", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExpenseCategory", x => new { x.OrganizationId, x.Id });
                    table.ForeignKey(
                        name: "FK_ExpenseCategory_ExpenseBucketLookup_Bucket",
                        column: x => x.Bucket,
                        principalTable: "ExpenseBucketLookup",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_ExpenseCategory_Organizations_OrganizationId",
                        column: x => x.OrganizationId,
                        principalTable: "Organizations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "ExpenseItem",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    CategoryId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Name = table.Column<string>(type: "nvarchar(100)", maxLength: 100, nullable: false),
                    NormalizedName = table.Column<string>(type: "nvarchar(100)", maxLength: 100, nullable: false),
                    StoppedOn = table.Column<DateOnly>(type: "date", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExpenseItem", x => new { x.OrganizationId, x.Id });
                    table.ForeignKey(
                        name: "FK_ExpenseItem_ExpenseCategory_OrganizationId_CategoryId",
                        columns: x => new { x.OrganizationId, x.CategoryId },
                        principalTable: "ExpenseCategory",
                        principalColumns: new[] { "OrganizationId", "Id" },
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_ExpenseItem_Organizations_OrganizationId",
                        column: x => x.OrganizationId,
                        principalTable: "Organizations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.InsertData(
                table: "ExpenseBucketLookup",
                columns: new[] { "Id", "Name" },
                values: new object[,]
                {
                    { 1, "RepairsAndMaintenance" },
                    { 2, "RecurringCharges" },
                    { 3, "LoanRepayments" }
                });

            // Assumption A2: legacy cost versions report under a bucket. RepairsAndUpkeep (2) counts as repairs and
            // maintenance (1); running costs, crew costs and fixed commitments count as recurring charges (2). Only the
            // new column is filled; nothing the version already recorded changes.
            migrationBuilder.Sql(
                "UPDATE [RecurringVersion] SET [Bucket] = CASE WHEN [Category] = 2 THEN 1 ELSE 2 END " +
                "WHERE [Kind] = 1 AND [Category] IS NOT NULL AND [Bucket] IS NULL;");

            migrationBuilder.InsertData(
                table: "RecurrenceFrequencyLookup",
                columns: new[] { "Id", "Name" },
                values: new object[] { 4, "Yearly" });

            migrationBuilder.CreateIndex(
                name: "IX_RecurringVersion_Bucket",
                table: "RecurringVersion",
                column: "Bucket");

            migrationBuilder.CreateIndex(
                name: "IX_RecurringVersion_OrganizationId_ExpenseItemId",
                table: "RecurringVersion",
                columns: new[] { "OrganizationId", "ExpenseItemId" });

            migrationBuilder.CreateIndex(
                name: "IX_ExpenseCategory_Bucket",
                table: "ExpenseCategory",
                column: "Bucket");

            migrationBuilder.CreateIndex(
                name: "IX_ExpenseCategory_OrganizationId_NormalizedName",
                table: "ExpenseCategory",
                columns: new[] { "OrganizationId", "NormalizedName" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ExpenseItem_OrganizationId_CategoryId_NormalizedName",
                table: "ExpenseItem",
                columns: new[] { "OrganizationId", "CategoryId", "NormalizedName" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_VehicleInvestment_OrganizationId_RecordedBy",
                table: "VehicleInvestment",
                columns: new[] { "OrganizationId", "RecordedBy" });

            migrationBuilder.CreateIndex(
                name: "IX_VehicleInvestment_OrganizationId_VehicleId_Date",
                table: "VehicleInvestment",
                columns: new[] { "OrganizationId", "VehicleId", "Date" });

            migrationBuilder.AddForeignKey(
                name: "FK_RecurringVersion_ExpenseBucketLookup_Bucket",
                table: "RecurringVersion",
                column: "Bucket",
                principalTable: "ExpenseBucketLookup",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_RecurringVersion_ExpenseItem_OrganizationId_ExpenseItemId",
                table: "RecurringVersion",
                columns: new[] { "OrganizationId", "ExpenseItemId" },
                principalTable: "ExpenseItem",
                principalColumns: new[] { "OrganizationId", "Id" },
                onDelete: ReferentialAction.Restrict);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_RecurringVersion_ExpenseBucketLookup_Bucket",
                table: "RecurringVersion");

            migrationBuilder.DropForeignKey(
                name: "FK_RecurringVersion_ExpenseItem_OrganizationId_ExpenseItemId",
                table: "RecurringVersion");

            migrationBuilder.DropTable(
                name: "ExpenseItem");

            migrationBuilder.DropTable(
                name: "VehicleInvestment");

            migrationBuilder.DropTable(
                name: "ExpenseCategory");

            migrationBuilder.DropTable(
                name: "ExpenseBucketLookup");

            migrationBuilder.DropIndex(
                name: "IX_RecurringVersion_Bucket",
                table: "RecurringVersion");

            migrationBuilder.DropIndex(
                name: "IX_RecurringVersion_OrganizationId_ExpenseItemId",
                table: "RecurringVersion");

            // Yearly schedules saved since the upgrade still reference lookup row 4, and history is never deleted, so the
            // row is removed only when nothing uses it; otherwise the rollback keeps it and still succeeds.
            migrationBuilder.Sql(
                "DELETE FROM [RecurrenceFrequencyLookup] WHERE [Id] = 4 " +
                "AND NOT EXISTS (SELECT 1 FROM [RecurringVersion] WHERE [Frequency] = 4);");

            migrationBuilder.DropColumn(
                name: "Bucket",
                table: "RecurringVersion");

            migrationBuilder.DropColumn(
                name: "ExpenseItemId",
                table: "RecurringVersion");

            migrationBuilder.DropColumn(
                name: "Month",
                table: "RecurringVersion");

            migrationBuilder.DropColumn(
                name: "Note",
                table: "RecurringVersion");
        }
    }
}
