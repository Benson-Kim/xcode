using Auth.Infrastructure;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Auth.Tests;

public sealed class EmailSenderTests
{
    [Theory]
    [InlineData("127.0.0.1", "false", false)]
    [InlineData("localhost", "false", false)]
    [InlineData("::1", "false", false)]
    [InlineData("smtp.example.com", "false", true)]
    [InlineData("10.0.0.5", "false", true)]
    [InlineData("127.0.0.1", null, true)]
    [InlineData("smtp.example.com", null, true)]
    public void MailIsEncryptedUnlessTurnedOffForARelayOnThisMachine(string host, string? enableSsl, bool encrypted)
    {
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["Email:Host"] = host, ["Email:EnableSsl"] = enableSsl })
            .Build();
        Assert.Equal(encrypted, SmtpEmailSender.UsesTls(config));
    }
}
