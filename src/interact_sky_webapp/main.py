import traceback

import astropy.units as u

import lightkurve as lk
from lightkurve.interact import show_skyview_widget, prepare_lightcurve_datasource, make_lightcurve_figure_elements
from .ext_gaia_tic import ExtendedGaiaDR3TICInteractSkyCatalogProvider

from bokeh.layouts import row, column
from bokeh.models import Button, Div, TextInput, Select, CustomJS, LinearColorMapper, Checkbox
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


def make_lc_fig(url, period=None, epoch=None, epoch_format=None, use_cmap_for_folded=False):
    try:
        lc = read_ztf_csv(url)

        if "filtercode" in lc.colnames:  # include ZTF filter in label for title
            filter_str = ",".join(np.unique(lc["filtercode"]))
            lc.label += f" ({filter_str})"

        if period is not None:
            if epoch is not None:
                if epoch_format is None or epoch_format == "btjd":
                    epoch_time = Time(epoch, format="btjd")
                elif epoch_format == "hjd":
                    epoch_time = Time(epoch, format="jd", scale="utc")
                else:
                    raise ValueError(f"Invalid epoch_format: {epoch_format}")
            else:
                epoch_time = None
            lc = lc.fold(period=period, epoch_time=epoch_time, normalize_phase=True)
            lc.label += f", P = {period} d"

        #  hack: cadenceno and quality columns expected by prepare_lightcurve_datasource()
        lc["quality"] = np.zeros_like(lc.flux, dtype=int)
        lc["cadenceno"] = lc["quality"]
        lc_source = prepare_lightcurve_datasource(lc)
        if isinstance(lc, lk.FoldedLightCurve) and use_cmap_for_folded:
            lc_source.data["time_original"] = lc.time_original.value

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
        if isinstance(lc, lk.FoldedLightCurve) and use_cmap_for_folded:
            # for phase plot, add color to circles to signify time
            time_cmap = LinearColorMapper(
                palette="Viridis256",
                low=min(lc_source.data["time_original"]),
                high=max(lc_source.data["time_original"])
            )
            r_lc_circle.glyph.fill_color = dict(field="time_original", transform=time_cmap)
            r_lc_circle.nonselection_glyph.fill_color = dict(field="time_original", transform=time_cmap)

        return fig_lc
    except Exception as e:
        traceback.print_exc()  # for sever side debug
        return Div(text=f"Error in loading lightcurve. {type(e).__name__}: {e}", name="lc_fig")


def create_lc_viewer_ui():
    in_url = TextInput(
        width=600, placeholder="ZTF Lightcurve CSV URL (the LC link to the right of ZTF OID)",
        # value="https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves?ID=660106400019009&COLLECTION=ztf_dr21&FORMAT=csv",  # TST
    )

    in_period = TextInput(
        width=100,
        placeholder="optional",
        # value="1.651",  # TST
    )

    in_epoch = TextInput(width=120, placeholder="optional")  # slightly wider, to (long) accommodate JD value

    in_epoch_format = Select(
        options=[("btjd", "BTJD"), ("hjd", "HJD")],
        value="btjd"
    )

    btn_period_half = Button(label="1/2 P")
    btn_period_double = Button(label="2x P")

    in_use_cmap_for_folded = Checkbox(label="Use color map to show time in phase plot", active=False)
    btn_plot = Button(label="Plot", button_type="primary")

    ui_layout = column(
        Div(text="<hr>"),  # a spacer
        Div(text="<h3>Lightcurve</h3>"),
        row(Div(text="URL *"), in_url),
        row(
            Div(text="Period (d)"), in_period, Div(text="epoch"), in_epoch, in_epoch_format,
            btn_period_half, btn_period_double,
        ),
        row(btn_plot, in_use_cmap_for_folded),
        name="lc_viewer_ctl_ctr",
    )

    # add interactivity
    def add_lc_fig():
        url = in_url.value

        period = in_period.value
        # convert to optional float
        period = float(period) if period != "" else None

        epoch = in_epoch.value
        # convert to optional float
        epoch = float(epoch) if epoch != "" else None

        epoch_format = in_epoch_format.value

        use_cmap_for_folded = in_use_cmap_for_folded.active
        fig = make_lc_fig(url, period, epoch, epoch_format, use_cmap_for_folded)

        # add the plot (replacing existing plot, if any)
        old_fig = ui_layout.select_one({"name": "lc_fig"})
        if old_fig is not None:
            # https://discourse.bokeh.org/t/clearing-plot-or-removing-all-glyphs/6792/6
            ui_layout.children[-1] = fig
        else:
            ui_layout.children.append(fig)

    def add_lc_fig_with_msg():
        # immediately show a message, as the actual plotting would take time
        msg_ui = Div(text="Plotting...", name="lc_fig")
        old_fig = ui_layout.select_one({"name": "lc_fig"})
        if old_fig is not None:
            # https://discourse.bokeh.org/t/clearing-plot-or-removing-all-glyphs/6792/6
            ui_layout.children[-1] = msg_ui
        else:
            ui_layout.children.append(msg_ui)
        curdoc().add_next_tick_callback(add_lc_fig)

    btn_plot.on_click(add_lc_fig_with_msg)

    def do_change_period(factor):
        try:
            period = float(in_period.value)
        except Exception:
            # No-op for case no period (empty string), or somehow an invalid number is used
            return

        # change the period and  re-plot
        in_period.value = str(period * factor)
        add_lc_fig_with_msg()

    btn_period_half.on_click(lambda: do_change_period(0.5))
    btn_period_double.on_click(lambda: do_change_period(2))

    return ui_layout


def create_search_form(tic, sector, magnitude_limit):
    def to_str(val):
        if val is None:
            return ""
        else:
            return str(val)

    # return a plain html search form, instead of using bokeh widgets
    #
    # HTML search form has the advantage of being completely stateless,
    # not relying on communicating with server (via WebSocket).
    # So for cases such as deploying in serverless environments such as Google Cloud Run,
    # if the server instance has been shutdown due to idle policy,
    # - plain html form would still work, as it will create a new HTTP request.
    # - bokeh widget / WebSocket based form would not work, as it
    #   relies on connecting to the server instance that has been shutdown.

    # put css text into its constant string so that curly braces
    # will not be misinterpreted as f-string substitution
    css_text = """
    <style>
        #search-form-ctr {
            padding-left: 10px;
            padding-right: 16px;
        }
        #search-form-ctr input {
            padding: 4px;
            margin-bottom: 10px;
        }
    </style>
"""
    return column(
        Div(text=f"""
<div id="search-form-ctr">
{css_text}
    <form>
        TIC *<br>
        <input name="tic" value="{to_str(tic)}" accesskey="/"><br>
        Sector<br>
        <input name="sector" value="{to_str(sector)}" placeholder="optional, latest if not specified"><br>
        mag. limit<br>
        <input name="magnitude_limit" value="{to_str(magnitude_limit)}" placeholder="optional, Tmag + 7 if not specified"><br>
        <input type="submit" value="Show">
    </form>
</div>
"""),
        name="app_search",
    )


def create_app_ui_container():
    ui_layout = row(
        column(name="app_left"),  # for search form
        column(name="app_main"),
        name="app_ctr",
    )

    return ui_layout


async def create_app_body_ui(tic, sector, magnitude_limit=None):
    # if True:  # for dev purpose only
    #     return column(create_lc_viewer_ui())

    # convert (potential) textual inputs to typed value
    try:
        tic = None if tic is None or tic == "" else int(tic)
        sector = None if sector is None or sector == "" else int(sector)
        magnitude_limit = None if magnitude_limit is None or magnitude_limit == "" else float(magnitude_limit)
    except Exception as err:
        return Div(text=f"<h3>Skyview</h3> Invalid Parameter. Error: {err}", name="skyview")

    if tic is None:
        return column(
            Div(text="<h3>Skyview</h3>", name="skyview"),
            Div(text="<h3>Lightcurve</h3>", name="lc_viewer"),
        )

    if sector is not None:
        msg_label = f"TIC {tic} sector {sector}"
    else:
        msg_label = f"TIC {tic}"
    aperture_mask = "pipeline"
    cutout_size = None
    sr = lk.search_targetpixelfile(f"TIC{tic}", mission="TESS", sector=sector)
    if len(sr) > 1:
        # exclude fast cadence data (20s), TPFs with fast cadence always has 2 min cadence counterparts
        # for the use case here, the fast cadence data is irrelevant. It'd just make the processing slower.
        sr = sr[sr.exptime > 60 *u.s]
    if len(sr) < 1:
        print(f"INFO: no TPF found for {msg_label}. Use TessCut.")
        aperture_mask = None  # N/A for TessCut
        cutout_size = (11, 11)  # OPEN: would be too small for bright stars
        sr = lk.search_tesscut(f"TIC{tic}", sector=sector)
    if len(sr) < 1:
        print(f"INFO: Cannot find TPF or TESSCut for {msg_label}. No plot to be made.")
        return Div(text=f"<h3>SkyView</h3> Cannot find Pixel data for {msg_label}", name="skyview")

    tpf = sr[-1].download(cutout_size=cutout_size)
    print("DBG2: ", tpf, f" sector {tpf.sector}")

    if magnitude_limit is None:
        # supply default
        magnitude_limit = tpf.meta.get("TESSMAG", 0)
        if magnitude_limit == 0:
            # handle case TESSMAG header is missing, or is explicitly 0 (from TessCut)
            magnitude_limit = 18
        else:
            magnitude_limit += 7

    # truncate the TPF to avoid showing the pixel brightness
    # at the beginning of observation,
    # as it's often not representative
    # (due to scatter light at the beginning of a sector)
    # Show brightness around day 3 (arbitrarily) instead.
    if tpf.time.max() - tpf.time.min() > 3:
        tpf = tpf[tpf.time.value > tpf.time.min().value + 3]

    create_skyview_ui = show_skyview_widget(
        tpf,
        aperture_mask=aperture_mask,
        magnitude_limit=magnitude_limit,
        catalogs=[
            (
                ExtendedGaiaDR3TICInteractSkyCatalogProvider,
                dict(extra_cols_in_detail_view={"RUWE": "RUWE", "sepsi": "sepsi", "e_RV": "e_RV (km/s)", "IPDfmp": "IPDfmp"},
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

    return column(
        await create_skyview_ui(),
        create_lc_viewer_ui(),
        # the name is used to signify an interactive UI is returned
        # (as opposed to the UI with a dummy UI or error message in the boundary conditions)
        name="app_body_interactive",
    )


def add_connection_lost_ui(doc):
    # UI to notify users when the websocket connection to the server is lost
    # thus losing all server-side based interactive features

    # https://docs.bokeh.org/en/latest/docs/examples/interaction/js_callbacks/doc_js_events.html

    js_connection_lost = CustomJS(code="""
document.body.insertAdjacentHTML("afterbegin", `
<div id="banner_ctr" style="font-size: 1.1rem; padding: 10px; padding-left: 5vw;
    background-color: rgba(255, 0, 0, 0.7); color: white; font-weight: bold;">
Lost the connection to the server. You'd need to reload the page for some interactive functions.
</div>
`);
""")
    doc.js_on_event("connection_lost", js_connection_lost)


def show_app(tic, sector, magnitude_limit=None):

    async def create_app_ui(doc):
        ui_ctr = create_app_ui_container()
        ui_left = ui_ctr.select_one({"name": "app_left"})
        ui_left.children = [create_search_form(tic, sector, magnitude_limit)]

        ui_main = ui_ctr.select_one({"name": "app_main"})
        ui_body = await create_app_body_ui(tic, sector, magnitude_limit=magnitude_limit)
        ui_main.children = [ui_body]
        doc.add_root(ui_ctr)
        if ui_body.name == "app_body_interactive":
            # the UI for monitoring WebSocket connection is only relevant
            # in the normal case that interactive widgets are to be shown.
            add_connection_lost_ui(doc)

    #
    # the actual entry point
    #
    doc = curdoc()
    doc.add_next_tick_callback(lambda: create_app_ui(doc))


def get_arg_as_int(args, arg_name, default_val=None):
    try:
        val = int(args.get(arg_name)[0])
    except:
        val = default_val
    return val


def get_arg_as_float(args, arg_name, default_val=None):
    try:
        val = float(args.get(arg_name)[0])
    except:
        val = default_val
    return val

#
# Entry Point logic
#
args = curdoc().session_context.request.arguments
tic = get_arg_as_int(args, "tic", None)  # default value for sample
sector = get_arg_as_int(args, "sector", None)
magnitude_limit = get_arg_as_float(args, "magnitude_limit", None)
print("DBG1: ", tic, sector, magnitude_limit, args)

curdoc().title = "TESS SkyView with Gaia DR3, ZTF and VSX"
show_app(tic, sector, magnitude_limit)
