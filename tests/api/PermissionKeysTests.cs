using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.RegularExpressions;
using Auth.Application;
using Auth.Application.Revenue;
using Auth.Domain;
using Xunit;

namespace Auth.Tests;

// The server owns permission keys and revenue statuses; the TS package mirrors them. These fail when the two drift.
public sealed class PermissionKeysTests
{
    private static IReadOnlyList<string> Quoted(string text) =>
        Regex.Matches(text, "\"([^\"]+)\"").Select(x => x.Groups[1].Value).ToArray();

    private static string Between(string text, string start, string end)
    {
        var from = text.IndexOf(start, StringComparison.Ordinal);
        Assert.True(from >= 0, $"'{start}' not found.");
        from += start.Length;
        var to = text.IndexOf(end, from, StringComparison.Ordinal);
        Assert.True(to >= 0, $"'{end}' not found after '{start}'.");
        return text[from..to];
    }

    [Fact]
    public void EveryConstantIsInTheCatalogAndEveryCatalogKeyHasAConstant()
    {
        var constants = typeof(PermissionKeys).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(x => x.IsLiteral).Select(x => (string)x.GetRawConstantValue()!).ToArray();
        Assert.Equal(constants.Length, constants.Distinct().Count());
        Assert.Equal(PermissionCatalog.All.Order(), constants.Order());
    }

    [Fact]
    public void TheSharedKeyListMatchesTheCatalog()
    {
        var keys = Quoted(Between(RepoFile.Read("packages/shared/src/permissions.ts"), "export const PERMISSION_KEYS = [", "] as const;"));
        var expected = string.Join(Environment.NewLine, PermissionCatalog.All.Select(x => $"  \"{x}\","));
        Assert.True(PermissionCatalog.All.SequenceEqual(keys),
            $"packages/shared/src/permissions.ts PERMISSION_KEYS differs from PermissionCatalog. Expected:{Environment.NewLine}{expected}");
    }

    [Fact]
    public void DependenciesNameOnlyCatalogKeys()
    {
        foreach (var key in PermissionCatalog.All)
            Assert.All(PermissionDependencies.DirectFor(key), x => Assert.Contains(x, PermissionCatalog.All));
        Assert.All(PermissionCatalog.RolePermissions.Values.SelectMany(x => x), x => Assert.Contains(x, PermissionCatalog.All));
    }

    [Fact]
    public void ARefusalNamesAKeyTheCatalogDoesNotLabel()
    {
        Assert.Equal("Doing that needs the permission \"no.such_key\".", PermissionCatalog.Refusal("Doing that", "no.such_key").Message);
        Assert.Equal("Doing that needs the permission \"Capture revenue\".", PermissionCatalog.Refusal("Doing that", PermissionKeys.RevenueCapture).Message);
    }

    [Fact]
    public void CellStatusesKeepTheirWireValues()
    {
        Assert.Equal("[\"none\",\"future\",\"missing\",\"amount\",\"reason\"]", JsonSerializer.Serialize(Enum.GetValues<CellStatus>()));
        Assert.Equal(CellStatus.Missing, JsonSerializer.Deserialize<CellStatus>("\"missing\""));
    }

    [Fact]
    public void CellStatusesMatchTheClients()
    {
        var statuses = Quoted(Between(RepoFile.Read("packages/shared/src/revenue.ts"), "export const REVENUE_STATUSES = [", "] as const"));
        Assert.Equal(Enum.GetValues<CellStatus>().Select(x => JsonSerializer.Serialize(x).Trim('"')), statuses);
    }
}

internal static class RepoFile
{
    // Builds with --artifacts-path run outside the repository, so the source file's own path is tried first.
    public static string Read(string relative, [CallerFilePath] string caller = "")
    {
        foreach (var start in new[] { Path.GetDirectoryName(caller), AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
            for (var dir = string.IsNullOrEmpty(start) ? null : new DirectoryInfo(start); dir is not null; dir = dir.Parent)
                if (File.Exists(Path.Combine(dir.FullName, relative)))
                    return File.ReadAllText(Path.Combine(dir.FullName, relative));
        throw new FileNotFoundException($"{relative} was not found above the test project.");
    }
}
