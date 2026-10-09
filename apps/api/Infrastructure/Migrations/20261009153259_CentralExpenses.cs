using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class CentralExpenses : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "CentralExpenses",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Date = table.Column<DateOnly>(type: "date", nullable: false),
                    VehicleId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    ExpenseItemId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Units = table.Column<decimal>(type: "decimal(12,3)", precision: 12, scale: 3, nullable: false),
                    UnitAmount = table.Column<decimal>(type: "decimal(14,2)", precision: 14, scale: 2, nullable: false),
                    Total = table.Column<decimal>(type: "decimal(14,2)", precision: 14, scale: 2, nullable: false),
                    Note = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: true),
                    GroupId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    GroupSize = table.Column<int>(type: "int", nullable: false),
                    GroupTotal = table.Column<decimal>(type: "decimal(14,2)", precision: 14, scale: 2, nullable: false),
                    GroupUnits = table.Column<decimal>(type: "decimal(12,3)", precision: 12, scale: 3, nullable: false),
                    GroupUnitAmount = table.Column<decimal>(type: "decimal(14,2)", precision: 14, scale: 2, nullable: false),
                    RecordedBy = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    RecordedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    UpdatedBy = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    RemovedBy = table.Column<Guid>(type: "uniqueidentifier", nullable: true),
                    RemovedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true),
                    RemovalReason = table.Column<string>(type: "nvarchar(500)", maxLength: 500, nullable: true),
                    Version = table.Column<long>(type: "bigint", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CentralExpenses", x => new { x.OrganizationId, x.Id });
                    table.ForeignKey(
                        name: "FK_CentralExpenses_ExpenseItem_OrganizationId_ExpenseItemId",
                        columns: x => new { x.OrganizationId, x.ExpenseItemId },
                        principalTable: "ExpenseItem",
                        principalColumns: new[] { "OrganizationId", "Id" },
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_CentralExpenses_FleetVehicle_OrganizationId_VehicleId",
                        columns: x => new { x.OrganizationId, x.VehicleId },
                        principalTable: "FleetVehicle",
                        principalColumns: new[] { "OrganizationId", "Id" },
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_CentralExpenses_Organizations_OrganizationId",
                        column: x => x.OrganizationId,
                        principalTable: "Organizations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CentralExpenses_OrganizationId_Date",
                table: "CentralExpenses",
                columns: new[] { "OrganizationId", "Date" });

            migrationBuilder.CreateIndex(
                name: "IX_CentralExpenses_OrganizationId_ExpenseItemId",
                table: "CentralExpenses",
                columns: new[] { "OrganizationId", "ExpenseItemId" });

            migrationBuilder.CreateIndex(
                name: "IX_CentralExpenses_OrganizationId_GroupId_VehicleId",
                table: "CentralExpenses",
                columns: new[] { "OrganizationId", "GroupId", "VehicleId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_CentralExpenses_OrganizationId_VehicleId_Date",
                table: "CentralExpenses",
                columns: new[] { "OrganizationId", "VehicleId", "Date" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CentralExpenses");
        }
    }
}
