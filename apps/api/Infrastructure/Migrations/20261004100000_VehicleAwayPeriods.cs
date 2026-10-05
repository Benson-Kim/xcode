using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class VehicleAwayPeriods : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "VehicleAwayPeriod",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    OrganizationId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    VehicleId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    LeftOn = table.Column<DateOnly>(type: "date", nullable: false),
                    ReturnedOn = table.Column<DateOnly>(type: "date", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_VehicleAwayPeriod", x => new { x.OrganizationId, x.Id });
                    table.ForeignKey(
                        name: "FK_VehicleAwayPeriod_FleetVehicle_OrganizationId_VehicleId",
                        columns: x => new { x.OrganizationId, x.VehicleId },
                        principalTable: "FleetVehicle",
                        principalColumns: new[] { "OrganizationId", "Id" },
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_VehicleAwayPeriod_Organizations_OrganizationId",
                        column: x => x.OrganizationId,
                        principalTable: "Organizations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_VehicleAwayPeriod_OrganizationId_VehicleId_LeftOn",
                table: "VehicleAwayPeriod",
                columns: new[] { "OrganizationId", "VehicleId", "LeftOn" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "VehicleAwayPeriod");
        }
    }
}
