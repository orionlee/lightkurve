from typing import Union
import warnings

import astropy.units as u

from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time

from astroquery.vizier import Vizier

import numpy as np

from .interact_sky_provider import ProperMotionCorrectionMeta


class GaiaDR3InteractSkyCatalogProvider:

    # query: generic
    coord: SkyCoord
    radius: Union[float, u.Quantity]
    magnitude_limit: float
    # for plotting
    scatter_kwargs: dict

    # Vizier-specific
    catalog_name = "I/355/gaiadr3"
    columns = ["*", "RAJ2000", "DEJ2000"]
    magnitude_limit_column_name = "Gmag"

    J2000 = Time(2000, format="jyear", scale="tt")

    def init(
        self,
        coord: SkyCoord,
        radius: Union[float, u.Quantity],
        magnitude_limit: float,
        scatter_kwargs: dict = None,
    ) -> None:
        self.coord = coord
        self.radius = radius
        self.magnitude_limit = magnitude_limit
        if scatter_kwargs is not None:
            self.scatter_kwargs = scatter_kwargs
        else:
            self.scatter_kwargs = dict(
                marker="circle",
                fill_alpha=0.3,
                line_color=None,
                selection_color="firebrick",
                nonselection_fill_alpha=0.3,
                nonselection_line_color=None,
                nonselection_line_alpha=1.0,
                fill_color="firebrick",
                hover_fill_color="firebrick",
                hover_alpha=0.9,
                hover_line_color="white",
            )

    def query_catalog(self) -> Table:
        with warnings.catch_warnings():
            # suppress useless warning to workaround  https://github.com/astropy/astroquery/issues/2352
            warnings.filterwarnings("ignore", category=u.UnitsWarning, message="Unit 'e' not supported by the VOUnit standard")
            vizier = Vizier(
                columns=self.columns,
            )
            vizier.ROW_LIMIT = -1
            result = vizier.query_region(
                self.coord,
                catalog=self.catalog_name,
                radius=self.radius,
            )
        no_targets_found_message = ValueError("Either no sources were found in the query region " "or Vizier is unavailable")
        too_few_found_message = ValueError("No sources found brighter than {:0.1f}".format(self.magnitude_limit))
        if result is None:
            raise no_targets_found_message
        elif len(result) == 0:
            raise too_few_found_message
        result = result[self.catalog_name]
        result = result[result[self.magnitude_limit_column_name] < self.magnitude_limit]
        if len(result) == 0:
            raise no_targets_found_message

        # to be used as the basis for sizing the dots in plots
        result["magForSize"] = result[self.magnitude_limit_column_name]

        return result

    def get_proper_motion_correction_meta(self) -> ProperMotionCorrectionMeta:
        return ProperMotionCorrectionMeta("RAJ2000", "DEJ2000", "pmRA", "pmDE", self.J2000)

    def add_to_data_source(self, result: Table, source: dict):
        more_data = dict()
        for col in [  # the additional columns to be included in the data source
            "Source",
            "Gmag",
            "Plx",
            # TODO:
        ]:
            # bokeh ColumnDataSource-specific workaround
            # convert column with large integers to string, to avoid
            # BokehUserWarning: out of range integer may result in loss of precision
            # TODO: make it more generic, and explain why we do not do it for all np.int64 type columns
            col_val = result[col]
            if col in ["Source"]:
                col_val = col_val.astype(str)
            more_data[col] = col_val
        more_data["one_over_plx"] = 1.0 / (result["Plx"] / 1000.0)
        source.update(more_data)

    def get_tooltips(self) -> list:
        return [
            ("Gaia Source", "@Source"),
            ('Separation (")', "@separation{0.00}"),
            ("Gmag", "@Gmag"),
            ("Parallax (mas)", "@Plx (~@one_over_plx{0,0} pc)"),
            ("RA", "@ra{0,0.00000000}"),
            ("DEC", "@dec{0,0.00000000}"),
            ("column", "@x{0.0}"),
            ("row", "@y{0.0}"),
        ]

    def get_detail_view(self, data: dict) -> dict:
        # the vizier URL returns both Gaia DR3 Main and Gaia DR3 Astrophysical parameters table for convenience
        vizier_url = (
            "https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=+I%2F355%2Fgaiadr3+I%2F355%2Fparamp"
            f"&Source={data['Source']}"
        )
        simbad_url_by_gaia_source = f"https://simbad.u-strasbg.fr/simbad/sim-id?Ident=Gaia DR3 {data['Source']}"
        simbad_url_by_coord = (
            f"https://simbad.u-strasbg.fr/simbad/sim-coo?Coord={data['ra']}+{data['dec']}&Radius=2&Radius.unit=arcmin"
        )
        return {
            "Source": f"""{data['Source']} (<a href="{vizier_url}" target="_blank">Vizier</a>)""",
            'Separation (")': f"{data['separation']:.2f}",
            "Gmag": f"{data['Gmag']:.3f}",
            "Parallax (mas)": f"{data['Plx']:.3f} (~ {data['one_over_plx']:,.0f} pc)",
            "RA": f"{data['ra']:.8f}",
            "DEC": f"{data['dec']:.8f}",
            "column": f"{data['x']:.1f}",
            "row": f"{data['y']:.1f}",
        }, [
            f'<a target="_blank" href="{simbad_url_by_gaia_source}">SIMBAD by Gaia Source</a>',
            f'<a target="_blank" href="{simbad_url_by_coord}">SIMBAD by coordinate</a>',
        ]
