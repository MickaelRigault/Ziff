#!/usr/bin/env python
# -*- coding: utf-8 -*-
################################################################################
# Filename:          download_query.py
# Description:       script description
# Author:            Romain Graziani <romain.graziani@clermont.in2p3.fr>
# Author:            $Author: rgraziani $
# Created on:        $Date: 2020/09/25 16:23:01 $
# Modified on:       2020/10/09 11:28:22
# Copyright:         2019, Romain Graziani
# $Id: download_query.py, 2020/09/25 16:23:01  RG $
################################################################################

"""
.. _download_query.py:

download_query.py
==============


"""
__license__ = "2019, Romain Graziani"
__docformat__ = 'reStructuredText'
__author__ = 'Romain Graziani <romain.graziani@clermont.in2p3.fr>'
__date__ = '2020/09/25 16:23:01'
__adv__ = 'download_query.py'

import argparse

print("ziff download_target is deprecated. Use 'irsa_query.py --target' instead.")


parser = argparse.ArgumentParser()
parser.add_argument("--target",type=str,default = "ZTF19aanbojt")
parser.add_argument("--overwrite",type=int,default = 1)
parser.add_argument("--nprocess",type=int,default = 1)
parser.add_argument("--priorcreation",type=int,default = 300)
parser.add_argument("--postlast",type=int,default = 300)



args = parser.parse_args()

from ztfquery import marshal
from ztfquery import query

m = marshal.MarshalAccess.load_local()
zquery = query.ZTFQuery()
zquery.load_metadata(kind = 'sci', **m.get_target_metadataquery(args.target, priorcreation = args.priorcreation, postlast = args.postlast))
print(zquery.metatable)
keys = ['sciimg.fits', 'mskimg.fits', 'psfcat.fits']
for _key in keys:
    zquery.download_data(_key,show_progress=True, notebook=False, nprocess=args.nprocess, overwrite = bool(args.overwrite))
        

# End of download_query.py ========================================================
