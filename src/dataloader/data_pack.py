# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import os
import random
import numpy as np

import torch

from src.dataloader.reader_colmap_dataset import read_colmap_dataset
from src.dataloader.reader_nerf_dataset import read_nerf_dataset

from src.cameras import Camera, MiniCam


class DataPack:

    def __init__(self,
                 source_path,
                 image_dir_name="images",
                 res_downscale=0.,
                 res_width=0,
                 skip_blend_alpha=False,
                 alpha_is_white=False,
                 data_device="cpu",
                 use_test=False,
                 test_every=8,
                 camera_params_only=False):

        camera_creator = CameraCreator(
            res_downscale=res_downscale,
            res_width=res_width,
            skip_blend_alpha=skip_blend_alpha,
            alpha_is_white=alpha_is_white,
            data_device=data_device,
            camera_params_only=camera_params_only,
        )

        sparse_path = os.path.join(source_path, "sparse")
        colmap_path = os.path.join(source_path, "colmap", "sparse")
        meta_path1 = os.path.join(source_path, "transforms_train.json")
        meta_path2 = os.path.join(source_path, "transforms.json")

        # TODO: read camera by multithreading

        if os.path.exists(sparse_path) or os.path.exists(colmap_path):
            print("Read dataset in COLMAP format.")
            dataset = read_colmap_dataset(
                source_path=source_path,
                image_dir_name=image_dir_name,
                use_test=use_test,
                test_every=test_every,
                camera_creator=camera_creator)
        elif os.path.exists(meta_path1) or os.path.exists(meta_path2):
            print("Read dataset in NeRF format.")
            dataset = read_nerf_dataset(
                source_path=source_path,
                use_test=use_test,
                test_every=test_every,
                camera_creator=camera_creator)
        else:
            raise Exception("Unknown scene type!")

        self._cameras = {
            'train': dataset['train_cam_lst'],
            'test': dataset['test_cam_lst'],
        }

        ##############################
        # Read additional dataset info
        ##############################
        # If the dataset suggested a scene bound
        self.suggested_bounding = dataset.get('suggested_bounding', None)

        # If the dataset provide a transformation to other coordinate
        self.to_world_matrix = None
        to_world_path = os.path.join(source_path, 'to_world_matrix.txt')
        if os.path.isfile(to_world_path):
            self.to_world_matrix = np.loadtxt(to_world_path)

        # If the dataset has a point cloud
        self.point_cloud = dataset.get('point_cloud', None)

    def get_train_cameras(self):
        return self._cameras['train']

    def get_test_cameras(self):
        return self._cameras['test']


# Create a random sequence of image indices
def compute_iter_idx(num_data, num_iter):
    tr_iter_idx = []
    while len(tr_iter_idx) < num_iter:
        lst = list(range(num_data))
        random.shuffle(lst)
        tr_iter_idx.extend(lst)
    return tr_iter_idx[:num_iter]


# Function that create Camera instances while parsing dataset
class CameraCreator:

    warned = False

    def __init__(self,
                 res_downscale=0.,
                 res_width=0,
                 skip_blend_alpha=False,
                 alpha_is_white=False,
                 data_device="cpu",
                 camera_params_only=False):

        self.res_downscale = res_downscale
        self.res_width = res_width
        self.skip_blend_alpha = skip_blend_alpha
        self.alpha_is_white = alpha_is_white
        self.data_device = data_device
        self.camera_params_only = camera_params_only

    def __call__(self,
                 image,
                 w2c,
                 fovx,
                 fovy,
                 cx_p=0.5,
                 cy_p=0.5,
                 sparse_pt=None,
                 image_name=""):

        if self.camera_params_only:
            return MiniCam(
                c2w=np.linalg.inv(w2c),
                fovx=fovx, fovy=fovy,
                cx_p=cx_p, cy_p=cy_p,
                width=image.size[0],
                height=image.size[1],
                image_name=image_name)

        # Determine target resolution
        if self.res_downscale > 0:
            downscale = self.res_downscale
        elif self.res_width > 0:
            downscale = image.size[0] / self.res_width
        else:
            downscale = 1

            total_pix = image.size[0] * image.size[1]
            if total_pix > 1200 ** 2 and not self.warned:
                self.warned = True
                suggest_ds = (total_pix ** 0.5) / 1200
                print(f"###################################################################")
                print(f"Image too large. Suggest to use `--res_downscale {suggest_ds:.1f}`.")
                print(f"###################################################################")

        # Resize image if needed
        if downscale != 1:
            image = image.resize(round(image.size[0] / downscale), round(image.size[1] / downscale))

        # Convert image to tensor
        tensor = torch.tensor(np.array(image), dtype=torch.float32).moveaxis(-1, 0) / 255.0
        if tensor.shape[0] == 4:
            # Blend alpha channel
            tensor, mask = tensor.split([3, 1], dim=0)
            if not self.skip_blend_alpha:
                tensor = tensor * mask + int(self.alpha_is_white) * (1 - mask)

        return Camera(
            w2c=w2c,
            fovx=fovx, fovy=fovy,
            cx_p=cx_p, cy_p=cy_p,
            image=tensor,
            sparse_pt=sparse_pt,
            image_name=image_name)
