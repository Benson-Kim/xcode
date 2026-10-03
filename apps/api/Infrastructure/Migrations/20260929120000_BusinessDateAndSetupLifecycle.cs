using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class BusinessDateAndSetupLifecycle : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateOnly>(
                name: "BusinessDate",
                table: "Organizations",
                type: "date",
                nullable: true);

            migrationBuilder.AddColumn<DateOnly>(
                name: "ArchivedOn",
                table: "PsvCompany",
                type: "date",
                nullable: true);

            migrationBuilder.AddColumn<DateOnly>(
                name: "LeftOn",
                table: "FleetVehicle",
                type: "date",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "BusinessDate",
                table: "Organizations");

            migrationBuilder.DropColumn(
                name: "ArchivedOn",
                table: "PsvCompany");

            migrationBuilder.DropColumn(
                name: "LeftOn",
                table: "FleetVehicle");
        }
    }
}
