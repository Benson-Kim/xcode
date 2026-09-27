using System.Text.RegularExpressions;

namespace Auth.Domain;

public static class PhoneNumber
{
     public static string Normalize(string value)
     {
          var digits = Regex.Replace(value ?? "", @"[\s()+-]", "");
          if (Regex.IsMatch(digits, @"^0[17][0-9]{8}$")) return "+254" + digits[1..];
          if (Regex.IsMatch(digits, @"^254[17][0-9]{8}$")) return "+" + digits;
          return "";
     }
}