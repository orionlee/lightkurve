import logging

import lightkurve as lk

log = logging.getLogger(__name__)


async def get_tpf(tic, sector, msg_label):
    cutout_size = None
    sr = lk.search_targetpixelfile(f"TIC{tic}", mission="TESS", sector=sector)
    if len(sr) > 1:
        # exclude fast cadence data (20s), TPFs with fast cadence always has 2 min cadence counterparts
        # for the use case here, the fast cadence data is irrelevant. It'd just make the processing slower.
        sr = sr[sr.exptime > 60 *u.s]
    if len(sr) < 1:
        log.debug(f"No TPF found for {msg_label}. Use TessCut.")
        cutout_size = (11, 11)  # OPEN: would be too small for bright stars
        sr = lk.search_tesscut(f"TIC{tic}", sector=sector)
    if len(sr) < 1:
        return None, sr

    tpf = sr[-1].download(cutout_size=cutout_size)
    return tpf, sr


def is_tesscut(tpf):
    return "astrocut" == tpf.meta.get('CREATOR')
