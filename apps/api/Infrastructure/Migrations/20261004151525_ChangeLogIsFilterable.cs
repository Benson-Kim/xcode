using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class ChangeLogIsFilterable : Migration
    {
        // The change log can now be narrowed by date, which means comparing its instants inside the query. Both of
        // them are UTC already - OrganizationSettingsVersion refuses any other offset - so they are stored as plain
        // UTC datetimes, which every provider XCODE runs on can compare; a datetimeoffset cannot be compared in
        // SQLite at all. Nothing is lost: the offset dropped here was always zero, and Down puts it back as zero.
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<DateTime>(
                name: "OccurredAt",
                table: "OrganizationSettingsVersion",
                type: "datetime2",
                nullable: false,
                oldClrType: typeof(DateTimeOffset),
                oldType: "datetimeoffset");

            migrationBuilder.AlterColumn<DateTime>(
                name: "EffectiveFrom",
                table: "OrganizationSettingsVersion",
                type: "datetime2",
                nullable: true,
                oldClrType: typeof(DateTimeOffset),
                oldType: "datetimeoffset",
                oldNullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<DateTimeOffset>(
                name: "OccurredAt",
                table: "OrganizationSettingsVersion",
                type: "datetimeoffset",
                nullable: false,
                oldClrType: typeof(DateTime),
                oldType: "datetime2");

            migrationBuilder.AlterColumn<DateTimeOffset>(
                name: "EffectiveFrom",
                table: "OrganizationSettingsVersion",
                type: "datetimeoffset",
                nullable: true,
                oldClrType: typeof(DateTime),
                oldType: "datetime2",
                oldNullable: true);
        }
    }
}
