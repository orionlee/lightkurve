import traceback

import astropy.units as u

import lightkurve as lk
from lightkurve.interact import show_skyview_widget, prepare_lightcurve_datasource, make_lightcurve_figure_elements

from bokeh.layouts import row, column
from bokeh.models import Button, Div, TextInput, Dropdown
from bokeh.plotting import curdoc


# import lines for read_ztf_csv
import re
import warnings
from astropy.time import Time
from astropy.table import Table
import numpy as np


def read_ztf_csv(
    url=None,
    time_column="hjd",
    time_format="jd",
    time_scale="utc",
    flux_column="mag",
    flux_err_column="magerr",
    mask_func=lambda lc: lc["catflags"] != 0,
):
    """Return ZTF Archive lightcurve files in IPAC Table csv.

    Parameters
    ----------
    mask_func : function, optional
        a function that returns a boolean mask given a `Lightcurve` object
        of the data. Cadences with `True` will be masked out.
        Pass `None` to disable masking.
        The default is to exclude cadences where `catflags` is not 0, the
        guideline for VSX submission.
        https://www.aavso.org/vsx/index.php?view=about.notice
    """
    # Note: First tried to read ZTF's ipac table .tbl, but got
    #   TypeError: converter type does not match column type
    # due to: https://github.com/astropy/astropy/issues/15989

    def get_required_column(tab, colname):
        if colname not in tab.colnames:
            raise ValueError(f"Required column {colname} is not found")
        return tab[colname]

    def filter_rows_with_invalid_time(tab, colname):
        # Some times the time value is nan for unknown reason. E.g.,
        # https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves?ID=848110200002484&COLLECTION=ztf_dr20&FORMAT=csv
        # some hjd values are nan, even though there is mjd value
        filtered = tab[np.isfinite(tab[colname])]
        num_rows_filtered = len(tab) - len(filtered)
        if num_rows_filtered > 0:
            warnings.warn(f"{num_rows_filtered} skipped because they do not have valid time values.", lk.LightkurveWarning)
        return filtered

    tab = Table.read(
        url,
        format="ascii.csv",
        converters={
            "oid": np.int64,
            "expid": np.int64,
            "filefracday": np.int64,
        },
    )

    tab = filter_rows_with_invalid_time(tab, time_column)

    time = get_required_column(tab, time_column)
    time = Time(time, format=time_format, scale=time_scale)
    flux = get_required_column(tab, flux_column)
    flux_err = get_required_column(tab, flux_err_column)

    lc = lk.LightCurve(
        time=time,
        flux=flux,
        flux_err=flux_err,
        data=tab,
    )

    # assign units
    for col in ["flux", "flux_err", flux_column, flux_err_column, "limitmag"]:
        if col in lc.colnames:
            lc[col] = lc[col] * u.mag

    lc.meta.update(
        {
            "FILEURL": url,
            "FLUX_ORIGIN": flux_column,
            "TIME_ORIGIN": time_column,
        }
    )

    oid_match = re.search(r"https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves.+ID=(\d+)", url)
    if oid_match is not None:
        id = f"ZTF OID {oid_match[1]}"  # include data release number too?
        lc.meta["OBJECT"] = id
        lc.meta["LABEL"] = id

    if mask_func is not None:
        mask = mask_func(lc)
        lc = lc[~mask]

    return lc


def make_lc_fig(url, period=None):
    try:
        lc = read_ztf_csv(url)

        if period is not None:
            lc = lc.fold(period=period, normalize_phase=True)

        #  hack: cadenceno and quality columns expected by prepare_lightcurve_datasource()
        lc["quality"] = np.zeros_like(lc.flux, dtype=int)
        lc["cadenceno"] = lc["quality"]
        lc_source = prepare_lightcurve_datasource(lc)

        ylim_func = lambda lc: (np.nanmin(lc.flux).value, np.nanmax(lc.flux).value)
        fig_lc, vertical_line = make_lightcurve_figure_elements(lc, lc_source, ylim_func=ylim_func)
        fig_lc.name = "lc_fig"
        # Customize the plot
        vertical_line.visible = False
        if isinstance(lc, lk.FoldedLightCurve):
            fig_lc.xaxis.axis_label = "Phase"
        else:
            fig_lc.xaxis.axis_label = f"Time [{lc.time.format.upper()}]"

        if lc.flux.unit is u.mag:
            fig_lc.yaxis.axis_label = "Mag"
            # flip y-axis as it's in magnitude (smaller value at top)
            ystart, yend = fig_lc.y_range.start, fig_lc.y_range.end
            fig_lc.y_range.start, fig_lc.y_range.end = yend, ystart

        # make the plot scatter like instead of lines
        # hack: assume the renderers are in specific order
        #       can be avoided if the renderers have name when they are created.
        # r_lc_step = [r for r in fig_lc.renderers if r.name == "lc_step"][0]
        r_lc_step = fig_lc.renderers[0]
        r_lc_step.visible = False

        # r_lc_circle = [r for r in fig_lc.renderers if r.name == "lc_circle"][0]
        r_lc_circle = fig_lc.renderers[1]
        r_lc_circle.glyph.fill_color = "gray"
        r_lc_circle.glyph.fill_alpha = 1.0
        r_lc_circle.nonselection_glyph.fill_color = "gray"
        r_lc_circle.nonselection_glyph.fill_alpha = 1.0

        return fig_lc
        # return Div(text=f"TODO - Lightcurve with {len(lc)} points, url:  {url}", name="lc_fig")
    except Exception as e:
        traceback.print_exc()  # for sever side debug
        return Div(text=f"Error in loading lightcurve. {type(e).__name__}: {e}", name="lc_fig")


def create_lc_viewer_ui(doc):
    in_url = TextInput(
        width=600, placeholder="ZTF Lightcurve CSV URL",
        # value="https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves?ID=660106400019009&COLLECTION=ztf_dr21&FORMAT=csv",  # TST
    )

    in_period = TextInput(
        width=100,
        # value="1.651",  # TST
    )

    show_btn = Button(label="Show", button_type="primary")

    ui_layout = column(
        Div(text="<hr>"),  # a spacer
        Div(text="<h3>Lightcurve</h3>"),
        row(Div(text="URL:"), in_url),
        row(Div(text="Period (d):"), in_period),
        show_btn,
        name="lc_viewer_ctl_ctr",
    )

    # add interactivity
    def add_lc_fig():
        url = in_url.value

        period = in_period.value
        # convert to optional float
        if period == "":
            period = None
        else:
            period = float(period)

        fig = make_lc_fig(url, period)

        # add the plot (replacing existing plot, if any)
        old_fig = ui_layout.select_one({"name": "lc_fig"})
        if old_fig is not None:
            # https://discourse.bokeh.org/t/clearing-plot-or-removing-all-glyphs/6792/6
            ui_layout.children[-1] = fig
        else:
            ui_layout.children.append(fig)

    show_btn.on_click(add_lc_fig)

    doc.add_root(ui_layout)


def show_app(tic, sector):
    # if True:    # test LC viewer UI only
    #     create_lc_viewer_ui(curdoc())
    #     return

    sr = lk.search_targetpixelfile(f"TIC{tic}", mission="TESS", sector=sector, author="SPOC")
    tpf = sr[-1].download()
    print("DBG2: ", tpf)

    create_skyview_ui = show_skyview_widget(
        tpf,
        aperture_mask="pipeline",
        magnitude_limit=tpf.meta.get("TESSMAG", 10) + 8,  # defaulted to 18
        catalogs=[
            (
                "gaiadr3_tic",
                dict(extra_cols_in_detail_view={"RUWE": "RUWE", "sepsi": "sepsi", "e_RV": "e_RV (km/s)"},
                    # urls_template=dict(gaiadr3_nss_url="https://vizier.cfa.harvard.edu/viz-bin/VizieR-4?-ref=VIZ65a1a2351812e4&-source=I%2F357&Source=%s",),
                )
            ),

            (
                "ztf",
                dict(radius=1.5*u.arcmin)
            ),

            "vsx",
        ],
        return_type="doc_init_fn",
    )

    async def create_app_ui(doc):
        await create_skyview_ui(doc)
        create_lc_viewer_ui(doc)

    doc = curdoc()
    doc.add_next_tick_callback(lambda: create_app_ui(doc))


def get_arg_as_int(args, arg_name, default_val=None):
    try:
        val = int(args.get(arg_name)[0])
    except:
        val = default_val
    return val

# Entry Point logic
args = curdoc().session_context.request.arguments
tic = get_arg_as_int(args, "tic", 400621146)  # default value for sample
sector = get_arg_as_int(args, "sector", None)
print("DBG1: ", tic, sector)

curdoc().title = "TESS SkyView with Gaia DR3, ZTF and VSX"
show_app(tic, sector)
