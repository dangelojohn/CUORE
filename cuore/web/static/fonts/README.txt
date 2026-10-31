Marque web fonts (owner-approved drops; nothing here is fetched automatically).

cuore.css defines --display and --numerals per data-marque and base.html links
fonts/fonts.css ONLY when that file exists. Until then the tokens fall through to
the system stacks and nothing on the pages changes.

INSTALLED 2026-10-29 with the owner's approval ("download the fonts"): the seven
files below were fetched from github.com/google/fonts (commit main of that day),
checked as TrueType, and fonts.css (from fonts.css.template) is now linked by
base.html and m_base.html. Each family's OFL.txt is kept here as OFL-<family>.txt.
To turn the fonts off, delete or rename fonts.css and restart.

Open-licence stand-ins chosen in docs/design/ALFA_TYPOGRAPHY.md (all SIL OFL,
from github.com/google/fonts; copy each family's OFL.txt next to its files):
  alfa      display  Jost-VF.ttf            (ofl/jost/Jost[wght].ttf, renamed; 135 KB)
            numerals BarlowCondensed-Regular.ttf (102 KB), BarlowCondensed-Bold.ttf (110 KB)
  ferrari   display  Saira-VF.ttf           (ofl/saira/Saira[wdth,wght].ttf, renamed; 484 KB)
            numerals TitilliumWeb-Regular.ttf (64 KB), TitilliumWeb-Bold.ttf (60 KB)
  maserati  display  Jost-VF.ttf (weight 300 headings). EBGaramond-VF.ttf is kept on disk but no longer referenced (retired 2026-10-31).
            numerals Jost-VF.ttf (shared)

These are stand-ins. The manufacturers' own typefaces (Alfa Romeo: Apex New per
the 2015 brand guidelines, to be confirmed from the document) replace them when
the brand packages and their licences arrive; the token names stay the same.
