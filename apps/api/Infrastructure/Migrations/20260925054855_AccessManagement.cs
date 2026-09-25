using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AccessManagement : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_SetupCompanyScope_Memberships_OrganizationId_UserId",
                table: "SetupCompanyScope");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupCompanyScope_Organizations_OrganizationId",
                table: "SetupCompanyScope");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupCompanyScope_PsvCompany_OrganizationId_CompanyId",
                table: "SetupCompanyScope");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupDataScope_Memberships_OrganizationId_UserId",
                table: "SetupDataScope");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupDataScope_Organizations_OrganizationId",
                table: "SetupDataScope");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupVehicleScope_FleetVehicle_OrganizationId_VehicleId",
                table: "SetupVehicleScope");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupVehicleScope_Memberships_OrganizationId_UserId",
                table: "SetupVehicleScope");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupVehicleScope_Organizations_OrganizationId",
                table: "SetupVehicleScope");

            migrationBuilder.DropPrimaryKey(
                name: "PK_SetupVehicleScope",
                table: "SetupVehicleScope");

            migrationBuilder.DropPrimaryKey(
                name: "PK_SetupDataScope",
                table: "SetupDataScope");

            migrationBuilder.DropPrimaryKey(
                name: "PK_SetupCompanyScope",
                table: "SetupCompanyScope");

            migrationBuilder.RenameTable(
                name: "SetupVehicleScope",
                newName: "SetupVehicleScopes");

            migrationBuilder.RenameTable(
                name: "SetupDataScope",
                newName: "SetupDataScopes");

            migrationBuilder.RenameTable(
                name: "SetupCompanyScope",
                newName: "SetupCompanyScopes");

            migrationBuilder.RenameIndex(
                name: "IX_SetupVehicleScope_OrganizationId_VehicleId",
                table: "SetupVehicleScopes",
                newName: "IX_SetupVehicleScopes_OrganizationId_VehicleId");

            migrationBuilder.RenameIndex(
                name: "IX_SetupCompanyScope_OrganizationId_CompanyId",
                table: "SetupCompanyScopes",
                newName: "IX_SetupCompanyScopes_OrganizationId_CompanyId");

            migrationBuilder.AddColumn<decimal>(
                name: "ApprovalLimit",
                table: "Memberships",
                type: "decimal(14,2)",
                precision: 14,
                scale: 2,
                nullable: true);

            migrationBuilder.AddPrimaryKey(
                name: "PK_SetupVehicleScopes",
                table: "SetupVehicleScopes",
                columns: new[] { "OrganizationId", "UserId", "VehicleId" });

            migrationBuilder.AddPrimaryKey(
                name: "PK_SetupDataScopes",
                table: "SetupDataScopes",
                columns: new[] { "OrganizationId", "UserId" });

            migrationBuilder.AddPrimaryKey(
                name: "PK_SetupCompanyScopes",
                table: "SetupCompanyScopes",
                columns: new[] { "OrganizationId", "UserId", "CompanyId" });

            migrationBuilder.AddForeignKey(
                name: "FK_SetupCompanyScopes_Memberships_OrganizationId_UserId",
                table: "SetupCompanyScopes",
                columns: new[] { "OrganizationId", "UserId" },
                principalTable: "Memberships",
                principalColumns: new[] { "OrganizationId", "UserId" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupCompanyScopes_Organizations_OrganizationId",
                table: "SetupCompanyScopes",
                column: "OrganizationId",
                principalTable: "Organizations",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupCompanyScopes_PsvCompany_OrganizationId_CompanyId",
                table: "SetupCompanyScopes",
                columns: new[] { "OrganizationId", "CompanyId" },
                principalTable: "PsvCompany",
                principalColumns: new[] { "OrganizationId", "Id" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupDataScopes_Memberships_OrganizationId_UserId",
                table: "SetupDataScopes",
                columns: new[] { "OrganizationId", "UserId" },
                principalTable: "Memberships",
                principalColumns: new[] { "OrganizationId", "UserId" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupDataScopes_Organizations_OrganizationId",
                table: "SetupDataScopes",
                column: "OrganizationId",
                principalTable: "Organizations",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupVehicleScopes_FleetVehicle_OrganizationId_VehicleId",
                table: "SetupVehicleScopes",
                columns: new[] { "OrganizationId", "VehicleId" },
                principalTable: "FleetVehicle",
                principalColumns: new[] { "OrganizationId", "Id" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupVehicleScopes_Memberships_OrganizationId_UserId",
                table: "SetupVehicleScopes",
                columns: new[] { "OrganizationId", "UserId" },
                principalTable: "Memberships",
                principalColumns: new[] { "OrganizationId", "UserId" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupVehicleScopes_Organizations_OrganizationId",
                table: "SetupVehicleScopes",
                column: "OrganizationId",
                principalTable: "Organizations",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_SetupCompanyScopes_Memberships_OrganizationId_UserId",
                table: "SetupCompanyScopes");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupCompanyScopes_Organizations_OrganizationId",
                table: "SetupCompanyScopes");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupCompanyScopes_PsvCompany_OrganizationId_CompanyId",
                table: "SetupCompanyScopes");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupDataScopes_Memberships_OrganizationId_UserId",
                table: "SetupDataScopes");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupDataScopes_Organizations_OrganizationId",
                table: "SetupDataScopes");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupVehicleScopes_FleetVehicle_OrganizationId_VehicleId",
                table: "SetupVehicleScopes");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupVehicleScopes_Memberships_OrganizationId_UserId",
                table: "SetupVehicleScopes");

            migrationBuilder.DropForeignKey(
                name: "FK_SetupVehicleScopes_Organizations_OrganizationId",
                table: "SetupVehicleScopes");

            migrationBuilder.DropPrimaryKey(
                name: "PK_SetupVehicleScopes",
                table: "SetupVehicleScopes");

            migrationBuilder.DropPrimaryKey(
                name: "PK_SetupDataScopes",
                table: "SetupDataScopes");

            migrationBuilder.DropPrimaryKey(
                name: "PK_SetupCompanyScopes",
                table: "SetupCompanyScopes");

            migrationBuilder.DropColumn(
                name: "ApprovalLimit",
                table: "Memberships");

            migrationBuilder.RenameTable(
                name: "SetupVehicleScopes",
                newName: "SetupVehicleScope");

            migrationBuilder.RenameTable(
                name: "SetupDataScopes",
                newName: "SetupDataScope");

            migrationBuilder.RenameTable(
                name: "SetupCompanyScopes",
                newName: "SetupCompanyScope");

            migrationBuilder.RenameIndex(
                name: "IX_SetupVehicleScopes_OrganizationId_VehicleId",
                table: "SetupVehicleScope",
                newName: "IX_SetupVehicleScope_OrganizationId_VehicleId");

            migrationBuilder.RenameIndex(
                name: "IX_SetupCompanyScopes_OrganizationId_CompanyId",
                table: "SetupCompanyScope",
                newName: "IX_SetupCompanyScope_OrganizationId_CompanyId");

            migrationBuilder.AddPrimaryKey(
                name: "PK_SetupVehicleScope",
                table: "SetupVehicleScope",
                columns: new[] { "OrganizationId", "UserId", "VehicleId" });

            migrationBuilder.AddPrimaryKey(
                name: "PK_SetupDataScope",
                table: "SetupDataScope",
                columns: new[] { "OrganizationId", "UserId" });

            migrationBuilder.AddPrimaryKey(
                name: "PK_SetupCompanyScope",
                table: "SetupCompanyScope",
                columns: new[] { "OrganizationId", "UserId", "CompanyId" });

            migrationBuilder.AddForeignKey(
                name: "FK_SetupCompanyScope_Memberships_OrganizationId_UserId",
                table: "SetupCompanyScope",
                columns: new[] { "OrganizationId", "UserId" },
                principalTable: "Memberships",
                principalColumns: new[] { "OrganizationId", "UserId" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupCompanyScope_Organizations_OrganizationId",
                table: "SetupCompanyScope",
                column: "OrganizationId",
                principalTable: "Organizations",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupCompanyScope_PsvCompany_OrganizationId_CompanyId",
                table: "SetupCompanyScope",
                columns: new[] { "OrganizationId", "CompanyId" },
                principalTable: "PsvCompany",
                principalColumns: new[] { "OrganizationId", "Id" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupDataScope_Memberships_OrganizationId_UserId",
                table: "SetupDataScope",
                columns: new[] { "OrganizationId", "UserId" },
                principalTable: "Memberships",
                principalColumns: new[] { "OrganizationId", "UserId" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupDataScope_Organizations_OrganizationId",
                table: "SetupDataScope",
                column: "OrganizationId",
                principalTable: "Organizations",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupVehicleScope_FleetVehicle_OrganizationId_VehicleId",
                table: "SetupVehicleScope",
                columns: new[] { "OrganizationId", "VehicleId" },
                principalTable: "FleetVehicle",
                principalColumns: new[] { "OrganizationId", "Id" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupVehicleScope_Memberships_OrganizationId_UserId",
                table: "SetupVehicleScope",
                columns: new[] { "OrganizationId", "UserId" },
                principalTable: "Memberships",
                principalColumns: new[] { "OrganizationId", "UserId" },
                onDelete: ReferentialAction.Restrict);

            migrationBuilder.AddForeignKey(
                name: "FK_SetupVehicleScope_Organizations_OrganizationId",
                table: "SetupVehicleScope",
                column: "OrganizationId",
                principalTable: "Organizations",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);
        }
    }
}
