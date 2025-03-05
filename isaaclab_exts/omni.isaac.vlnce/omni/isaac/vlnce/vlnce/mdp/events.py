import torch

import omni.isaac.lab.sim as sim_utils
import omni.isaac.lab.utils.math as math_utils
from omni.isaac.lab.actuators import ImplicitActuator
from omni.isaac.lab.assets import Articulation, RigidObject
from omni.isaac.lab.managers import SceneEntityCfg
from omni.isaac.lab.terrains import TerrainImporter


from omni.isaac.lab.envs import ManagerBasedEnv


def reset_camera_pos_uniform(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor,
    asset_cfg: SceneEntityCfg,
    pose_delta_range: dict[str, tuple[float, float]],
):
    """Reset the camera to a random position uniformly within the given ranges.

    This function randomizes the position of the asset.

    * It samples the delta position from the given ranges and adds them to the default camera position, before setting
      them into the physics simulation.
    * It samples the root orientation from the given ranges and sets them into the physics simulation.
    * It samples the root velocity from the given ranges and sets them into the physics simulation.

    The function takes a dictionary of pose and velocity ranges for each axis and rotation. The keys of the
    dictionary are ``x``, ``y``, ``z``, ``roll``, ``pitch``, and ``yaw``. The values are tuples of the form
    ``(min, max)``. If the dictionary does not contain a key, the position or velocity is set to zero for that axis.
    """
    # extract the used quantities (to enable type-hinting)
    camera: RigidObject | Articulation = env.scene[asset_cfg.name]
    # get default root state
    pos_w, quat_w = camera._compute_view_world_poses(env_ids)

    # poses
    range_list = [pose_delta_range.get(key, (0.0, 0.0)) for key in ["x", "y", "z", "roll", "pitch", "yaw"]]
    ranges = torch.tensor(range_list, device=camera.device)
    rand_samples = math_utils.sample_uniform(ranges[:, 0], ranges[:, 1], (len(env_ids), 6), device=camera.device)

    positions = pos_w + rand_samples[:, 0:3]
    orientations_delta = math_utils.quat_from_euler_xyz(rand_samples[:, 3], rand_samples[:, 4], rand_samples[:, 5])
    orientations = math_utils.quat_mul(quat_w, orientations_delta)

    # set into the physics simulation
    camera.set_world_poses(positions, orientations, env_ids=env_ids, convention="world")