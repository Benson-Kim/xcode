const MAX_ENTRIES = 200;

export function remember<K, V>(cache: Map<K, V>, key: K, create: () => V): V {
  if (cache.has(key)) return cache.get(key) as V;
  const value = create();
  if (cache.size >= MAX_ENTRIES) cache.clear();
  cache.set(key, value);
  return value;
}

const dateTimeFormats = new Map<string, Intl.DateTimeFormat>();
const numberFormats = new Map<string, Intl.NumberFormat>();

export const dateTimeFormat = (
  locale: string,
  variant: string,
  timeZone: string | undefined,
  options: Intl.DateTimeFormatOptions,
) =>
  remember(
    dateTimeFormats,
    `${locale}|${timeZone ?? ""}|${variant}`,
    () => new Intl.DateTimeFormat(locale, { ...options, timeZone }),
  );

export const numberFormat = (
  locale: string,
  minimumFractionDigits: number,
  maximumFractionDigits: number,
  useGrouping: boolean,
) =>
  remember(
    numberFormats,
    `${locale}|${minimumFractionDigits}|${maximumFractionDigits}|${useGrouping}`,
    () =>
      new Intl.NumberFormat(locale, {
        minimumFractionDigits,
        maximumFractionDigits,
        useGrouping,
      }),
  );
