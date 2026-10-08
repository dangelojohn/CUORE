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
