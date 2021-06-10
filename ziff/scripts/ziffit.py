#! /usr/bin/env python
# -*- coding: utf-8 -*-
import os
import warnings
import time
import pandas
import numpy as np

from ztfquery import io
from .. import base

import dask
#from .. import __version__


DEFAULT_FIT_GMAG=[13, 18]
DEFAULT_SHAPE_GMAG=[13,18]
DEFAULT_ISOLATION = 14
    
def collect_input(file_, use_dask=False, overwrite=False,
                      waittime=None,
                      isolationlimit=DEFAULT_ISOLATION, 
                      fit_gmag=DEFAULT_FIT_GMAG, shape_gmag=DEFAULT_SHAPE_GMAG):
    """ """
    delayed = dask.delayed if use_dask else _not_delayed_

    #
    # - Waiting time is any
    #
    # - Get Files

    # - This way, first sciimg, then mskimg, this enables not to overlead IRSA.
    sciimg_mkimg = delayed(get_file_delayed)(file_, waittime=waittime,
                                                 suffix=["sciimg.fits","mskimg.fits"],
                                                 overwrite=overwrite, 
                                                 show_progress= not use_dask, maxnprocess=1)
    sciimg = sciimg_mkimg[0]
    mkimg  = sciimg_mkimg[1]
    #
    # - Build Ziff    
    ziff   = delayed(base.ZIFF)(sciimg, mkimg, fetch_psf=False)
    #
    # - Get the catalog    
    cats  = delayed(get_ziffit_gaia_catalog)(ziff, fit_gmag=fit_gmag, shape_gmag=shape_gmag,
                                                 isolationlimit=isolationlimit,shuffled=True)
    cat_tofit  = cats[0]
    cat_toshape= cats[1]
    
    return cat_tofit,cat_toshape

    
    
def ziffit_single(file_, use_dask=False, overwrite=False,
                      isolationlimit=DEFAULT_ISOLATION, waittime=None,
                      nstars=800, interporder=3, maxoutliers=None,
                      stamp_size=15,
                      fit_gmag=DEFAULT_FIT_GMAG, shape_gmag=DEFAULT_SHAPE_GMAG,
                      verbose=False):
    """ high level script function of ziff to 
    - find the isolated star from gaia 
    - fit the PSF using piff
    - compute and store the stars and psf-model shape parameters

    = Dask oriented =


    """
    delayed = dask.delayed if use_dask else _not_delayed_

    #
    # - Waiting time is any
    #
    # - Get Files

    # - This way, first sciimg, then mskimg, this enables not to overlead IRSA.
    if verbose:
        print("loading images")
    sciimg_mkimg = delayed(get_file_delayed)(file_, waittime=waittime,
                                                 suffix=["sciimg.fits","mskimg.fits"],
                                                 overwrite=overwrite, 
                                                 show_progress= not use_dask, maxnprocess=1)
    sciimg = sciimg_mkimg[0]
    mkimg  = sciimg_mkimg[1]
    #
    # - Build Ziff
    if verbose:
        print("loading ziff")
    ziff   = delayed(base.ZIFF)(sciimg, mkimg, fetch_psf=False)
    #
    # - Get the catalog
    if verbose:
        print("loading cats")
    cats  = delayed(get_ziffit_gaia_catalog)(ziff, fit_gmag=fit_gmag, shape_gmag=shape_gmag,
                                              isolationlimit=isolationlimit,
                                              shuffled=True)
    cat_tofit  = cats[0]
    cat_toshape= cats[1]
    #
    # - Fit the PSF
    psf    = delayed(base.estimate_psf)(ziff, cat_toshape, stamp_size=stamp_size,
                                            interporder=interporder, nstars=nstars,
                                            maxoutliers=maxoutliers, verbose=False)
    # shapes
    shapes  = delayed(base.get_shapes)(ziff, psf, cat_tofit, store=True, stamp_size=stamp_size,
                                                incl_residual=True, incl_stars=True)
    
    return delayed(_get_ziffit_output_)(shapes)

def _get_ziff_psf_cat_(file_, whichpsf="psf_PixelGrid_BasisPolynomial5.piff"):
    """ """
    files_needed = io.get_file(file_, suffix=[whichpsf,"sciimg.fits", "mskimg.fits",
                                              "shapecat_gaia.fits"], check_suffix=False)
    # Dask
    psffile, sciimg, mkimg, catfile = files_needed[0],files_needed[1],files_needed[2],files_needed[3]

    ziff         = base.ZIFF(sciimg, mkimg, fetch_psf=False)
    cat_toshape  = base.catlib.Catalog.load(catfile, wcs=ziff.wcs)
    psf          = base.piff.PSF.read(file_name=psffile, logger=None)
    
    return ziff, psf, cat_toshape

def compute_shapes(file_, use_dask=False, incl_residual=True, incl_stars=True,
                       whichpsf="psf_PixelGrid_BasisPolynomial5.piff", stamp_size=15):
    """ high level script function of ziff to 
    - compute and store the stars and psf-model shape parameters

    This re-perform the last steps of ziffit_single.

    = Dask oriented =

    """
    delayed = dask.delayed if use_dask else _not_delayed_


    input_needed = delayed(_get_ziff_psf_cat_)(file_, whichpsf=whichpsf)
    ziff, psf, cat_toshape = input_needed[0],input_needed[1],input_needed[2]
    
    shapes       = delayed(base.get_shapes)(ziff, psf, cat_toshape, store=True, stamp_size=stamp_size,
                                                incl_residual=incl_residual, incl_stars=incl_stars)
    
    return shapes[["sigma_model","sigma_data"]].median(axis=0).values

    

    



# ================ #
#    INTERNAL      #
# ================ #
def _not_delayed_(func):
    return func

def _get_ziffit_output_(shapes):
    """ """
    if shapes is not None:
        return shapes[["sigma_model","sigma_data"]].median(axis=0).values
    return [None,None]

def get_ziffit_gaia_catalog(ziff, isolationlimit=DEFAULT_ISOLATION,
                                fit_gmag=DEFAULT_FIT_GMAG, shape_gmag=DEFAULT_SHAPE_GMAG,
                                shuffled=True, verbose=True):
    """ """
    if not ziff.has_images():
        warnings.warn("No image in the given ziff")
        return None,None

    try:
        if "gaia" not in ziff.catalog:
            if verbose:
                print("loading gaia")        
            ziff.fetch_gaia_catalog(isolationlimit=isolationlimit)
        
        cat_to_fit   = ziff.get_catalog("gaia", filtered=True, shuffled=shuffled, 
                              writeto="psf", #psfcat_gaia.fits
                              add_filter={'gmag_outrange':['gmag', fit_gmag]},
                              xyformat="fortran")
    
        cat_to_shape = ziff.get_catalog("gaia", filtered=True, shuffled=shuffled, 
                              writeto="shape", #shapecat_gaia.fits
                              add_filter={'gmag_outrange':['gmag', shape_gmag]},
                              xyformat="fortran")
    
        return cat_to_fit,cat_to_shape
    except:
        warnings.warn("Failed grabing the gaia catalogs, Nones returned")
        return None,None

def get_binned_data(files, bin_val, key, savefile=None, columns=None,
                    quantity='sigma', normref="model"):
    """ """
    filefracday = [f.split("/")[-1].split("_")[1] for f in files]
    df = pandas.concat([pandas.read_parquet(f, columns=columns) for f in files], keys=filefracday
                           ).reset_index().rename({"level_0":"filefracday"}, axis=1)


    norm = df.groupby(["obsjd"])[f"{quantity}_{normref}"].transform("median")
    
    df[f"{quantity}_data_n"] = df[f"{quantity}_data"]/norm
    df[f"{quantity}_model_n"] = df[f"{quantity}_model"]/norm
    df[f"{quantity}_residual"] = (df[f"{quantity}_data"]-df[f"{quantity}_model"])/df[f"{quantity}_model"]
    
    df[f"{key}_digit"] = np.digitize(df[key], bin_val)
    if savefile:
        df.to_parquet(savefile)
        
    return df
    
def get_sigma_data(files, bins_u, bins_v,
                    minimal=False,
                   quantity='sigma', normref="model", incl_residual=True,
                   basecolumns=['u', 'v', 'ccdid', 'qid', 'rcid', 'obsjd', 'fieldid','filterid', 'maglim'],
                   savefile=None,
                  ):
    if minimal:
        shape_columns = [f"{quantity}_data",  f"{quantity}_model"]
        incl_residual = False
    else:
        shape_columns = [f"sigma_data",f"sigma_model"] + \
                        [f"shapeg2_data",f"shapeg2_model"] + \
                        [f"shapeg1_data",f"shapeg1_model"] + \
                        [f"centerv_data",f"centerv_model"] + \
                        [f"centeru_data",f"centeru_model"]
    columns = basecolumns + shape_columns
    if incl_residual: 
        columns += ["residual"]

    filefracday = [f.split("/")[-1].split("_")[1] for f in files]
    df = pandas.concat([pandas.read_parquet(f, columns=columns) for f in files], keys=filefracday
                           ).reset_index().rename({"level_0":"filefracday"}, axis=1)
    
    norm = df.groupby(["obsjd"])[f"{quantity}_{normref}"].transform("median")
    
    df[f"{quantity}_data_n"] = df[f"{quantity}_data"]/norm
    df[f"{quantity}_model_n"] = df[f"{quantity}_model"]/norm
    df[f"{quantity}_residual"] = (df[f"{quantity}_data"]-df[f"{quantity}_model"])/df[f"{quantity}_model"]
    df["u_digit"] = np.digitize(df["u"],bins_u)
    df["v_digit"] = np.digitize(df["v"],bins_v)
    if savefile:
        df.to_parquet(savefile)
    return df



def get_file_delayed(file_, waittime=None,
                         suffix=["sciimg.fits","mskimg.fits"], overwrite=False, 
                         show_progress=True, maxnprocess=1, **kwargs):
    """ """
    if waittime is not None:
        time.sleep(waittime)
        
    return io.get_file(file_, suffix=suffix, overwrite=overwrite, 
                        show_progress=show_progress, maxnprocess=maxnprocess)
    
# ================ #
#    INTERNAL      #
# ================ #
