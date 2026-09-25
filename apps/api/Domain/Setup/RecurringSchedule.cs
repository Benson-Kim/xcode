namespace Auth.Domain.Setup;

public enum RecurrenceFrequency
{
     Daily = 1,
     Weekly = 2,
     Monthly = 3
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
     public RecurringSchedule(RecurrenceFrequency frequency, int? day = null, bool lastDay = false)
     {
          if (!Enum.IsDefined(frequency) ||
              (frequency == RecurrenceFrequency.Daily && (day is not null || lastDay)) ||
              (frequency == RecurrenceFrequency.Weekly && (day is null or < 0 or > 6 || lastDay)) ||
              (frequency == RecurrenceFrequency.Monthly && (lastDay ? day is not null : day is null or < 1 or > 28)))
               throw new ArgumentException("Choose daily, a weekday (0–6), or a month day (1–28 / last).");
          (Frequency, Day, LastDay) = (frequency, day, lastDay);
     }
     public bool IsDue(DateOnly date) => Frequency switch
     {
          RecurrenceFrequency.Daily => true,
          RecurrenceFrequency.Weekly => (int)date.DayOfWeek == Day,
          RecurrenceFrequency.Monthly => date.Day == (LastDay ? DateTime.DaysInMonth(date.Year, date.Month) : Day),
          _ => false
     };
}

