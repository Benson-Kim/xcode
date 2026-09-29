using System.Net.Http.Json;
using Auth.Application.Setup;

namespace Auth.Tests;

// Scheduled costs name an expense item. Tests take one from the demo catalog, adding it under "Charges" when the
// design's catalog has no item of that name.
public static class ExpenseItemTestData
{
    public static async Task<Guid> Id(HttpClient client, string name)
    {
        var options = (await client.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))!;
        if (options.FirstOrDefault(x => x.Name == name) is { } found)
            return found.Id;
        var charges = options.First(x => x.CategoryName == "Charges").CategoryId;
        using var created = await client.PostAsJsonAsync($"/setup/expense-categories/{charges}/items", new { name });
        created.EnsureSuccessStatusCode();
        return (await created.Content.ReadFromJsonAsync<Created>())!.Id;
    }

    private sealed record Created(Guid Id);
}
