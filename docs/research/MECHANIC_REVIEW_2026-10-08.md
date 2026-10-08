# Mechanic review of the Job screen, 2026-10-08 (verbatim, from a tester with the mechanic's hat on)

Context: the tester clicked the Dossier tab, got "Internal Server Error", and every page returned 500 afterwards; only the Job screen was fully reviewed.

Impressed by: the verdict banner ("UNVERIFIED REPAIR ... Not proof of repair"), the fuel-window flag ("94 % fuel at code set, out of window"), recording the absence of a symptom ("Nothing felt is useful evidence"), and the 12-step flow with verification before release.

Would get it thrown off the shop floor:
1. It crashed and stayed crashed. One tab click took the whole app down.
2. It contradicts itself on one screen: hero says "4 open codes" and UNVERIFIED_REPAIR; step 3 says "no codes read yet; verdict not computed"; step 4 says "no MES log since intake".
3. "(unnamed vehicle)" everywhere; decode the VIN.
4. Touch targets: the symptom picker is a small scrollbox showing six of twelve; wants all twelve as big tappable chips like the conditions chips.
5. The date field is a raw US mm/dd/yyyy input; default "when" to now with one tap to override; the odometer field asks to retype a number the header already shows.
6. Layout bugs: header wordmark overlapped the tagline at the viewed width; the floating "Ask / correct" popup sat on top of the conditions chips, blocking input.
7. Language consistency: step names in Italian, body text in English; pick one per locale.

Verdict: easy to follow, the model is effective, the diagnostic honesty is impressive; would not use it today because of stability, state contradictions and glove-friendliness; would want the fixed version. Offered to review Dossier, Codes, Systems and Report after a restart.

## Second pass (all five tabs, stopwatch mentality), verbatim summary

Core problem: the app is organised around the data, not the mechanic's next move; the same question is answered in three places (Job wizard, Dossier clusters, Codes/Systems evidence); nothing says "do this next". Toll booth: ~70 % of every screen is repeated chrome (wordmark, full hero with KPIs, vehicle bar, tabs, Job step bar even on other tabs); Report paints the VIN three times; Ask/correct panel open by default over form chips.
Priorities: 1 Bench landing screen per car (car decoded, complaint, verdict chip, next 2-3 actions as big checkable items with parts, bulletins, tools inline). 2 Verdict gets a next-action sentence ("Cannot verify: EVAP monitor won't run above ~85 % fuel. Burn fuel into window, then drive cycle. Meanwhile: smoke test (18-030-17)"). 3 Hero shrinks to a one-line ~40 px status strip after the first view; full banner only on Report. 4 Job step bar only on the Job tab. 5 Dossier collapsed by default, one summary line per cluster, remembered, pinned jump bar. 6 Merge Job and Dossier: the 12-step flow is the spine, each step pulls in its dossier card. 7 Systems: graph first, only systems with codes by default, correlation prose behind a disclosure, edge details one tap deep. 8 Codes table: relative dates and session counts, system filter chips matching the clusters, rows link to the cluster; keep the ordering. 9 Chrome bugs: wordmark collides with the tagline; Ask/correct must default closed. 10 Stopwatch test: next action in 0 taps and 0 scrolls; any code, bulletin or freeze frame in <= 2 taps.
