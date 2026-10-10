# data/raw — put real source files here (they are not uploaded to GitHub)

This folder is empty in the offline build. Files here are ignored by git because they are large.
Expected names (see docs/DATA.md for the source of each):

    megt44n045hb.lbl  megt44n045hb.img      MOLA topography (or run scripts/fetch_mola.py with internet)
    megc44n045hb.lbl  megc44n045hb.img      MOLA shot counts
    ctx/M20_JezeroCrater_CTXDEM_20m.tif     CTX DEM (not integrated yet)
    ctx/M20_JezeroCrater_CTXortho_mosaic_5m.tif
    m20/M20_traverse.json                   Perseverance traverse (read automatically)
    m20/M20_waypoints.json
    crism/jezeroFinal.tif + its readme      (not integrated yet)
    meda/  data files + .xml labels         (not integrated yet)

Check what is present:  python scripts/check_local_data.py
Then rebuild:           python run.py --rebuild
