using System.Text.RegularExpressions;

namespace Auth.Domain;

public readonly record struct PhoneNumber
{
    private static readonly Regex SubscriberRegex = new(@"^[17][0-9]{8}$", RegexOptions.Compiled);

    public string Value { get; }

    private PhoneNumber(string value) => Value = value;

    public static bool TryCreate(string input, out PhoneNumber result)
    {
        var normalized = Normalize(input);
        if (normalized.Length == 0)
        {
            result = default;
            return false;
        }
        result = new PhoneNumber(normalized);
        return true;
    }

    public static string Normalize(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "";

        var digits = Regex.Replace(value, @"\D", "");

        if (digits.StartsWith("254") && digits.Length == 12)
        {
            var subscriberPart = digits[3..];
            if (SubscriberRegex.IsMatch(subscriberPart))
                return "+" + digits;
        }

        if (digits.StartsWith("0") && digits.Length == 10)
        {
            var subscriberPart = digits[1..];
            if (SubscriberRegex.IsMatch(subscriberPart))
                return "+254" + subscriberPart;
        }

        if (digits.Length == 9 && SubscriberRegex.IsMatch(digits))
            return "+254" + digits;

        return "";
    }

    public override string ToString() => Value;

    public static implicit operator string(PhoneNumber phone) => phone.Value;
}
