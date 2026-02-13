export function useI18n(_options?: { useScope?: 'global' | 'local' }) {
  const locale = useState<string>('app-locale', () => 'en')

  const t = (key: string) => key
  const n = (value: number) => value

  return {
    locale,
    t,
    n,
  }
}
