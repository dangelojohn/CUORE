Marque web fonts (owner-approved drops; nothing here is fetched automatically).

cuore.css defines --display and --numerals per data-marque and base.html links
fonts/fonts.css ONLY when that file exists. Until then the tokens fall through to
the system stacks and nothing on the pages changes.

To switch the fonts on:
  1. Put the approved font files in this folder (names below).
  2. Rename fonts.css.template to fonts.css (edit it if a file name differs).
  3. Restart CUORE. No code change needed.

Open-licence stand-ins chosen in docs/design/ALFA_TYPOGRAPHY.md (all SIL OFL,
from github.com/google/fonts; copy each family's OFL.txt next to its files):
  alfa      display  Jost-VF.ttf            (ofl/jost/Jost[wght].ttf, renamed; 135 KB)
            numerals BarlowCondensed-Regular.ttf (102 KB), BarlowCondensed-Bold.ttf (110 KB)
  ferrari   display  Saira-VF.ttf           (ofl/saira/Saira[wdth,wght].ttf, renamed; 484 KB)
            numerals TitilliumWeb-Regular.ttf (64 KB), TitilliumWeb-Bold.ttf (60 KB)
  maserati  display  EBGaramond-VF.ttf      (ofl/ebgaramond/EBGaramond[wght].ttf, renamed; 851 KB)
            numerals Jost-VF.ttf (shared)

These are stand-ins. The manufacturers' own typefaces (Alfa Romeo: Apex New per
the 2015 brand guidelines, to be confirmed from the document) replace them when
the brand packages and their licences arrive; the token names stay the same.
