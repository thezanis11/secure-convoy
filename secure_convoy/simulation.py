"""Longitudinal platoon, causal delayed messages and layered defensive control.

This is a research model, not a safety-certified controller. State truth is used
only by the plant, metrics and the emulated sensors; controllers receive radar
measurements and packets available at the current simulation time.
"""
from dataclasses import dataclass, asdict
import hashlib
import heapq
import hmac
import json
import math

import numpy as np


@dataclass(frozen=True)
class Config:
    vehicles: int = 7
    duration: float = 42.0
    dt: float = 0.05
    message_period: float = 0.1
    vehicle_length: float = 4.5
    initial_speed: float = 27.0
    initial_headway: float = 0.75
    max_acceleration: float = 2.5
    radar_gap_noise: float = 0.15
    radar_speed_noise: float = 0.10
    packet_ttl: float = 0.40


SCENARIOS = ('clean', 'emergency_brake', 'network_degraded', 'external_spoof',
             'insider_spoof', 'replay', 'outage', 'subtle_insider')
CONTROLLERS = ('local_acc', 'trusting_cacc', 'authenticated_cacc', 'defended_cacc')
ABLATIONS = ('without_auth', 'without_consistency', 'without_supervisor')


def key_for(sender):
    # Public deterministic DEMO keys for reproducibility, never deployment keys.
    return hashlib.sha256(f'secure-convoy-public-demo-key:{sender}'.encode()).digest()


def canonical(packet):
    fields = {k: packet[k] for k in ('sender', 'sequence', 'sent_at', 'position', 'speed', 'acceleration')}
    return json.dumps(fields, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sign(packet):
    result = dict(packet)
    result['tag'] = hmac.new(key_for(packet['sender']), canonical(packet), hashlib.sha256).hexdigest()
    return result


def authenticate(packet, sender, now, last_sequence, ttl):
    try:
        if packet['sender'] != sender:
            return 'sender'
        if not all(math.isfinite(float(packet[k])) for k in ('sent_at', 'position', 'speed', 'acceleration')):
            return 'nonfinite'
        expected = hmac.new(key_for(sender), canonical(packet), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(packet['tag'], expected):
            return 'signature'
        if packet['sequence'] <= last_sequence:
            return 'replay'
        if now - packet['sent_at'] > ttl or packet['sent_at'] > now + 0.05:
            return 'freshness'
        return None
    except (KeyError, ValueError, TypeError):
        return 'malformed'


def lead_command(t, scenario):
    if scenario == 'clean':
        return 0.45 * math.sin(t / 4)
    if 15 <= t < 18:
        return -7.5
    if 22 <= t < 31:
        return 1.8
    return 0.0


def safety_bound(gap, own_speed, front_speed, headway=1.05, gain=1.2):
    """First-order headway barrier command bound (no formal noisy-plant guarantee)."""
    barrier = gap - 3.0 - headway * own_speed
    return (front_speed - own_speed + gain * barrier) / headway


def integrate(x, v, a, command, lag, brake, dt, jerk_limit):
    """Exact constant-acceleration step with nonnegative speed and stopping time."""
    derivative = np.clip((command - a) / lag, -jerk_limit, jerk_limit)
    new_a = np.clip(a + derivative * dt, -brake, 2.5)
    moving_time = np.full(len(v), dt)
    stopping = (new_a < 0) & (v + new_a * dt < 0)
    moving_time[stopping] = -v[stopping] / new_a[stopping]
    new_x = x + v * moving_time + 0.5 * new_a * moving_time ** 2
    new_v = np.maximum(0.0, v + new_a * dt)
    return new_x, new_v, new_a


def simulate(seed=0, scenario='clean', controller='defended_cacc', config=None, trace=False, plant_step=None):
    cfg = config or Config()
    advance = plant_step or integrate
    if scenario not in SCENARIOS or controller not in CONTROLLERS + ABLATIONS:
        raise ValueError('Unknown scenario or controller')
    if cfg.dt <= 0 or cfg.dt > cfg.message_period or cfg.vehicles < 2:
        raise ValueError('Invalid time step or platoon size')
    # Independent RNG streams keep plant/radar/network comparable across policies.
    plant_rng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
    radar_rng = np.random.default_rng(np.random.SeedSequence([seed, 2]))
    net_rng = np.random.default_rng(np.random.SeedSequence([seed, 3]))
    n = cfg.vehicles
    lag = plant_rng.uniform(0.18, 0.35, n)
    brake = plant_rng.uniform(7.0, 8.5, n)
    brake[0] = 8.5
    gap0 = 3 + cfg.initial_headway * cfg.initial_speed
    x = -np.arange(n, dtype=float) * (gap0 + cfg.vehicle_length)
    v = np.full(n, cfg.initial_speed)
    a = np.zeros(n)
    packet = [None] * n
    last_sequence = [-1] * n
    history = [[] for _ in range(n)]
    queue = []
    serial = sequence = 0
    received = rejected = attack_sent = attack_accepted = benign_rejected = 0
    consistency_rejections = supervisor_steps = 0
    reject_reasons = {}
    min_gap = float('inf')
    min_ttc = float('inf')
    spacing_sq = speed_sq = jerk_sq = 0.0
    sample_count = 0
    follower_energy = np.zeros(n-1)
    leader_energy = 0.0
    collided = np.zeros(n-1, dtype=bool)
    first_collision = None
    frames = []
    security = controller in ('authenticated_cacc', 'defended_cacc', 'without_consistency', 'without_supervisor')
    consistency = controller in ('defended_cacc', 'without_auth', 'without_supervisor')
    supervisor = controller in ('defended_cacc', 'without_auth', 'without_consistency')
    next_broadcast = 0.0
    for step in range(int(round(cfg.duration / cfg.dt))):
        t = step * cfg.dt
        gaps = x[:-1] - x[1:] - cfg.vehicle_length
        radar_gap = gaps + radar_rng.normal(0, cfg.radar_gap_noise, n-1)
        front_speed = np.maximum(0, v[:-1] + radar_rng.normal(0, cfg.radar_speed_noise, n-1))
        if t + 1e-9 >= next_broadcast:
            for follower in range(1, n):
                sender = follower - 1
                current = sign(dict(sender=sender, sequence=sequence, sent_at=t,
                                    position=float(x[sender]), speed=float(v[sender]), acceleration=float(a[sender])))
                history[follower].append(current)
                old = history[follower][-9] if len(history[follower]) >= 9 else current
                outgoing = dict(current)
                attack = follower == 1 and 12 <= t < 22 and scenario in ('external_spoof', 'insider_spoof', 'replay', 'subtle_insider')
                if attack:
                    attack_sent += 1
                    if scenario == 'replay':
                        outgoing = dict(old)
                    else:
                        outgoing['speed'] += 10.0 if scenario != 'subtle_insider' else 0.4
                        outgoing['acceleration'] = 5.0 if scenario != 'subtle_insider' else 2.0
                        outgoing['position'] += 30.0 if scenario != 'subtle_insider' else 0.0
                        if scenario in ('insider_spoof', 'subtle_insider'):
                            outgoing = sign(outgoing)
                drop = 0.30 if scenario == 'network_degraded' else 0.02
                delay = max(0.0, net_rng.normal(0.23, 0.10) if scenario == 'network_degraded' else net_rng.normal(0.045, 0.015))
                lost = net_rng.random() < drop
                if scenario == 'outage' and 12 <= t < 22:
                    lost = True
                if not lost:
                    heapq.heappush(queue, (t + delay, serial, follower, outgoing, attack))
                    serial += 1
            sequence += 1
            next_broadcast += cfg.message_period
        while queue and queue[0][0] <= t + 1e-9:
            _, _, follower, incoming, attack = heapq.heappop(queue)
            received += 1
            reason = authenticate(incoming, follower-1, t, last_sequence[follower], cfg.packet_ttl) if security else None
            if reason is None and consistency:
                age = max(0, t - incoming['sent_at'])
                expected_gap = incoming['position'] + incoming['speed'] * age - x[follower] - cfg.vehicle_length
                speed_error = abs(incoming['speed'] - front_speed[follower-1])
                gap_error = abs(expected_gap - radar_gap[follower-1])
                if speed_error > 1.0 + 9.0 * age or gap_error > 1.0 + 0.5 * 9 * age ** 2:
                    reason = 'radar_consistency'
                    consistency_rejections += 1
            if reason is not None:
                rejected += 1
                benign_rejected += int(not attack)
                reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
            else:
                packet[follower] = incoming
                last_sequence[follower] = incoming['sequence']
                attack_accepted += int(attack)
        command = np.zeros(n)
        command[0] = lead_command(t, scenario)
        for follower in range(1, n):
            message = packet[follower]
            fresh = message is not None and (not security or t - message['sent_at'] <= cfg.packet_ttl)
            cooperative = controller != 'local_acc' and fresh
            headway = 0.75 if cooperative else 1.2
            desired_gap = 3 + headway * v[follower]
            observed_front = front_speed[follower-1]
            feedforward = 0.0
            if cooperative:
                # Trusting/auth-only policies use the communicated state;
                # defended control anchors relative speed to local radar.
                if not consistency:
                    observed_front = message['speed']
                feedforward = 0.85 * message['acceleration']
            proposed = 0.45 * (radar_gap[follower-1] - desired_gap) + 0.9 * (observed_front - v[follower]) + feedforward
            if supervisor:
                bound = safety_bound(radar_gap[follower-1] - 0.5, v[follower], front_speed[follower-1])
                if proposed > bound:
                    supervisor_steps += 1
                    proposed = bound
                stopping_gap = 3 + 0.35 * v[follower] + max(0, v[follower]**2 / (2*6.5) - front_speed[follower-1]**2 / (2*9.0))
                if radar_gap[follower-1] < stopping_gap:
                    proposed = min(proposed, -6.5)
            command[follower] = np.clip(proposed, -brake[follower], cfg.max_acceleration)
        old_a = a.copy()
        # Every policy has the same physical actuator/jerk capability.
        x, v, a = advance(x, v, a, command, lag, brake, cfg.dt, 25.0)
        new_gaps = x[:-1] - x[1:] - cfg.vehicle_length
        min_gap = min(min_gap, float(new_gaps.min()))
        newly_collided = new_gaps <= 0
        collided |= newly_collided
        if newly_collided.any() and first_collision is None:
            first_collision = t + cfg.dt
        closing = v[1:] - v[:-1]
        dangerous = (closing > 0.1) & (new_gaps > 0)
        if dangerous.any():
            min_ttc = min(min_ttc, float((new_gaps[dangerous] / closing[dangerous]).min()))
        spacing_sq += float(np.sum((new_gaps - (3 + 0.75*v[1:]))**2))
        speed_sq += float(np.sum((v[1:] - v[0])**2))
        jerk_sq += float(np.sum(((a[1:] - old_a[1:]) / cfg.dt)**2))
        sample_count += n-1
        leader_energy += a[0]**2 * cfg.dt
        follower_energy += a[1:]**2 * cfg.dt
        if trace:
            for i in range(n):
                frames.append(dict(time=t+cfg.dt, vehicle=i, position=float(x[i]), speed=float(v[i]),
                                   acceleration=float(a[i]), command=float(command[i]),
                                   gap=None if i == 0 else float(new_gaps[i-1])))
        # After physical contact the independent-vehicle model no longer models
        # dynamics correctly. Stop rather than let cars pass through each other.
        if collided.any():
            break
    result = dict(seed=seed, scenario=scenario, controller=controller,
                  collision=bool(collided.any()), collision_pairs=int(collided.sum()),
                  first_collision_seconds=first_collision, simulated_seconds=(step+1)*cfg.dt,
                  min_gap_m=min_gap, min_ttc_seconds=None if not math.isfinite(min_ttc) else min_ttc,
                  spacing_rmse_m=math.sqrt(spacing_sq/sample_count),
                  speed_tracking_rmse_mps=math.sqrt(speed_sq/sample_count),
                  jerk_rms_mps3=math.sqrt(jerk_sq/sample_count),
                  max_acceleration_energy_gain=float(np.max(follower_energy/max(leader_energy, 1e-9))),
                  packets_received=received, packets_rejected=rejected,
                  benign_packets_rejected=benign_rejected,
                  attack_packets_sent=attack_sent, attack_packets_accepted=attack_accepted,
                  consistency_rejections=consistency_rejections, supervisor_steps=supervisor_steps,
                  rejection_reasons=reject_reasons)
    return result, frames
