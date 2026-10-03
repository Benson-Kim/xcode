using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AccessIntegrity : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateIndex(
                name: "IX_PersonRoles_OrganizationId_UserId",
                table: "PersonRoles",
                columns: new[] { "OrganizationId", "UserId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Memberships_UserId_Active",
                table: "Memberships",
                column: "UserId",
                unique: true,
                filter: "[Active] = 1");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_PersonRoles_OrganizationId_UserId",
                table: "PersonRoles");

            migrationBuilder.DropIndex(
                name: "IX_Memberships_UserId_Active",
                table: "Memberships");
        }
    }
}
