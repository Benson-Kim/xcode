namespace Auth.Domain.Setup;

public enum RecurrenceFrequency
{
     // Legacy: no longer offered for new saves, but versions saved as daily keep posting.
     Daily = 1,
     Weekly = 2,
     Monthly = 3,
     Yearly = 4
}

public enum RecurringKind
{
     Cost = 1,
     Savings = 2
}


public enum CostCategory
{
     RunningCosts = 1,
     RepairsAndUpkeep = 2,
     CrewCosts = 3,
     FixedCommitments = 4
}

public sealed record RecurringSchedule
{
     public RecurrenceFrequency Frequency { get; }
     public int? Day { get; }
     public bool LastDay { get; }
     // Yearly only: the month (1–12) it falls due in.
     public int? Month { get; }
     public RecurringSchedule(RecurrenceFrequency frequency, int? day = null, bool lastDay = false, int? month = null)
     {
          var monthDay = lastDay ? day is null : day is >= 1 and <= 28;
          if (!Enum.IsDefined(frequency) ||
              (frequency != RecurrenceFrequency.Yearly && month is not null) ||
              (frequency == RecurrenceFrequency.Daily && (day is not null || lastDay)) ||
              (frequency == RecurrenceFrequency.Weekly && (day is null or < 0 or > 6 || lastDay)) ||
              (frequency == RecurrenceFrequency.Monthly && !monthDay) ||
              (frequency == RecurrenceFrequency.Yearly && (month is null or < 1 or > 12 || !monthDay)))
               throw new ArgumentException("Choose a weekday (0–6), a month day (1–28 / last), or for yearly a month (1–12) and a day.");
          (Frequency, Day, LastDay, Month) = (frequency, day, lastDay, month);
     }
     // O(1) for every frequency: a due date is a pure function of the date.
     public bool IsDue(DateOnly date) => Frequency switch
     {
          RecurrenceFrequency.Daily => true,
          RecurrenceFrequency.Weekly => (int)date.DayOfWeek == Day,
          RecurrenceFrequency.Monthly => date.Day == DueDay(date),
          RecurrenceFrequency.Yearly => date.Month == Month && date.Day == DueDay(date),
          _ => false
     };
     // The dates from first through last that IsDue accepts, stepped rather than tested: by 7 days for weekly, one per
     // month or one per year. O(dates returned + 1).
     public IEnumerable<DateOnly> Occurrences(DateOnly first, DateOnly last)
     {
          if (first > last) yield break;
          if (Frequency is RecurrenceFrequency.Daily or RecurrenceFrequency.Weekly)
          {
               var step = Frequency == RecurrenceFrequency.Daily ? 1 : 7;
               var date = Frequency == RecurrenceFrequency.Daily ? first : first.AddDays((Day!.Value - (int)first.DayOfWeek + 7) % 7);
               for (; date <= last; date = date.AddDays(step)) yield return date;
               yield break;
          }
          var months = Frequency == RecurrenceFrequency.Monthly ? 1 : 12;
          for (var month = new DateOnly(first.Year, Frequency == RecurrenceFrequency.Monthly ? first.Month : Month!.Value, 1);
               month <= last; month = month.AddMonths(months))
          {
               var day = DueDay(month)!.Value;
               if (day > DateTime.DaysInMonth(month.Year, month.Month)) continue;
               var date = new DateOnly(month.Year, month.Month, day);
               if (date >= first && date <= last) yield return date;
          }
     }
     private int? DueDay(DateOnly date) => LastDay ? DateTime.DaysInMonth(date.Year, date.Month) : Day;
}

