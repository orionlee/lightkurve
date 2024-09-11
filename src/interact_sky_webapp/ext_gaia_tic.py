from typing import Tuple

import astroquery.vizier as vizier

from lightkurve.interact_sky_providers.gaia_tic import GaiaDR3TICInteractSkyCatalogProvider


class ExtendedGaiaDR3TICInteractSkyCatalogProvider(GaiaDR3TICInteractSkyCatalogProvider):
    """Custom extension to standard Gaia DR3 TIC provider."""

    def get_detail_view(self, data: dict) -> Tuple[dict, list]:
        key_vals, extra_rows = super().get_detail_view(data)
        source = data["Source"]
        if source != "":
            # links to Gaia DR3 Stellar Variability catalog (based on photometric dispersions)
            vizier_server = vizier.conf.server
            gaia_dispersions_url = f"https://{vizier_server}/viz-bin/VizieR-4?-source=J%2FA%2BA%2F677%2FA137%2Fcatalog&Source={source}"
            extra_rows.append(f'<a href="{gaia_dispersions_url}" target="_blank">Gaia DR3 Stellar Variability</a> [2023A&A...677A.137M]')

        return key_vals, extra_rows
