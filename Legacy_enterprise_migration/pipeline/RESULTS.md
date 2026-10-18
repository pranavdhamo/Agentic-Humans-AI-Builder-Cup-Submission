# Migration pipeline results

| Run | Program | Model | Mode | Test suite | First attempt (records identical) | Repairs | Final | Verdict | Tokens in / out | LLM time |
|---|---|---|---|---|---|---|---|---|---|---|
| 20261018-004400 | posttran | gemini-3.8-flash | guided | 3 scenarios | 845/846 | 1 | 846/846 | **PASS** | 29,179 / 9,474 | 6.5 min |
| 20261018-015342 | intcalc | gemini-3.8-flash | guided | 5 scenarios | 311/311 | 0 | 311/311 | **PASS** | 13,401 / 5,088 | 5.2 min |
| 20261018-085517 | intcalc | gemini-3.8-flash | naive | 5 scenarios | 311/311 | 0 | 311/311 | **PASS** | 12,973 / 4,886 | 3.4 min |
| 20261018-003010 | posttran | gemini-3.8-flash | guided | 2 scenarios | 622/731 | 1 | 731/731 | **PASS** | 28,873 / 7,545 | 6.1 min |
| 20261018-003802 | posttran | gemini-3.8-flash | naive | 2 scenarios | 622/731 | 0 | 622/731 | **FAIL** | 14,236 / 3,704 | 4.4 min |

Records identical = records whose every field matches what the REAL COBOL produced, summed over all scenarios. The test suite grew between runs (a stronger scenario was added after the first run exposed a shortcut), so compare rows with the same suite size. The 2-scenario posttran PASS (20261018-003010) was a false pass: it hard-coded a zero filler, and re-scoring that code on the later hidden-state scenario FAILS (5/55 category records wrong). Single runs at low temperature: indicative, not statistics. Token counts are as reported by the API.
