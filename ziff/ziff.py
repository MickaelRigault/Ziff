#!/usr/bin/env python
# -*- coding: utf-8 -*-
################################################################################
# Filename:          ziff.py
# Description:       script description
# Author:            Romain Graziani <romain.graziani@clermont.in2p3.fr>
# Author:            $Author: rgraziani $
# Created on:        $Date: 2020/09/21 10:40:18 $
# Modified on:       2020/10/13 15:24:04
# Copyright:         2019, Romain Graziani
# $Id: ziff.py, 2020/09/21 10:40:18  RG $
################################################################################

"""
.. _ziff.py:

ziff.py
==============


"""
__license__ = "2019, Romain Graziani"
__docformat__ = 'reStructuredText'
__author__ = 'Romain Graziani <romain.graziani@clermont.in2p3.fr>'
__date__ = '2020/09/21 10:40:18'
__adv__ = 'ziff.py'

import os
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
import json
import pkg_resources
from .catalog import Catalog, ReferenceCatalog
import logging
import piff
from piff.star import Star, StarData, StarFit

import galsim
import pandas as pd

collection_functions = [
    'set_config_value',
    'run_piff',
    'set_default_catalogue',
    'make_stars',
    'reflux_stars',
    'compute_residuals'
]

######################
#                    #
#  Ziff Class        #
#                    #
######################

class Ziff(object):
    # Wrapper of piff for ztf
    
    def __init__ (self, sciimg, mskimg=None, logger=None,
                      build_default_cat=True, load_default_cat=True,
                      check_exist=True, save_cat=True):
        """Wrapper of PIFF for ZTF 

        Single fit of potentially multi images.
        
        Parameters
        ----------
        sciimg: [string]
            path to the ztf science image (sciimg)
            
        mskimg: [string or None] -optional-
            path to the science image mask (mskimg)

        logger: [logger or None] -optional-
            logger passed to piff. 

        build_default_cat: [bool] -optional-
            DOC 

        load_default_cat: [bool] -optional-
            DOC

        check_exist: [bool] -optional-
            DOC 

        save_cat: [bool] -optional-
            DOC 

        
        """

        sciimg = np.atleast_1d(sciimg)
        if check_exist:
            for s in sciimg:
                if not os.path.exists(s):
                    raise FileNotFoundError(f"{s} does not exist.")
                
        self._sciimg = sciimg
        self.set_mskimg(mskimg)
        self.set_logger(logger)
        self._catalog = {}
        self.load_default_config()
        
        if load_default_cat:
            self.load_default_catalog()
        elif build_default_cat:
            self.build_default_catalog(save_cat = save_cat)

    @classmethod
    def from_file(cls, filename, row=0, **kwargs):
        """ """
        with open(filename,'r') as f: 
            lines = f.readlines()
            for (i,line) in enumerate(lines):
                if i == row:
                    sciimg = line[0:-1].split(',')
                    return cls(sciimg, **kwargs)

    @classmethod
    def from_zquery(cls, zquery,  **kwargs):
        """ """
        sciimg_list = zquery.get_local_data("sciimg.fits")
        mskimg_list =  zquery.get_local_data("mskimg.fits")
        return cls(sciimg_list, mskimg_list, **kwargs) #cls(name, date.today().year - year)
    

    # ================ #
    #   Methods        #
    # ================ #
    # -------- #
    #  LOADER  #
    # -------- #
    def load_default_config(self):
        """ Load the default configuration settings using default configuration file """
        file_name = pkg_resources.resource_filename('ziff', 'data/default_config.json')
        with open(file_name) as config_file:
            self.config = json.load(config_file)
            
        # add the filename
        self.config['i/o']['image_file_name'] = self._sciimg.tolist()

    def load_default_catalog(self):
        print("Loading default catalogs")
        try:
            self.set_catalog([self.get_catalog('gaia_calibration',i) for i in range(self.nimgs)])
            self.set_catalog([self.get_catalog('gaia_full',i) for i in range(self.nimgs)])
        except FileNotFoundError:
            print("Catalogs not found")
            self.build_default_catalog()

    def load_psf(self, path = None, save_suffix = 'output.piff'):
        """ Load an existing 'psf.piff' file. """
        if path is None:
            path = self.prefix[0] + save_suffix
        self._psf = piff.PSF.read(file_name=path,logger=self.logger)

    # -------- #
    # BUILDER  #
    # -------- #
    def build_default_catalog(self, save_cat = True):
        """ """
        print("Building default catalogs")
        #catalogs = [self.build_all_cat(num = i) for i in range(self.nimgs)]
        catalogs = []
        for i in range(self.nimgs):
            catalogs.append(self.build_all_cat(num = i))
        self.set_catalog([catalogs[i][0] for i in range(self.nimgs)])
        self.set_catalog([catalogs[i][1] for i in range(self.nimgs)])
        if save_cat:
            self.save_all_cats()
            
    def build_default_calibration_cat(self, num):
        """ """
        subziff = self.create_singleimg_ziff(num)
        c = ReferenceCatalog(ziff = subziff, which = 'gaia', name = 'gaia_calibration') # Catalog object
        c.download() # fetch gaia catalog
        # Filters
        c.set_is_isolated()
        c.set_mask_pixels()
        c.add_filter('Gmag',[13,16], name = 'mag_filter')
        c.add_filter('xpos',[20,3030], name = 'border_filter_x')
        c.add_filter('ypos',[20,3030], name = 'border_filter_y')
        c.add_filter('is_isolated',[1,2], name = 'isolated_filter')
        c.add_filter('has_badpix', [-0.5, 0.5], 'filter_badpix')
        c.data['ra'] = c.data['RA_ICRS']
        c.data['dec'] = c.data['DE_ICRS']
        c.set_sky()
        #c.save_fits(filtered=True)
        return c

    def build_default_full_cat(self, num):
        """ """
        subziff = self.create_singleimg_ziff(num)
        c = ReferenceCatalog(ziff = subziff, which = 'gaia', name = 'gaia_full')
        c.download()
        c.set_sky()
        c.set_is_isolated()
        c.set_mask_pixels()
        c.add_filter('xpos',[10,3040], name = 'border_filter_x')
        c.add_filter('ypos',[10,3040], name = 'border_filter_y')
        c.add_filter('has_badpix', [-0.5, 0.5], 'filter_badpix')
        c.add_filter('Gmag',[12,18], name = 'mag_filter')
        c.add_filter('is_isolated',[1,2], name = 'isolated_filter')
        return c

    def build_all_cat(self,num):
        """ """        
        c = self.build_default_calibration_cat(num)

        c2 = c.copy('gaia_full')        
        c2.remove_filter('mag_filter')
        c2.add_filter('Gmag',[12,18], name = 'mag_filter')
        return (c,c2)
    
    # -------- #
    #  SETTER  #
    # -------- #
    def set_mskimg(self, mskimg=None):
        """ Set mskimg, or find one if it's None """
        if mskimg is None:
            self._mskimg = [None]*self.nimgs
            for i,(s,p) in enumerate(zip(self._sciimg,self.prefix)):
                if os.path.exists(p+'mskimg.fits'):
                    self._mskimg[i] = p + 'mskimg.fits'
        else:
            self._mskimg = np.atleast_1d(mskimg)
            assert(len(self._mskimg) == len(self._sciimg))

    def set_logger(self, logger=None):
        """ set the logger that is going to be passed to piff """
        if logger is None:
            logging.basicConfig(filename=self.prefix[0] + 'logger.piff',level=logging.DEBUG)
            logger = logging.getLogger()
            self.logger = logger
        else:
            self.logger = logger
    
    def set_config_value(self, key_path, value, sep=','):
        """ update the configuration values """
        # Should be cleaned but it works
        kp = key_path.split(sep)
        to_eval = 'config' + ''.join([f"['{k}']" for k in kp]) + f" = {value}"
        if isinstance(value, str):
            to_eval = 'config' + ''.join([f"['{k}']" for k in kp]) + f" = '{value}'"
        exec(to_eval,{'config':self.config})

    def set_default_config(self):
        """ Load the default configuration settings using default configuration file """
        print("DEPRECATED, set_default_config -> load_default_config")
        return self.load_default_config()
    
    def set_catalog(self, catalogs, name=None):
        """ Add a new catalog """
        if name is None:
            name = catalogs[0].name # odd to have a [0] here
            
        self._catalog[catalogs[0].name] = catalogs
        
    # -------- #
    #  GETTER  #
    # -------- #            
    def create_singleimg_ziff(self, num):
        """ create a new Ziff instance with single image """
        return Ziff(self._sciimg[num],self._mskimg[num],logger=self.logger, load_default_cat = False, build_default_cat = False, save_cat = False)
    
    def get_prefix(self):
        """ Get the img prefix """
        # IO Stuffs
        return ['_'.join(s.split('_')[0:-1])+'_' for s in self._sciimg]

    def get_dir(self):
        """ Get the directory of the image """
        # IO Stuffs        
        return [os.path.dirname(s) for s in self._sciimg]    

    
    def get_catalog(self, name, num):
        """ """
        subziff = self.create_singleimg_ziff(num)
        return Catalog.load(self.prefix[num] + name + '.fits', ziff=subziff, name=name)

    # --------- #
    #  PIFF     #
    # --------- #
    def run_piff(self, catalog, prefix = None, overwrite_cat = False, save_suffix = 'output.piff'):
        """ run the piff PSF algorithm on the given images using the given reference catalog (star location) 
        
        Parameters
        ----------
        catalog
        """
        if prefix is None:
            prefix = self.prefix
            
        cat = self.process_catalog_name(catalog)
        prefix = np.atleast_1d(prefix)
        # Save catalogue
        self.save_catalog(cat,prefix,overwrite_cat)
        
        # Update config
        self.config['i/o']['cat_file_name'] = [p +  c.name + '.fits' for (p,c) in zip(prefix,cat)]
        self.config['calibration_cat'] = [c.get_config() for c in cat]
        inputfile = self.get_piff_inputfile()
        
        # Piff stars
        stars = inputfile.makeStars()
        wcs, pointing = self.get_wcspointing()

        psf = piff.SimplePSF.process(self.config['psf'])
        psf.fit(stars, wcs, pointing, logger=self.logger)
        [psf.write(p + save_suffix) for p in self.prefix]
        self._psf = psf
        [self.save_config(p + 'piff_config.json') for p in self.prefix]

    def make_stars(self, catalog, prefix = None, overwrite_cat = True, append_df_keys = None):
        """ """
        if prefix is None:
            prefix = self.prefix
        cat = self.process_catalog_name(catalog)
        self.config['i/o']['cat_file_name'] = [p + c.name + '.fits' for (c,p) in zip(cat,prefix)]
        # Save catalogue
        if overwrite_cat:
            self.save_catalog(cat,prefix,overwrite_cat)
        else:
            self.logger.warning("Using already saved catalogs")
        inputfile = self.get_piff_inputfile()
        stars = inputfile.makeStars(logger=self.logger)
        for s in stars:
            s._cat_kwargs = {}
        if append_df_keys is not None:
            append_df_keys = np.atleast_1d(append_df_keys)
            df = self.get_stacked_cat_df()[catalog]
            for (i,s) in enumerate(stars):
                for key in append_df_keys:
                    s._cat_kwargs[key] = df.iloc[i][key]
                    s._cat_kwargs['name'] = df.iloc[i].name
        return stars

    def reflux_stars(self, stars, fit_center = False, which = 'minuit'):
        """ measure the flux and centroid (if allowed) of the star give the PSF.
        

        Parameters
        ----------
            which : either 'minuit' or 'piff'
            DOC

        Returns
        -------
        """
        if fit_center:
            self.psf.model._centered = True
        wcs, pointing = self.get_wcspointing()
        new_stars = []
        for (i,s) in enumerate(stars):
            print(f"Processing {i+1}/{len(stars)}")
            s.image.wcs = wcs[s.chipnum]
            s.run_hsm()
            new_s = self.psf.model.initialize(s)
            new_s = self.psf.interpolateStar(new_s)
            new_s.fit.flux = s.run_hsm()[0]
            new_s.fit.center = (0,0)
            if which == 'minuit':
                new_s = self.reflux_minuit(new_s, fit_center = fit_center)
            else:
                new_s = self.psf.model.reflux(new_s, fit_center = fit_center)
            new_s._cat_kwargs = s._cat_kwargs
            new_stars.append(new_s)
        self.psf.model._centered = False
        return new_stars


    #REFLUIX MINUIT
    

    def reflux_minuit(self, star, fit_center=True):
        # Make sure input is properly normalized
        self.psf.model.normalize(star)
        # Calculate the current centroid of the model at the location of this star.
        # We'll shift the star's position to try to zero this out.
        delta_u = np.arange(-self.psf.model._origin[0], self.psf.model.size-self.psf.model._origin[0])
        delta_v = np.arange(-self.psf.model._origin[1], self.psf.model.size-self.psf.model._origin[1])
        u, v = np.meshgrid(delta_u, delta_v)
        temp = star.fit.params.reshape(self.psf.model.size,self.psf.model.size)
        params_cenu = np.sum(u*temp)/np.sum(temp)
        params_cenv = np.sum(v*temp)/np.sum(temp)
        data, weight, u, v = star.data.getDataVector()
        dof = np.count_nonzero(weight)
        
        def chi2(center_x,center_y, flux):
            data, weight, u, v = star.data.getDataVector()
            center = (center_x,center_y)
            scaled_flux = flux * star.data.pixel_area
            up = u-center[0]
            vp = v-center[1]
            coeffs, psfx, psfy, _,_ = self.psf.model.interp_calculate(up/self.psf.model.scale, vp/self.psf.model.scale, True)
            index1d = self.psf.model._indexFromPsfxy(psfx, psfy)
            nopsf = index1d < 0
            alt_index1d = np.where(nopsf, 0, index1d)
            coeffs = np.where(nopsf, 0., coeffs)
            pvals = star.fit.params[alt_index1d]
            mod = np.sum(coeffs*pvals, axis=1)
            resid = data - mod*scaled_flux
            chisq = np.sum(resid**2 * weight)
            return chisq
        
        from iminuit import Minuit
        m = Minuit(chi2,center_x = 0, center_y = 0, limit_center_x = (-3,3), limit_center_y = (-3,3), flux=1000,limit_flux = (1,None), fix_center_x = not fit_center, fix_center_y = not fit_center, print_level = 0,error_flux = 1, error_center_x = 0.01, error_center_y = 0.01, errordef = 1)
        _ = m.migrad()  # run optimiser
        #print(m.values)
        
        return Star(star.data, StarFit(star.fit.params,
                                       flux = m.values['flux'],
                                       center = (m.values['center_x'],m.values['center_y']),
                                       params_var = star.fit.params_var,
                                       chisq = 0,
                                       dof = dof,
                                       A = star.fit.A,
                                       b = star.fit.b))
    # --------- #
    #  OTHER    #
    # --------- #
    def read_shapes(self, as_df = True, save_suffix = 'shapes'):
        """ """
        # RESULT READER
        # - Should not be native here.
        f = np.load(self.prefix[0]+f'{save_suffix}.npz')
        if as_df:
            return pd.DataFrame.from_dict(dict(f))
        return f
    
    def process_catalog_name(self, catalog):
        """ Eval if catalog is a name or an object. Returns the object """
        if isinstance(catalog, str):
            return self._catalog[catalog]
        elif isinstance(catalog, Catalog):
            return catalog
        else:
            raise TypeError("catalog must be a name or a Catalog")

    def get_stacked_cat_df(self):
        dfs = {}
        for cat in self.catalog:
            c = self.process_catalog_name(cat)
            df = []
            for i in range(self.nimgs):
                dfi = c[i].data
                dfi = dfi.loc[dfi['filter'] == 1]
                df.append(dfi)
            dfs[cat] = pd.concat(df)
        return dfs
    
    def save_all_cats(self, overwrite= True):
        for cat in self.catalog:
            c = self.process_catalog_name(cat)
            self.save_catalog(c, self.prefix, overwrite = overwrite)
            
    def save_catalog(self, cat, prefix, overwrite):
        for (c,p) in zip(cat,prefix):
            c.write_to(p + c.name + '.fits', overwrite = overwrite, filtered=True)
            
    def save_config(self, path):
        with open(path, 'w') as f:
            json.dump(self.config, f)

    def get_stars_cat_kwargs(self, stars):
        out = {}
        keys = stars[0]._cat_kwargs.keys()
        for k in keys:
            out[k] = []
        for s in stars:
            for k in keys:
                out[k].append(s._cat_kwargs[k])
        return out
    
    def compute_shapes(self, stars, save=False, save_suffix = 'shapes'):
        shapes = {'instru_flux': [], 'T_data': [], 'T_model': [],
                      'g1_data': [],'g2_data': [],'g1_model': [],
                      'g2_model': [],'u': [],'v': [],
                      'flag_data': [],'flag_model': [],
                      'center_u' : [],'center_v' : []}
        for s in stars:
            s.run_hsm()
            ns = self.psf.drawStar(s)
            ns.run_hsm()
            shapes['instru_flux'].append(s.flux)
            shapes['T_data'].append(s.hsm[3])
            shapes['T_model'].append(ns.hsm[3])
            shapes['g1_data'].append(s.hsm[4])
            shapes['g1_model'].append(ns.hsm[4])
            shapes['g2_data'].append(s.hsm[5])
            shapes['g2_model'].append(ns.hsm[5])
            shapes['u'].append(s.u)
            shapes['v'].append(s.v)
            shapes['center_u'].append(s.center[0])
            shapes['center_v'].append(s.center[1])
            shapes['flag_data'].append(s.hsm[6])
            shapes['flag_model'].append(ns.hsm[6])
            
        shapes['T_data_normalized'] = shapes['T_data']/np.median(shapes['T_data'])
        shapes['T_model_normalized'] = shapes['T_model']/np.median(shapes['T_data'])
        # Adding cat_kwargs
        shapes = {**shapes, **self.get_stars_cat_kwargs(stars)}
        if save:
            [np.savez(p + save_suffix,**shapes) for p in self.prefix]
        return shapes

    def compute_residuals(self, stars, normed = True, sky = 100):
        residuals = []
        for s in stars:
            draw = self.psf.drawStar(s)
            res = s.image.array - draw.image.array
            if normed:
                res /= draw.image.array + sky
            residuals.append(res)
        return np.stack(residuals)

    def get_ztfimg(self):
        """To use ztfimg from Rigault
        """
        from ztfimg import image
        imgs = [image.ScienceImage(s,m) for (s,m) in zip(self._sciimg,self._mskimg)]
        [img.load_source_background() for img in imgs]
        return imgs
    
    def get_header(self):
        """Get the header of the image
        """
        return [fits.open(s)[0].header for s in self._sciimg]
    
    def get_wcs(self):
        """Get the wcs solutin from the image header """
        return [WCS(h) for h in self.get_header()]

    def set_wcs(self):
        self._wcs = self.get_wcs()

    def get_mask_data(self):
        """ """
        return [fits.open(msk)[0].data for msk in self._mskimg]
    
    def set_mask(self, **kwargs):
        """ """
        self._mask = [i.get_mask(**kwargs) for  i in self.get_ztfimg()]
        
    def get_wcspointing(self):
        inputfile = self.get_piff_inputfile()
        wcs = inputfile.getWCS()
        inputfile.setPointing('RA','DEC')
        return wcs,inputfile.getPointing()

    def get_piff_inputfile(self):
        inputfile = piff.InputFiles(self.config['i/o'], logger=self.logger)
        inputfile.setPointing('RA','DEC')
        return inputfile
    
    # ================ #
    #   Properties     #
    # ================ #
    @property
    def catalog(self):
        """ Dictionnary of catalogs used by Piff"""
        return self._catalog
    
    @property
    def mask(self):
        """ """
        if not hasattr(self,"_mask"):
            self.set_mask()
        return self._mask
    
    @property
    def ztfcat(self):
        """ New name for psfcat of zTF pipeline """
        return [p + 'psfcat.fits' for p in self.prefix]

    @property
    def prefix(self):
        """ Prefix of the image. Useful for getting mskimg, psfcat etc. in the actual pipeline """
        return self.get_prefix()
    
    @property
    def wcs(self):
        """ WCS solution """
        if not hasattr(self,'_wcs'):
            self.set_wcs()
        return self._wcs

    @property 
    def shape(self):
        """ Image shape """
        return (3080, 3072)
    
    @property
    def ra(self):
        if not hasattr(self, '_ra'):
            self._ra = [wcs.pixel_to_world_values(*np.asarray([header['NAXIS1'], header['NAXIS2']])/2 + 0.5)[0]
                            for (wcs,header) in zip(self.wcs,self.get_header())]
        return self._ra
    
    @property
    def dec(self):
        if not hasattr(self, '_dec'):
            self._dec = [wcs.pixel_to_world_values(*np.asarray([header['NAXIS1'], header['NAXIS2']])/2 + 0.5)[1]
                             for (wcs,header) in zip(self.wcs,self.get_header())]
        return self._dec

    @property
    def psf(self):
        if not hasattr(self, '_psf'):
            self.load_psf()
        return self._psf

    @property
    def nimgs(self):
        """ Number of images used"""
        return len(self._sciimg)

    @property
    def ccd(self):
        return [int(p.split('_')[-4][1::]) for p in self.prefix]

    @property
    def quadrants(self):
        return [int(p.split('_')[-2][1::]) for p in self.prefix]

    @property
    def fracday(self):
        return [int(p.split('/')[-2][1::]) for p in self.prefix]

    @property
    def filter(self):
        return [p.split('_')[-5][1::] for p in self.prefix]

    
######################
#                    #
#  Ziff Collection   #
#                    #
######################

class ZiffCollection( object ):
    
    def __init__(self, sciimg_list, mskimg_list = None, logger = None, **kwargs):
        """ 
        
        Parameters
        ----------
        sciimg_list, mskimg_list: [strings or list of] -optional-
            Path (or list of) to the ztf science image (sciimg.fits) and their corresponding mask images (mskimg.fits)

        logger: [logger or None] -optional-
            logger passed to piff.

        **kwargs goes to Ziff
        """
        if mskimg_list is None:
            mskimg_list = [None] * len(sciimg_list)
            
        self.ziffs = [Ziff(s,m,logger,**kwargs) for (s,m) in zip(np.atleast_1d(sciimg_list), np.atleast_1d(mskimg_list))]
    
    @classmethod
    def from_zquery(cls, zquery,  groupby = ['ccdid','fracday','fid'], **kwargs):
        """ """
        mt = zquery.get_local_metatable(which='dl')
        mt.index = np.arange(np.size(mt,axis=0))
        groupby = mt.groupby(groupby)
        groups = groupby.groups
        local_data_sciimg = np.asarray(zquery.get_local_data("sciimg.fits", filecheck = False))
        sciimg_list = [local_data_sciimg[groupby.get_group(i).index.values] for i in groups]
        local_data_mskimg = np.asarray(zquery.get_local_data("mskimg.fits", filecheck = False))
        mskimg_list = [local_data_mskimg[groupby.get_group(i).index.values] for i in groups]
        return cls(sciimg_list, mskimg_list, **kwargs) #cls(name, date.today().year - year)

    def to_file(self, filename):
        with open(filename,'w') as f:
            for ziff in self.ziffs:
                for (i,l0) in enumerate(ziff._sciimg):
                    if i ==0 :
                        f.write(l0)
                    else:
                        f.write(',' + l0)
                f.write('\n')
                
    @classmethod
    def from_file(cls, filename,max_rows=None, **kwargs):
        list_img = []
        with open(filename,'r') as f: 
            lines = f.readlines()
            if max_rows is None:
                max_rows = len(lines)
            for line in lines[0:max_rows]: 
                list_img.append(line[0:-1].split(',')) 
        return cls(list_img, **kwargs)

    def read_shapes(self):
        dfs = []
        for (i,z) in enumerate(self.ziffs):
            print('{i+1}/{len(self.ziffs)}')
            try:
                df = z.read_shapes()
                df['ccd'] = z.ccd[0]
                df['fracday'] = z.fracday[0]
                df['quadrant'] = z.quadrants[0]
                df['MAGZP'] = z.get_header()[0]['MAGZP']
                df['filter'] = z.filter[0]
                dfs.append(df)
            except FileNotFoundError:
                print(f"ziff {i+1} not found")
        return pd.concat(dfs)
    

    def eval_func(self, attr, parallel = False, **kwargs):
        return [getattr(z,attr)(**kwargs) for z in self.ziffs]

    def eval_func_stars(self,attr, stars_list, parallel = False, **kwargs):
        return [getattr(z,attr)(stars = stars_list[i],**kwargs) for (i,z) in enumerate(self.ziffs)]

# End of ziff.py ========================================================
