using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

#pragma warning disable CA1814 // Prefer jagged arrays over multidimensional

namespace Auth.Api.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class RetireOldCostCategories : Migration
    {
        // The four Phase 1 cost categories are retired: every cost names an expense item and carries that item's
        // bucket, which the expense-catalog migration backfilled for the versions saved before it, so nothing a
        // version reports under changes here. Down restores the column, its index, the lookup table and its rows;
        // the categories themselves cannot come back, because dropping the column is what loses them.
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_RecurringVersion_CostCategoryLookup_Category",
                table: "RecurringVersion");

            migrationBuilder.DropTable(
                name: "CostCategoryLookup");

            migrationBuilder.DropIndex(
                name: "IX_RecurringVersion_Category",
                table: "RecurringVersion");

            migrationBuilder.DropColumn(
                name: "Category",
                table: "RecurringVersion");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "Category",
                table: "RecurringVersion",
                type: "int",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "CostCategoryLookup",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false),
                    Name = table.Column<string>(type: "nvarchar(max)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CostCategoryLookup", x => x.Id);
                });

            migrationBuilder.InsertData(
                table: "CostCategoryLookup",
                columns: new[] { "Id", "Name" },
                values: new object[,]
                {
                    { 1, "RunningCosts" },
                    { 2, "RepairsAndUpkeep" },
                    { 3, "CrewCosts" },
                    { 4, "FixedCommitments" }
                });

            migrationBuilder.CreateIndex(
                name: "IX_RecurringVersion_Category",
                table: "RecurringVersion",
                column: "Category");

            migrationBuilder.AddForeignKey(
                name: "FK_RecurringVersion_CostCategoryLookup_Category",
                table: "RecurringVersion",
                column: "Category",
                principalTable: "CostCategoryLookup",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);
        }
    }
}
