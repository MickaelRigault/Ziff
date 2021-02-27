
import numpy as np
import pandas
import dask.dataframe as dd

from . import ziffit
from ztfquery import buildurl,io


def _residual_to_skydata_(residuals, buffer=2):
    """ """
    residuals  = residuals.reshape(len(residuals), 15, 15)
    residuals[:, buffer:-buffer,buffer:-buffer] = np.NaN
    median_sky = np.median(residuals, axis=0)
    means      = np.nanmean(residuals, axis=(1,2))
    stds       = np.nanstd(residuals, axis=(1,2))
    npoints    =  np.sum(~np.isnan(residuals), axis=(1,2))
    return median_sky,[means, stds, npoints]

def _fetch_residuals_(metadataframe, datakey='stars'):
    """ """
    # Slowest function
    fgroups = metadataframe.groupby("filename")
    datas = []
    for filename in list(fgroups.groups.keys()):
        source = fgroups.get_group(filename)["Source"].values
        fdata  = pandas.read_parquet(io.get_file(filename, suffix="psfshape.parquet", check_suffix=False),
                        columns=[datakey]).loc[source].values.tolist()
        datas.append(fdata)
        
    return np.squeeze(np.concatenate(datas))

def _fetch_filesource_data_(filename, datakey, sources=None):
    """ """
    data    = pandas.read_parquet(io.get_file(filename, suffix="psfshape.parquet", check_suffix=False),
                                    columns=[datakey])
    if sources is not None:
        data = data.loc[sources]
        
    return data.values.tolist()
    


def _fetch_data_of_filegroup_(dataframegroup, datakey="stars"):
    """ """
    filename = dataframegroup["filename"].iloc[0] # all the same
    sources  = dataframegroup["Source"].unique() # unclear
    fdata    = pandas.read_parquet(io.get_file(filename, suffix="psfshape.parquet", check_suffix=False),
                                    columns=[datakey]).loc[sources].values.tolist()
    return fdata



class PSFShapeAnalysis( object ):
    """ """
    def __init__(self):
        """ """
        
    @classmethod
    def from_directory(cls, directory, patern="*.parquet", urange=None, vrange=None, bins=None):
        """ """
        import os
        this = cls()
        data = dd.read_parquet(os.path.join(directory,patern))
        this.set_data(data, urange=urange, vrange=vrange, bins=bins)
        return this
        
    # --------- #
    #  SETTER   #
    # --------- #
    def set_client(self, client, persist=True):
        """ """
        self._client = client
        if self.has_data() and persist:
            self._data = self.client.persist(self.data)
            
        
    def set_data(self, data, urange=None, vrange=None, bins=None, persist=True):
        """ """
        self._data = data
        self.set_binning(urange=urange, vrange=vrange, bins=bins)
        if "u_digit,v_digit" not in self.data.columns:
            self.data["u_digit,v_digit"] = self.data["u_digit"].astype("str")+","+ self.data["v_digit"].astype("str")

        if persist and self.has_client():
            self._data = client.persist(self.data)

    def set_binning(self, urange, vrange, bins):
        """ """
        self._binning = {"urange":urange, "vrange":vrange, "bins":bins}

    # --------- #
    #  LOADER   #
    # --------- #
    def load_medianserie(self):
        """ """
        self._seriemedian = self.grouped_digit[["sigma_model_n","sigma_data_n","sigma_residual"]
                                              ].apply(pandas.Series.median).compute()

    def load_shapemaps(self):
        """ """
        hist2d = np.ones((4, self.binning["bins"],self.binning["bins"]))*np.NaN
        
        for k,v in self.seriemedian.iterrows():
            hist2d[0, k[1], k[0]] = v["sigma_data_n"]
            hist2d[1, k[1], k[0]] = v["sigma_model_n"]
            hist2d[2, k[1], k[0]] = v["sigma_residual"]

        for k,v in self.grouped_digit.size().compute().iteritems():
            hist2d[3, k[1], k[0]] = v

        self._shapemaps = {"data": hist2d[0],
                           "model": hist2d[1],
                           "residual": hist2d[2],
                           "density": hist2d[3]}
    # --------- #
    #  GETTER   #
    # --------- #
    def get_center_pixel(self):
        """ """
        ucenter = np.median(self.bins_u[~np.all(np.isnan(self.shapemaps["data"]), axis=0)])
        vcenter = np.median(self.bins_v[~np.all(np.isnan(self.shapemaps["data"]), axis=1)])
        return ucenter,vcenter

    def get_metapixels(self, resrange=None, modelrange=None, datarange=None, densityrange=None,
                           within=None, as_string=False):
        """ 
        Parameters
        ----------
        resrange, modelrange, datarange, density: [float, float]
            min value and max value to select the metapixels.
            Applied on residual, model or data map respetively
            e.g. resrange=[-0.1,0.1]
            

        within: [(float, float), float]
            u and v of the centroid + radius (in unit of u and v)
            e.g. within=((3000,-3000), 500)
                 within=(self.get_center_pixel(), 500)

        """
        flag = []
        for key,vrange in zip(
                        ["residual", "model", "data", "density"],
                        [resrange, modelrange, datarange, densityrange]):
            if vrange is not None:
                flag.append( (self.shapemaps[key]>vrange[0]) * (self.shapemaps[key]<vrange[1]))

        if len( flag ) >0:
            mpxl_args = np.argwhere(np.all(flag, axis=0))
        else:
            mpxl_args = None


        if within is not None:
            (ucentroid, vcentroid), dist_ = self.get_center_pixel(), 2000
            if mpxl_args is None:
                ub = self.bins_u-ucentroid
                vb = self.bins_v-vcentroid
                mpxl_args = np.sqrt(ub**2+ vb**2)<dist_
            else:
                ub = self.bins_u[mpxl_args.T[1]]-ucentroid
                vb = self.bins_v[mpxl_args.T[0]]-vcentroid
                mpxl_args = mpxl_args[np.sqrt(ub**2+ vb**2)<dist_]

        if as_string:
             return np.asarray([f"{u_},{v_}" for u_,v_ in mpxl_args])
         
        return mpxl_args


    def get_metapixel_data(self, metapixel, columns=None):
        """ """
        if columns is not None:
            self.data[columns][self.data['u_digit,v_digit'].isin(metapixel)]
        else:
            self.data[self.data['u_digit,v_digit'].isin(metapixel)]
        return data

    def fetch_metapixel_data(self, metapixel, datakey):
        """ """
        subdata = self.get_metapixel_data(metapixel, columns=["Source","filefracday","fieldid","ccdid","qid","filterid"])
        subdata["filename"] = buildurl.build_filename_from_dataframe(subdata)
        
        
    
    def get_metapixel_sources(self, metapixel, columns=["filename", "Source"], compute=True):
        """ """
        metapixeldata = self.grouped_digit.get_group(tuple(metapixel))
        metapixeldata["filename"] = buildurl.build_filename_from_dataframe(metapixeldata)
        if columns is not None and compute:
            return metapixeldata[columns].compute()
        
        return metapixeldata

    # ------------- #
    # Client GETTER #
    # ------------- #
    def cget_median_stampsky(self, metapixels, client, on="stars", buffer=2, gather=True):
        """ 
        Parameters
        ----------
        on: [string] -optional-
            on could be stars or residual
           
        """
        # dmetapixeldata is lazy
        all_meta = []
        for p_ in metapixels:
            metapixeldata = self.grouped_digit[["filefracday","fieldid","ccdid","qid","filterid","Source"]
                                                   ].get_group(tuple(metapixel))
            metapixeldata["filename"] = buildurl.build_filename_from_dataframe(metapixeldata)
        
        dmetapixeldata = [self.get_metapixel_sources(l_, compute=False)
                              for l_ in metapixels]
        # all metapixeldata are computed but still distribution inside the cluster
        # they are 'futures'
        #  They are computed together for the share the same data files
        f_metapixeldata  = client.compute(dmetapixeldata)
        
        # Logic. Then work on the distributed data
        
        # Grab all the stars for each of them. Computation made on the respective cluster's computer
        f_stamps = client.map(_fetch_residuals_, f_metapixeldata, datakey=on)
        
        # Compute the sky study on them
        f_skies = client.map(_residual_to_skydata_, f_stamps, buffer=buffer)

        if gather:
            return client.gather(f_skies)
        
        return f_skies
    # --------- #
    #  PLOTTER  #
    # --------- #
    def show_psfshape_maps(self, savefile=None, vmin="3", vmax="97"):
        """ """
        from ziff.plots import get_threeplot_axes, vminvmax_parser, display_binned2d

        fig, [axd, axm, axr], [cax, caxr] = get_threeplot_axes(fig=None, bottom=0.1, hxspan=0.09)


        vmin, vmax = vminvmax_parser(self.shapemaps["model"][self.shapemaps["model"]==self.shapemaps["model"]], vmin, vmax)

        prop = dict(xbins=self.bins_u, ybins=self.bins_v, transpose=False, 
                    vmin=vmin, vmax=vmax, cmap="coolwarm")

        imd = display_binned2d(axd, self.shapemaps["data"], **prop)
        # -> Model    
        imm = display_binned2d(axm, self.shapemaps["model"], cax=cax, **prop)

        imr = display_binned2d(axr, self.shapemaps["residual"]*100, cax=caxr, 
                                      **{**prop,**{"cmap":"coolwarm",
                                                   "vmin":-0.8,"vmax":+0.8}})
        imr.colorbar.set_ticks([-0.5,0,0.5])
        [ax.set_yticklabels(["" for _ in ax.get_yticklabels()]) for ax in [axm, axr]]


        textprop = dict(fontsize="small", color="0.3", loc="left")
        axd.set_title("data", **textprop)
        axm.set_title("model", **textprop)
        axr.set_title("(data-model)/model [%]", **textprop)
        fig.text(0.5, 0.99, "PSF width (normed per exposure)", va="top", ha="center", weight="bold")
        
        if savefile:
            fig.savefig(savefile, dpi=300)
            
        return fig

    # ================= #
    #    Properties     #
    # ================= #
    @property
    def client(self):
        """ """
        if not self.has_client():
            return None
        return self._client

    def has_client(self):
        """ """
        return hasattr(self, "_client") and self._client is not None
    
    @property
    def data(self):
        """ """
        return self._data

    def has_data(self):
        """ """
        return hasattr(self, "_data") and self._data is not None

    @property
    def grouped_digit(self):
        """ """
        if not hasattr(self,"_grouped_digit") or self._grouped_digit is None:
            self._grouped_digit = self.data.groupby(["u_digit","v_digit"])
            
        return self._grouped_digit

    @property
    def seriemedian(self):
        """ """
        if not hasattr(self,"_seriemedian") or self._seriemedian is None:
            self.load_medianserie()
            
        return self._seriemedian
    
    @property
    def shapemaps(self):
        """ """
        if not hasattr(self,"_shapemaps") or self._shapemaps is None:
            self.load_shapemaps()
            
        return self._shapemaps
    
    @property
    def binning(self):
        """ """
        return self._binning
    
    @property
    def bins_u(self):
        """ """
        return np.linspace(*self.binning["urange"], self.binning["bins"])

    @property
    def bins_v(self):
        """ """
        return np.linspace(*self.binning["vrange"], self.binning["bins"])
