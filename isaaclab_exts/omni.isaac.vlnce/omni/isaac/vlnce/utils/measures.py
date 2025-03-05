from typing import Any, Dict, List, Optional, Tuple, Union
from numpy import ndarray

import numpy as np
from scipy.spatial import KDTree


def euclidean_distance(
    pos_a: Union[List[float], ndarray], pos_b: Union[List[float], ndarray]
) -> float:
    return np.linalg.norm(np.array(pos_b) - np.array(pos_a), ord=2)


class Measure:
    """Represents a measure that provides measurement on top of environment
    and task.

    :data _metric: metric for the :ref:`Measure`, this has to be updated with
        each :ref:`step() <env.Env.step()>` call on :ref:`env.Env`.

    This can be used for tracking statistics when running experiments. The
    user of this class needs to implement the :ref:`reset_metric()` and
    :ref:`update_metric()` method

    """

    _metric: Any
    uuid: str

    def __init__(self, env, episode, **kwargs: Any) -> None:
        self._env = env
        self._episode = episode
        self._metric = None

    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError

    def reset_metric(self, *args: Any, **kwargs: Any) -> None:
        """Reset the metric for :ref:`Measure`"""
        raise NotImplementedError

    def update_metric(self, *args: Any, **kwargs: Any) -> None:
        r"""Update :ref:`_metric`, this method is called from :ref:`env.Env`
        on each :ref:`step() <env.Env.step()>`
        """
        raise NotImplementedError

    def get_metric(self):
        r"""..

        :return: the current metric for :ref:`Measure`.
        """
        return self._metric
    
    def get_robot_position(self):
        robot_pos_w = self._env.unwrapped.scene["robot"].data.root_pos_w[0].detach().cpu().numpy()
        return robot_pos_w
    

class MeasureManager:
    """A manager class for handling different measures and dependencies."""
    def __init__(self):
        self.measures = {}

    def register_measure(self, measure):
        """Register a new measure."""
        self.measures[measure._get_uuid()] = measure

    def get_measure(self, measure_uuid):
        """Get a measure by its uuid."""
        return self.measures.get(measure_uuid)

    def check_measure_dependencies(self, measure_uuid, dependencies):
        """
        Check if all required dependencies for the measure are initialized.
        :param measure_uuid: The UUID of the measure being checked.
        :param dependencies: List of dependent measure UUIDs.
        """
        for dependency_uuid in dependencies:
            if dependency_uuid not in self.measures:
                raise Exception(f"Dependency {dependency_uuid} is missing for measure {measure_uuid}.")
            
    def reset_measures(self, *args: Any, **kwargs: Any):
        """Reset all measures."""
        for measure in self.measures.values():
            measure.reset_metric(*args, **kwargs)
    
    def update_measures(self, *args: Any, **kwargs: Any):
        """Update all measures."""
        for measure in self.measures.values():
            measure.update_metric(*args, **kwargs)

    def get_measurements(self):
        """Get metrics for all measures."""
        return {measure._get_uuid(): measure.get_metric() for measure in self.measures.values()}

    

class PathLength(Measure):
    """Path Length (PL)
    PL = sum(geodesic_distance(agent_prev_position, agent_position)
            over all agent positions.
    """

    cls_uuid: str = "path_length"

    def __init__(self, env, episode, measure_manager, **kwargs: Any):
        super().__init__(env, episode, **kwargs)
        self.measure_manager = measure_manager

    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        return self.cls_uuid

    def reset_metric(self, *args: Any, **kwargs: Any):
        self._previous_position = self.get_robot_position()
        self._metric = 0.0

    def update_metric(self, *args: Any, **kwargs: Any):
        current_position = self.get_robot_position()
        self._metric += euclidean_distance(
            current_position, self._previous_position
        )
        self._previous_position = current_position


class DistanceToGoal(Measure):
    """The measure calculates a distance towards the goal."""

    cls_uuid: str = "distance_to_goal"

    def __init__(
        self, env, episode, *args: Any, **kwargs: Any
    ):
        super().__init__(env, episode, **kwargs)

        self._previous_position: Optional[Tuple[float, float, float]] = None
        self._gt_waypoints: Optional[
            List[Tuple[float, float, float]]
        ] = episode["gt_locations"]
        self._kdtree = KDTree(self._gt_waypoints)
    
    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        return self.cls_uuid

    def reset_metric(self, *args: Any, **kwargs: Any):
        self._previous_position = None
        self.update_metric(*args, **kwargs)  # type: ignore

    def distance_to_goal(self, current_position):
        
        # Find the closest waypoint to the current position
        closest_distance, closest_waypoint_idx = self._kdtree.query(current_position)
        
        # Initialize the total distance with the distance from the robot to the closest waypoint
        total_distance = closest_distance
        
        # Add the distance between waypoints from the closest waypoint to the goal
        for i in range(closest_waypoint_idx, len(self._gt_waypoints) - 1):
            total_distance += euclidean_distance(self._gt_waypoints[i], self._gt_waypoints[i + 1])
    
        return total_distance

    def update_metric(self, *args: Any, **kwargs: Any):
        current_position = self.get_robot_position()

        if self._previous_position is None or not np.allclose(
            self._previous_position, current_position, atol=1e-4
        ):
            distance_to_target = self.distance_to_goal(current_position)

            self._previous_position = (
                current_position[0],
                current_position[1],
                current_position[2],
            )
            self._metric = distance_to_target


class SPL(Measure):
    r"""SPL (Success weighted by Path Length)

    ref: On Evaluation of Embodied Agents - Anderson et. al
    https://arxiv.org/pdf/1807.06757.pdf
    The measure depends on Distance to Goal measure and Success measure
    to improve computational
    performance for sophisticated goal areas.
    """

    cls_uuid: str = "spl"

    def __init__(self, env, episode, measure_manager: MeasureManager, *args: Any, **kwargs: Any):
        super().__init__(env, episode)
        self.measure_manager = measure_manager
        self._previous_position: Union[None, np.ndarray, List[float]] = None
        self._start_end_episode_distance: Optional[float] = None
        self._agent_episode_distance: Optional[float] = None
        self._episode_view_points: Optional[
            List[Tuple[float, float, float]]
        ] = None

    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        return self.cls_uuid

    def reset_metric(self, *args: Any, **kwargs: Any):

        self._previous_position = self.get_robot_position()
        self._agent_episode_distance = 0.0
        self._start_end_episode_distance = self.measure_manager.measures[
            DistanceToGoal.cls_uuid
        ].get_metric()
        self.update_metric(  # type:ignore
            measure_manager=self.measure_manager,
            *args, **kwargs
        )

    def _euclidean_distance(self, position_a, position_b):
        return np.linalg.norm(position_b - position_a, ord=2)

    def update_metric(
        self, *args: Any, **kwargs: Any
    ):
        ep_success = self.measure_manager.measures[Success.cls_uuid].get_metric()

        current_position = self.get_robot_position()
        self._agent_episode_distance += euclidean_distance(
            current_position, self._previous_position
        )

        self._previous_position = current_position

        self._metric = ep_success * (
            self._start_end_episode_distance
            / max(
                self._start_end_episode_distance, self._agent_episode_distance
            )
        )


class Success(Measure):
    r"""Whether or not the agent succeeded at its task

    This measure depends on DistanceToGoal measure.
    """

    cls_uuid: str = "success"

    def __init__(self, env, episode, measure_manager, *args: Any, **kwargs: Any):
        super().__init__(env, episode)
        self._success_distance = episode["goals"][0]["radius"]
        self.measure_manager = measure_manager

    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        return self.cls_uuid

    def reset_metric(self, *args: Any, **kwargs: Any):
        self.update_metric(*args, **kwargs)  # type: ignore
        setattr(self._env, "is_stop_called", False)

    def update_metric(self, *args: Any, **kwargs: Any):
        distance_to_target = self.measure_manager.measures[
            DistanceToGoal.cls_uuid
        ].get_metric()

        if (
            hasattr(self._env, "is_stop_called")
            and self._env.is_stop_called  # type: ignore
            and distance_to_target < self._success_distance
        ):
            self._metric = 1.0
        else:
            self._metric = 0.0


class OracleNavigationError(Measure):
    """Oracle Navigation Error (ONE)
    ONE = min(geosdesic_distance(agent_pos, goal)) over all points in the
    agent path.
    """

    cls_uuid: str = "oracle_navigation_error"

    def __init__(self, env, episode, measure_manager, *args: Any, **kwargs: Any):
        super().__init__(env, episode)
        self.measure_manager = measure_manager

    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        return self.cls_uuid

    def reset_metric(self, *args: Any, **kwargs: Any):
        self.measure_manager.check_measure_dependencies(
            self.cls_uuid, [DistanceToGoal.cls_uuid]
        )
        self._metric = float("inf")
        self.update_metric()

    def update_metric(self, *args: Any, **kwargs: Any):
        distance_to_target = self.measure_manager.measures[
            DistanceToGoal.cls_uuid
        ].get_metric()
        self._metric = min(self._metric, distance_to_target)


class OracleSuccess(Measure):
    """Oracle Success Rate (OSR). OSR = I(ONE <= goal_radius)"""

    cls_uuid: str = "oracle_success"

    def __init__(self, env, episode, measure_manager: MeasureManager, *args: Any, **kwargs: Any):
        super().__init__(env, episode)
        self.measure_manager = measure_manager
        self._success_distance = episode["goals"][0]["radius"]

    def _get_uuid(self, *args: Any, **kwargs: Any) -> str:
        return self.cls_uuid

    def reset_metric(self, *args: Any, **kwargs: Any):
        self.measure_manager.check_measure_dependencies(
            self.cls_uuid, [DistanceToGoal.cls_uuid]
        )
        self._metric = 0.0
        self.update_metric()

    def update_metric(self, *args: Any, **kwargs: Any):
        d = self.measure_manager.measures[DistanceToGoal.cls_uuid].get_metric()
        self._metric = float(self._metric or d < self._success_distance)


def add_measurement(env, episode, measure_names=["PathLength", "DistanceToGoal", "Success", "SPL", "OracleNavigationError", "OracleSuccess"]):
    measure_manager = MeasureManager()
    for measure_name in measure_names:
        measure = eval(measure_name)(env, episode, measure_manager)
        measure_manager.register_measure(measure)
    
    return measure_manager