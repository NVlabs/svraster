# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import torch
import svraster_cuda

from src.utils.activation_utils import rgb2shzero
from src.utils import octree_utils

class SVConstructor:

    def model_init(self,
                   bounding,           # Scene bound [min_xyz, max_xyz]
                   outside_level,      # Number of Octree levels for background
                   init_n_level=6,     # Starting from (2^init_n_level)^3 voxels
                   init_out_ratio=2.0, # Number of voxel ratio for outside (background region)
                   sh_degree_init=3,   # Initial activated sh degree
                   geo_init=-10.0,     # Init pre-activation density
                   sh0_init=0.5,       # Init voxel colors in range [0,1]
                   shs_init=0.0,       # Init coefficients of higher-degree sh
                   cameras=None,       # Cameras that helps voxel allocation
                   ):

        assert outside_level <= svraster_cuda.meta.MAX_NUM_LEVELS

        # Define scene bound
        center = (bounding[0] + bounding[1]) * 0.5
        radius = (bounding[1] - bounding[0]) * 0.5
        self.scene_center = torch.tensor(center, dtype=torch.float32, device="cuda")
        self.inside_extent = 2 * torch.tensor(max(radius), dtype=torch.float32, device="cuda")
        self.scene_extent = self.inside_extent * (2 ** outside_level)

        # Init voxel layout.
        # The world is seperated into inside (main foreground) and outside (background) regions.
        in_path, in_level = octlayout_inside_uniform(
            scene_center=self.scene_center,
            scene_extent=self.scene_extent,
            outside_level=outside_level,
            n_level=init_n_level,
            cameras=cameras,
            filter_zero_visiblity=True,
            filter_near=-1)

        if outside_level == 0:
            # Object centric bounded scenes
            ou_path = torch.empty([0, 1], dtype=in_path.dtype, device="cuda")
            ou_level = torch.empty([0, 1], dtype=in_level.dtype, device="cuda")
        else:
            min_num = len(in_path) * init_out_ratio
            max_level = outside_level + init_n_level
            ou_path, ou_level = octlayout_outside_heuristic(
                scene_center=self.scene_center,
                scene_extent=self.scene_extent,
                outside_level=outside_level,
                cameras=cameras,
                min_num=min_num,
                max_level=max_level,
                filter_near=-1)

        self.octpath = torch.cat([ou_path, in_path])
        self.octlevel = torch.cat([ou_level, in_level])

        self.vox_center, self.vox_size = octree_utils.octpath_decoding(
            self.octpath, self.octlevel, self.scene_center, self.scene_extent)
        self.grid_pts_key, self.vox_key = octree_utils.build_grid_pts_link(self.octpath, self.octlevel)

        self.active_sh_degree = min(sh_degree_init, self.max_sh_degree)

        # Init trainable parameters
        self._geo_grid_pts = torch.full(
            [self.num_grid_pts, 1], geo_init,
            dtype=torch.float32, device="cuda").requires_grad_()

        self._sh0 = torch.full(
            [self.num_voxels, 3], rgb2shzero(sh0_init),
            dtype=torch.float32, device="cuda").requires_grad_()

        self._shs = torch.full(
            [self.num_voxels, (self.max_sh_degree+1)**2 - 1, 3], shs_init,
            dtype=torch.float32, device="cuda").requires_grad_()

        # Subdivision priority trackor
        self._subdiv_p = torch.ones(
            [self.num_voxels, 1],
            dtype=torch.float32, device="cuda").requires_grad_()
        self.subdiv_meta = torch.zeros(
            [self.num_voxels, 1],
            dtype=torch.float32, device="cuda")


#################################################
# Initial Octree layout construction
#################################################
def octlayout_filtering(octpath, octlevel, scene_center, scene_extent, cameras=None, filter_zero_visiblity=True, filter_near=-1):

    vox_center, vox_size = octree_utils.octpath_decoding(
        octpath, octlevel,
        scene_center, scene_extent)

    # Filtering
    kept_mask = torch.ones([len(octpath)], dtype=torch.bool, device="cuda")
    if filter_zero_visiblity:
        assert cameras is not None, "Cameras should be given to filter invisible voxels"
        rate = svraster_cuda.renderer.mark_max_samp_rate(
            cameras, octpath, vox_center, vox_size)
        kept_mask &= (rate > 0)
    if filter_near > 0:
        is_near = svraster_cuda.renderer.mark_near(
            cameras, octpath, vox_center, vox_size, near=filter_near)
        kept_mask &= (~is_near)
    kept_idx = torch.where(kept_mask)[0]
    octpath = octpath[kept_idx]
    octlevel = octlevel[kept_idx]
    return octpath, octlevel


def octlayout_inside_uniform(scene_center, scene_extent, outside_level, n_level, cameras=None, filter_zero_visiblity=True, filter_near=-1):
    octpath, octlevel = octree_utils.gen_octpath_dense(
        outside_level=outside_level,
        n_level_inside=n_level)

    octpath, octlevel = octlayout_filtering(
        octpath=octpath,
        octlevel=octlevel,
        scene_center=scene_center,
        scene_extent=scene_extent,
        cameras=cameras,
        filter_zero_visiblity=filter_zero_visiblity,
        filter_near=filter_near)
    return octpath, octlevel


def octlayout_outside_heuristic(scene_center, scene_extent, outside_level, cameras, min_num, max_level, filter_near=-1):

    assert cameras is not None, "Cameras should provided in this mode."

    # Init by adding one sub-level in each shell level
    octpath = []
    octlevel = []
    for lv in range(1, 1+outside_level):
        path, lv = octree_utils.gen_octpath_shell(
            shell_level=lv,
            n_level_inside=1)
        octpath.append(path)
        octlevel.append(lv)
    octpath = torch.cat(octpath)
    octlevel = torch.cat(octlevel)

    # Iteratively subdivide voxels with maximum sampling rate
    while True:
        vox_center, vox_size = octree_utils.octpath_decoding(
            octpath, octlevel, scene_center, scene_extent)
        samp_rate = svraster_cuda.renderer.mark_max_samp_rate(
            cameras, octpath, vox_center, vox_size)

        kept_idx = torch.where((samp_rate > 0))[0]
        octpath = octpath[kept_idx]
        octlevel = octlevel[kept_idx]
        octlevel_mask = (octlevel.squeeze(1) < max_level)
        samp_rate = samp_rate[kept_idx] * octlevel_mask
        vox_size = vox_size[kept_idx]
        still_need_n = (min_num - len(octpath)) // 7
        still_need_n = min(len(octpath), round(still_need_n))
        if still_need_n <= 0:
            break
        rank = samp_rate * (octlevel.squeeze(1) < svraster_cuda.meta.MAX_NUM_LEVELS)
        subdiv_mask = (rank >= rank.sort().values[-still_need_n])
        subdiv_mask &= (octlevel.squeeze(1) < svraster_cuda.meta.MAX_NUM_LEVELS)
        subdiv_mask &= octlevel_mask
        samp_rate *= subdiv_mask
        subdiv_mask &= (samp_rate >= samp_rate.quantile(0.9))  # Subdivide only 10% each iteration
        if subdiv_mask.sum() == 0:
            break
        octpath_children, octlevel_children = octree_utils.gen_children(
            octpath[subdiv_mask], octlevel[subdiv_mask])
        octpath = torch.cat([octpath[~subdiv_mask], octpath_children])
        octlevel = torch.cat([octlevel[~subdiv_mask], octlevel_children])

    octpath, octlevel = octlayout_filtering(
        octpath=octpath,
        octlevel=octlevel,
        scene_center=scene_center,
        scene_extent=scene_extent,
        cameras=cameras,
        filter_zero_visiblity=True,
        filter_near=filter_near)
    return octpath, octlevel
