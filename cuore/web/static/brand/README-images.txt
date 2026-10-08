Hero images for the vehicle strip (_vbar.html)
================================================

Drop owner-supplied car photos in this folder, named after the model
(last word of the vehicle's name, lowercased):

    stelvio.jpg
    giulia.jpg
    levante.jpg
    grecale.jpg
    purosangue.jpg

Not shipped in the repo -- these are the owner's own photos. The hero
band degrades cleanly when a file is missing: it's a CSS
background-image, not an <img>, so a missing file just leaves the
flat --surface-2 panel showing instead of a broken-image icon.

Suggested shot: wide, car filling the frame, darker exposure reads
better under the white hero-text overlay used at the bottom of the
band. Roughly 1600x700 or wider is plenty; anything will be cropped to
cover a ~176px-tall band (120px on narrow screens).
