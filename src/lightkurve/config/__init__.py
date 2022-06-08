import astropy.config as astropyconfig


ROOTNAME = 'lightkurve'


class ConfigNamespace(astropyconfig.ConfigNamespace):
    rootname = ROOTNAME


class ConfigItem(astropyconfig.ConfigItem):
    rootname = ROOTNAME


def get_config_dir():
    """
    Determines the package configuration directory name and creates the
    directory if it doesn't exist.

    This directory is typically ``$HOME/.lightkurve/config``, but if the
    XDG_CONFIG_HOME environment variable is set and the
    ``$XDG_CONFIG_HOME/lightkurve`` directory exists, it will be that directory.
    If neither exists, the former will be created and symlinked to the latter.

    Returns
    -------
    configdir : str
        The absolute path to the configuration directory.

    """
    return astropyconfig.get_config_dir(ROOTNAME)


def get_cache_dir():
    """
    Determines the default Lightkurve cache directory name and creates the
    directory if it doesn't exist.

    This directory is typically ``$HOME/.lightkurve/cache``, but if the
    XDG_CACHE_HOME environment variable is set and the
    ``$XDG_CACHE_HOME/lightkurve`` directory exists, it will be that directory.
    If neither exists, the former will be created and symlinked to the latter.

    Note: If users customize the default via ``search_result_download_dir``
    configuration, the value returned by this function is ignored: the
    user-specified directory will be used instead.

    Returns
    -------
    cachedir : str
        The absolute path to the cache directory.
    """
    return astropyconfig.get_cache_dir(ROOTNAME)


def warn_if_default_cache_dir_migration_needed():
    import os
    from pathlib import Path
    import warnings

    new_dir = Path(Path.home(), ".lightkurve", "cache")
    old_dir = Path(Path.home(), ".lightkurve-cache")
    if not old_dir.is_symlink() and old_dir.is_dir():
        # case 1: old_dir exists (not a symlink) - migration needed
        warnings.warn(
            f"Default data files cache directory is changed to {new_dir} ."
            f"Remove the old directory {old_dir}, or move its files to the new one.",
            UserWarning,
        )
        return True
    elif old_dir.is_symlink():
        # case 2: old_dir is a symlink, we check if it points to new_dir
        # Notes:
        # - resolving symlink could be done with old_dir.resolve()
        #   but it raises PermissionError [WinError 5] Access is denied on Windows
        # - we also avoid using Path.readlink(), as it requires Python 3.9+
        old_dir_target = Path(old_dir.parent, os.readlink(old_dir))
        if old_dir_target != new_dir:
            #  case 2a: old_dir is a symlink points and does not point to a new_dir - migration needed
            warnings.warn(
                f"Default data files cache directory is changed to {new_dir} ."
                f"Remove the old directory {old_dir} (a symlink), or move its files to the new one.",
                UserWarning,
            )
            return True
        else:
            #  case 2b: old_dir is a symlink points to new_dir
            # (e.g., for backward compatibility with older version of lightkurve)
            # no migration needed
            return False
    else:
        # case 3: old_dir does not exist. no migration needed
        return False
