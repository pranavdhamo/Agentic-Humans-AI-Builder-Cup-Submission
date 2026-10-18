import { describe, expect, it } from 'vitest'
import { duration, num, pct, splitRunId } from './format'

describe('format', () => {
  it('formats percentages', () => {
    expect(pct(845, 846)).toBe('99.9%')
    expect(pct(10, 10)).toBe('100%')
    expect(pct(0, 0)).toBe('-')
  })
  it('formats durations', () => {
    expect(duration(4.26)).toBe('4.3s')
    expect(duration(125)).toBe('2m 5s')
    expect(duration(-1)).toBe('-')
  })
  it('formats numbers', () => {
    expect(num(29179)).toBe('29,179')
    expect(num(null)).toBe('-')
  })
  it('splits run ids', () => {
    expect(splitRunId('results:20261018-004400-posttran')).toEqual(['results', '20261018-004400-posttran'])
  })
})
