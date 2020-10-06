#!/usr/bin/env python
# -*- coding: utf-8 -*-
################################################################################
# Filename:          stats.py
# Description:       script description
# Author:            Romain Graziani <romain.graziani@clermont.in2p3.fr>
# Author:            $Author: rgraziani $
# Created on:        $Date: 2020/10/02 10:48:39 $
# Modified on:       2020/10/05 17:06:13
# Copyright:         2019, Romain Graziani
# $Id: stats.py, 2020/10/02 10:48:39  RG $
################################################################################

"""
.. _stats.py:

stats.py
==============


"""
__license__ = "2019, Romain Graziani"
__docformat__ = 'reStructuredText'
__author__ = 'Romain Graziani <romain.graziani@clermont.in2p3.fr>'
__date__ = '2020/10/02 10:48:39'
__adv__ = 'stats.py'


import numpy as np
from scipy.stats import binned_statistic_2d, binned_statistic
import matplotlib.pyplot as plt
from .plots import make_focal_plane, get_ax_ccd, get_ax_cbar

class BinnedStatistic(object):
    def __init__(self, shapes, nbins = 20, groupby = ['ccd']):
        self._nbins = nbins
        self._shapes = shapes
        self._filters = {}
        self.add_filter('flag_data', [0,1])
        self.add_filter('flag_model', [0,1])
        self._groupby = shapes.groupby(groupby)

    def add_filter(self, key, range, name = None):
        if name is None:
            name = key
        self._filters[name] = {'key': key, 'range' : range}

    def get_flag(self, df = None):
        if df is None:
            df = self._shapes
        flag = np.ones(np.size(df,axis=0))
        for f in self._filters.values():
            flag *= (df[f['key']].values < f['range'][1]) * (df[f['key']].values >= f['range'][0])
        return flag.astype(bool)

    def scatter_plot_group(self, group, key = 'T_data', **kwargs):
        group = self._groupby.get_group(group)
        flag = self.get_flag(group)
        group = group[flag]
        fig, ax = plt.subplots()
        scat_kwargs = {'cmap':'RdBu_r', 's':50, 'vmin':0.9, 'vmax':1.1}
        s = ax.scatter(group['u'],group['v'],c=np.asarray(group[key]),**{**scat_kwargs,**kwargs})
        fig.colorbar(s,ax=ax)
        return fig, ax
    
    def compute_groupby_statistic(self, key = 'T_data', statistic = 'mean'):
        return getattr(getattr(self._groupby,key),statistic)()

    def compute_transform(self, key = 'T_data', statistic = 'mean'):
        return getattr(self._groupby,key).transform(statistic)
    
    def set_nbins(self, nbins):
        self._nbins = nbins

    def get_1d_hist(self, x, values, statistic = 'median'):
        if isinstance(x,str):
            x = self._shapes[x]
        bins = np.linspace(np.min(x),np.max(x),self.nbins)
        return bins, binned_statistic(x, values, statistic = statistic, bins = bins)

    def get_normalization(self, df = None,  norm_key = None , norm_groupby = ['fracday','ccd'], norm_stat = 'median'):
        if df is None:
            df =  self._shapes
        return getattr(df.groupby(norm_groupby),norm_key).transform(norm_stat).values
    
    def get_group_1d_hist(self, x, key, group,  statistic = 'median', norm_key = None , norm_groupby = ['fracday','ccd'], norm_stat = 'median', **kwargs):
        group = self._groupby.get_group(group)
        flag = self.get_flag(group)
        group = group[flag]
        if isinstance(x,str):
            x = group[x]
        if norm_key is not None:
            normalization = self.get_normalization(group, norm_key, norm_groupby, norm_stat)
        else:
            normalization  = 1
        return self.get_1d_hist(x, group[key].values/normalization, statistic = statistic)


    def get_uv_hist(self, u, v, data, statistic = 'median'):
        bins_u, bins_v = self.get_bins(u,v)
        return bins_u, bins_v, binned_statistic_2d(u, v, data, statistic=statistic, bins=[bins_u,bins_v]).statistic

    def get_group_uv_hist(self, key, group, statistic = 'median', norm_key = None , norm_groupby = ['fracday','ccd'], norm_stat = 'median'):
        group = self._groupby.get_group(group)
        flag = self.get_flag(group)
        group = group[flag]
        if norm_key is not None:
            normalization = self.get_normalization(group, norm_key, norm_groupby, norm_stat)
        else:
            normalization  = 1
        return self.get_uv_hist(group['u'].values, group['v'].values, group[key].values/normalization, statistic = statistic)

    def show_focal_plane(self, key, label = '', imshow_kwargs = {}, **hist_kwargs):
        fig, gs = make_focal_plane()
        for ccd in range(1,17):
            ax, i, j = get_ax_ccd(fig, gs, ccd)
            bins_u, bins_v, hist = self.get_group_uv_hist(key, ccd, **hist_kwargs)
            default_imshow_kwargs =  {'cmap' : 'viridis', 'origin':'lower', 'extent' : (bins_u[0],bins_u[-1],bins_v[0],bins_v[-1])}
            im = ax.imshow(hist.T, **{**default_imshow_kwargs,**imshow_kwargs})
            if i<3:
                ax.get_xaxis().set_visible(False)
            if j>0:
                ax.get_yaxis().set_visible(False)
        
        cbar_ax = get_ax_cbar(fig,gs)
        cbar = fig.colorbar(im, cax=cbar_ax)
        cbar.set_label(label,rotation = 270)

        return fig, gs

    def get_bins(self, u, v):
        bins_u = np.linspace(np.min(u),np.max(u),self.nbins)
        bins_v = np.linspace(np.min(v),np.max(v),self.nbins)
        return bins_u, bins_v

    @property
    def nbins(self):
        return self._nbins
    
    @property
    def groups(self):
        return self._groupby.groups

    
    
# End of stats.py ========================================================
