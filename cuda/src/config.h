/*************************************************************************
Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.

NVIDIA CORPORATION and its licensors retain all intellectual property
and proprietary rights in and to this software, related documentation
and any modifications thereto.  Any use, reproduction, disclosure or
distribution of this software and related documentation without an express
license agreement from NVIDIA CORPORATION is strictly prohibited.
*************************************************************************/

#ifndef RASTERIZER_CONFIG_H_INCLUDED
#define RASTERIZER_CONFIG_H_INCLUDED

#define BLOCK_X 16
#define BLOCK_Y 16
#define MAX_NUM_LEVELS 16
#define MAX_ALPHA 0.99999f
#define MIN_ALPHA 0.00001f
#define EARLY_STOP_T 0.0001f

#define STEP_SZ_SCALE 100.f

#define MAX_N_SAMP 3

// Below are the derived term from above
#define BLOCK_SIZE (BLOCK_X * BLOCK_Y)
#define NUM_BIT_ORDER_RANK (3 * MAX_NUM_LEVELS)
#define NUM_BIT_TILE_ID (64 - NUM_BIT_ORDER_RANK)

#endif
