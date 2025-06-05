# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

from src.sparse_voxel_gears.constructor import SVConstructor
from src.sparse_voxel_gears.properties import SVProperties
from src.sparse_voxel_gears.renderer import SVRenderer
from src.sparse_voxel_gears.adaptive import SVAdaptive
from src.sparse_voxel_gears.optimizer import SVOptimizer
from src.sparse_voxel_gears.io import SVInOut
from src.sparse_voxel_gears.pooling import SVPooling


class SparseVoxelModel(SVConstructor, SVProperties, SVRenderer, SVAdaptive, SVOptimizer, SVInOut, SVPooling):

    def __init__(self,
                 n_samp_per_vox=1,       # Number of sampled points per visited voxel
                 sh_degree=3,            # Use 3 * (k+1)^2 params per voxels for view-dependent colors
                 ss=1.5,                 # Super-sampling rates for anti-aliasing
                 white_background=False, # Assum white background
                 black_background=False, # Assum black background
                 ):
        '''
        Setup of the model. The config is defined by `cfg.model` in `src/config.py`.
        After the initial setup. There are two ways to instantiate the models:

        1. `model_load` defined in `src/sparse_voxel_gears/io.py`.
           Load the saved models from a given path.

        2. `model_init` defined in `src/sparse_voxel_gears/constructor.py`.
           Heuristically initial the sparse grid layout and parameters from the training datas.
        '''
        super().__init__()
        self.n_samp_per_vox = n_samp_per_vox
        self.max_sh_degree = sh_degree
        self.ss = ss
        self.white_background = white_background
        self.black_background = black_background

        # List the variable names
        self.per_voxel_attr_lst = [
            'octpath', 'octlevel',
            'vox_center', 'vox_size',
            'subdiv_meta',
        ]
        self.per_voxel_param_lst = [
            '_sh0', '_shs', '_subdiv_p',
        ]
        self.grid_pts_param_lst = [
            '_geo_grid_pts',
        ]
        self.state_attr_names = ['exp_avg', 'exp_avg_sq']

        # To be init from model_init
        self.scene_center = None
        self.scene_extent = None
        self.inside_extent = None
        self.octpath = None
        self.octlevel = None
        self.vox_center = None
        self.vox_size = None
        self.grid_pts_key = None
        self.vox_key = None
        self.active_sh_degree = sh_degree

        self._geo_grid_pts = None
        self._sh0 = None
        self._shs = None
        self._subdiv_p = None
        self.subdiv_meta = None
