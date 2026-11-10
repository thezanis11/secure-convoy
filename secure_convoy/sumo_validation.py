"""Closed-loop SUMO cross-engine consistency with shared actuator assumptions.

SUMO's built-in safety intervention is explicitly disabled: otherwise it could
mask the collisions our controller/security experiment is intended to measure.
This validates integration and closed-loop consistency, not real-road fidelity.
"""
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import uuid

import numpy as np
import pandas as pd

from .simulation import Config, CONTROLLERS, integrate, simulate

ROOT = Path(__file__).resolve().parents[1]


class SumoPlant:
    def __init__(self, config):
        import sumolib
        import traci
        self.cfg = config
        self.connection = None
        folder = ROOT/'data/sumo'
        folder.mkdir(parents=True, exist_ok=True)
        nodes = folder/'road.nod.xml'
        edges = folder/'road.edg.xml'
        net = folder/'road.net.xml'
        nodes.write_text('<nodes><node id="a" x="0" y="0"/><node id="b" x="6000" y="0"/></nodes>', encoding='utf-8')
        edges.write_text('<edges><edge id="road" from="a" to="b" numLanes="1" speed="60"/></edges>', encoding='utf-8')
        if not net.exists():
            subprocess.run([sumolib.checkBinary('netconvert'), '-n', str(nodes), '-e', str(edges), '-o', str(net)], check=True, capture_output=True)
        label = 'convoy-' + uuid.uuid4().hex[:12]
        args = [sumolib.checkBinary('sumo'), '-n', str(net), '--step-length', str(config.dt),
                '--step-method.ballistic', 'true', '--collision.action', 'warn', '--collision.mingap-factor', '0',
                '--time-to-teleport', '-1', '--no-step-log', 'true', '--no-warnings', 'true',
                '--duration-log.disable', 'true', '--seed', '42']
        traci.start(args, label=label, doSwitch=False, stdout=subprocess.DEVNULL, numRetries=3)
        self.connection = traci.getConnection(label)
        self.connection.route.add('route', ['road'])
        self.connection.vehicletype.copy('DEFAULT_VEHTYPE', 'convoy')
        self.connection.vehicletype.setTau('convoy', 0.05)
        self.connection.vehicletype.setMinGap('convoy', 0)
        self.connection.vehicletype.setLength('convoy', config.vehicle_length)
        self.connection.vehicletype.setDecel('convoy', 9)
        self.connection.vehicletype.setEmergencyDecel('convoy', 9)
        self.ids = [f'vehicle-{i}' for i in range(config.vehicles)]
        for i, vehicle in enumerate(self.ids):
            gap = 3 + config.initial_headway*config.initial_speed
            position = 1000 - i*(gap+config.vehicle_length)
            self.connection.vehicle.add(vehicle, 'route', typeID='convoy', departPos=str(position), departSpeed=str(config.initial_speed))
        for _ in range(100):
            self.connection.simulationStep()
            if set(self.ids).issubset(self.connection.vehicle.getIDList()):
                break
        else:
            self.close()
            raise RuntimeError('SUMO did not insert the complete platoon')
        for i, vehicle in enumerate(self.ids):
            self.connection.vehicle.setLength(vehicle, config.vehicle_length)
            self.connection.vehicle.setMinGap(vehicle, 0)
            self.connection.vehicle.setSpeedMode(vehicle, 0)
            self.connection.vehicle.setLaneChangeMode(vehicle, 0)
            self.connection.vehicle.moveTo(vehicle, 'road_0', 1000-i*(gap+config.vehicle_length))
            self.connection.vehicle.setSpeed(vehicle, config.initial_speed)
            self.connection.vehicle.setPreviousSpeed(vehicle, config.initial_speed, 0)
        self.version = self.connection.getVersion()

    def step(self, x, v, a, command, lag, brake, dt, jerk_limit):
        _, requested_v, requested_a = integrate(x, v, a, command, lag, brake, dt, jerk_limit)
        for vehicle, speed in zip(self.ids, requested_v):
            self.connection.vehicle.setSpeed(vehicle, float(speed))
        self.connection.simulationStep()
        actual_x = np.array([self.connection.vehicle.getLanePosition(vehicle)-1000 for vehicle in self.ids])
        actual_v = np.array([self.connection.vehicle.getSpeed(vehicle) for vehicle in self.ids])
        if not np.isfinite(actual_x).all() or np.any(actual_v < 0):
            raise RuntimeError('Invalid SUMO state; a vehicle may be missing')
        # Physical actuator state remains shared; SUMO handles vehicle movement.
        return actual_x, actual_v, requested_a

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def validate(seeds=(1000, 1001)):
    cfg = Config()
    out = ROOT/'reports'
    out.mkdir(exist_ok=True)
    records = []
    version = None
    for scenario in ('emergency_brake', 'external_spoof', 'insider_spoof', 'replay'):
        for controller in CONTROLLERS:
            for seed in seeds:
                reference, _ = simulate(seed, scenario, controller, cfg)
                plant = SumoPlant(cfg)
                try:
                    measured, _ = simulate(seed, scenario, controller, cfg, plant_step=plant.step)
                    version = plant.version
                finally:
                    plant.close()
                records.append(dict(scenario=scenario, controller=controller, seed=seed,
                                    reference_collision=reference['collision'], sumo_collision=measured['collision'],
                                    reference_min_gap=reference['min_gap_m'], sumo_min_gap=measured['min_gap_m'],
                                    min_gap_difference=measured['min_gap_m']-reference['min_gap_m']))
                print(f'SUMO {len(records)}/32: {scenario} / {controller} / {seed}', flush=True)
    frame = pd.DataFrame(records)
    frame.to_csv(out/'sumo_validation.csv', index=False)
    manifest = dict(sumo_version=version, config=asdict(cfg), runs=len(frame),
                    collision_agreement=float((frame.reference_collision == frame.sumo_collision).mean()),
                    max_abs_min_gap_difference=float(frame.min_gap_difference.abs().max()),
                    interpretation='closed-loop cross-engine consistency; actuator model, controllers and sensor assumptions shared',
                    sumo_safety_override='speedMode 0, laneChangeMode 0, collision.action warn; no automatic safety rescue',
                    independent_validation_limits='does not independently validate actuator physics, radio stack, sensors or real-road safety')
    (out/'sumo_experiment.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    validate()
