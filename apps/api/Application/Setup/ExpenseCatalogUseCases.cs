using Auth.Domain.Setup;

namespace Auth.Application.Setup;

// Expense categories and the items people pick on every expense and every scheduled expense. The catalog is
// organization-wide, so it has no data scope. Reasons are written automatically.
public sealed class ExpenseCatalogUseCases(ISetupExecution execution, ISetupRepository repository, IOrganizationRepository organizations)
{
    private const string Section = "expenses";
    private static readonly string[] CategoryReaders = ["expenses.view", "expenses.setup", "commitments.view"];
    private static readonly string[] OptionReaders = ["expenses.view", "expenses.setup", "commitments.view", "commitments.manage"];

    public Task<Page<ExpenseCategoryDto>> List(int page, int pageSize, CancellationToken ct) => execution.Read("", async actor =>
    {
        await RequireAny(actor, CategoryReaders, ct);
        SetupPagination.Validate(page, pageSize);
        return await repository.ExpenseCategories(actor.Today, page, pageSize, ct);
    }, ct);

    public Task<IReadOnlyList<ExpenseItemOption>> Options(CancellationToken ct) => execution.Read("", async actor =>
    {
        await RequireAny(actor, OptionReaders, ct);
        return await repository.ExpenseItemOptions(actor.Today, ct);
    }, ct);

    public Task<Guid> SaveCategory(Guid? id, SaveExpenseCategory input, CancellationToken ct) => execution.Write("expenses.setup", async actor =>
    {
        var name = SetupValue.Name(input.Name, ExpenseCategory.NameLength);
        var category = id is null ? new ExpenseCategory(actor.OrganizationId, name, input.Bucket)
            : await repository.ExpenseCategory(id.Value, ct) ?? throw new KeyNotFoundException();
        if (await repository.ExpenseCategoryNameExists(actor.OrganizationId, name.ToUpperInvariant(), id, ct))
            throw new ArgumentException("That category already exists.");
        var before = id is null ? null : Snapshot(category);
        var previous = (category.Name, category.Bucket);
        if (id is not null && !category.Change(name, input.Bucket))
            return category.Id;
        if (id is null)
            repository.Add(category);
        var countsAs = ExpenseBuckets.Label(category.Bucket).ToLowerInvariant();
        var reason = id is null ? $"Added expense category {category.Name}"
            : previous.Name == category.Name ? $"Changed {category.Name} to count as {countsAs}"
            : previous.Bucket == category.Bucket ? $"Renamed expense category {previous.Name} to {category.Name}"
            : $"Renamed expense category {previous.Name} to {category.Name}, counted as {countsAs}";
        await repository.RecordChange(actor, Section, category.Id, before, Snapshot(category), reason, ct);
        return category.Id;
    }, ct);

    public Task<Guid> SetCategoryStopped(Guid id, bool stopped, CancellationToken ct) => execution.Write("expenses.setup", async actor =>
    {
        var category = await repository.ExpenseCategory(id, ct) ?? throw new KeyNotFoundException();
        var before = Snapshot(category);
        if (stopped ? category.Stop(actor.Today) : category.Restore())
            await repository.RecordChange(actor, Section, category.Id, before, Snapshot(category),
                $"{(stopped ? "Turned off" : "Turned on")} expense category {category.Name}", ct);
        return category.Id;
    }, ct);

    public Task<Guid> AddItem(Guid categoryId, SaveExpenseItem input, CancellationToken ct) => execution.Write("expenses.setup", async actor =>
    {
        var category = await repository.ExpenseCategory(categoryId, ct) ?? throw new KeyNotFoundException();
        var item = new ExpenseItem(category, input.Name!);
        await EnsureUniqueItem(actor, item.CategoryId, item.Name, null, ct);
        repository.Add(item);
        await repository.RecordChange(actor, Section, item.Id, null, Snapshot(item), $"Added expense item {item.Name} under {category.Name}", ct);
        return item.Id;
    }, ct);

    public Task<Guid> RenameItem(Guid id, SaveExpenseItem input, CancellationToken ct) => execution.Write("expenses.setup", async actor =>
    {
        var name = SetupValue.Name(input.Name, ExpenseCategory.NameLength);
        var item = await repository.ExpenseItem(id, ct) ?? throw new KeyNotFoundException();
        await EnsureUniqueItem(actor, item.CategoryId, name, item.Id, ct);
        var before = Snapshot(item);
        var previous = item.Name;
        if (item.Rename(name))
            await repository.RecordChange(actor, Section, item.Id, before, Snapshot(item), $"Renamed expense item {previous} to {item.Name}", ct);
        return item.Id;
    }, ct);

    public Task<Guid> SetItemStopped(Guid id, bool stopped, CancellationToken ct) => execution.Write("expenses.setup", async actor =>
    {
        var item = await repository.ExpenseItem(id, ct) ?? throw new KeyNotFoundException();
        var before = Snapshot(item);
        if (stopped ? item.Stop(actor.Today) : item.Restore())
            await repository.RecordChange(actor, Section, item.Id, before, Snapshot(item),
                $"{(stopped ? "Turned off" : "Turned on")} expense item {item.Name}", ct);
        return item.Id;
    }, ct);

    // Item names are unique within their category, ignoring case.
    private async Task EnsureUniqueItem(SetupActor actor, Guid categoryId, string name, Guid? except, CancellationToken ct)
    {
        if (await repository.ExpenseItemNameExists(actor.OrganizationId, categoryId, name.ToUpperInvariant(), except, ct))
            throw new ArgumentException("That item already exists in this category.");
    }

    // Reading the catalog takes any one of several permissions, so it is checked here rather than by the pipeline,
    // which already refused anyone who is not an active member.
    private async Task RequireAny(SetupActor actor, string[] permissions, CancellationToken ct)
    {
        var granted = await organizations.Permissions(actor.UserId, ct);
        if (!permissions.Any(granted.Contains))
            throw new UnauthorizedAccessException();
    }

    private static object Snapshot(ExpenseCategory category) => new
    {
        category.Id,
        category.Name,
        category.Bucket,
        category.StoppedOn
    };

    private static object Snapshot(ExpenseItem item) => new
    {
        item.Id,
        item.CategoryId,
        item.Name,
        item.StoppedOn
    };
}
