# Model, controls and threat assumptions

## State, dynamics and sensors

Each vehicle has longitudinal front-bumper position x, speed v and acceleration a. The free bumper gap is `g_i = x_(i-1) - x_i - L`, with `L = 4.5 m`.

The actuator approaches a requested command u through a first-order lag: `da/dt = clip((u-a)/tau, -25, 25)`. Acceleration is saturated between the vehicle's braking limit and 2.5 m/s². The same limits apply to every policy. Tau is drawn uniformly from 0.18–0.35 s, braking capacity from 7.0–8.5 m/s², with a leader limit of 8.5 m/s².

Positions use a constant-acceleration ballistic step. A stopping-time correction prevents a vehicle with small positive speed from moving backwards or integrating beyond its stopping point. The simulation stops at the first gap <= 0, because independent free-vehicle dynamics no longer describe a crash.

Radar measures gap and predecessor speed with independent Gaussian standard deviations 0.15 m and 0.10 m/s. This is an emulated measurement model, not a real radar dataset. Independent random streams separate plant parameters, sensor noise and network behavior. Physical samples are comparable across policies sharing a seed.

## Controllers

The cooperative proposal is `u = 0.45*(measured_gap - 3 - h*v) + 0.9*(front_speed - v) + 0.85*front_acceleration`.

With a usable packet, h = 0.75 s. Local ACC or fallback uses h = 1.2 s and no feed-forward. Trusting and authenticated-only CACC use the communicated predecessor speed. The consistency-based variants anchor relative speed to local radar instead. Consequently the consistency ablation includes this sensor-choice change; it is not merely a different rejection threshold.

The headway supervisor forms `b = measured_gap - 0.5 - 3 - 1.05*v` and caps acceleration by `(front_speed - v + 1.2*b)/1.05`. It also compares gap to a conservative stopping-distance expression using 0.35 s reaction allowance, 6.5 m/s² ego braking and 9 m/s² predecessor braking. It can request strong braking when the margin is violated.

This resembles a first-order barrier condition, but it is not a proof of robust safety for the noisy lagged plant. The extra buffer, braking rule and fallback are stated explicitly. Parameters were fixed before the final grid; no optimization against test collisions was performed.

## Messages and attacker capabilities

Every 100 ms, a sender broadcasts ID, monotonically increasing sequence, simulation timestamp, position, speed and acceleration. Canonical JSON is authenticated with HMAC-SHA256. Demo keys are public deterministic values. Freshness allows at most 400 ms age and 50 ms future skew. A rejection never advances the accepted sequence counter.

Normal links have 45 ms mean delay, 15 ms standard deviation and 2% loss. The degraded scenario uses 230 ms mean, 100 ms standard deviation and 30% loss. Arrival events are processed from a causal heap. Reusing an accepted packet between broadcasts is distinct from accepting a replayed arrival.

| Scenario | Attacker / fault | Capability |
|---|---|---|
| clean | none | mild sinusoidal leader acceleration |
| emergency_brake | none | leader braking from 15 to 18 s |
| network_degraded | network fault | delay, losses and reordering |
| external_spoof | outsider | modify first follower's predecessor state, no valid signing key |
| insider_spoof | compromised sender | forge speed/position/acceleration and compute a valid tag |
| replay | observer | resend an old authentic message, not regenerate its sequence or timestamp |
| outage | network fault | all messages lost from 12 to 22 s |
| subtle_insider | compromised sender | small speed bias and false acceleration, intended to probe consistency limits |

Attacks run from 12 to 22 s. The insider cases deliberately give the adversary the first sender's key. This separates cryptographic authenticity from physical truth. No real traffic is intercepted or injected.

## Evaluation and uncertainty

The final primary grid uses seeds 1000–1031, all eight scenarios and all four policies. Development seeds are separate. Checkpoints are tied to the simulation source, configuration and task list by SHA256. All prescribed cases are retained, including failures.

Collision frequency gets a Wilson interval per cell. Collision-rate reduction relative to trusting CACC is bootstrapped over matched seeds. Degenerate bootstrap intervals on identical outcomes do not establish certainty; Wilson intervals and model limitations must also be read.

The reported spacing RMSE compares gaps to a common compactness reference `3 + 0.75*v`. It is not the tracking error against local ACC's 1.2 s target. RMS jerk quantifies acceleration variation; collisions shorten its horizon. The acceleration-energy amplification proxy is not a formal transfer-function or string-stability result.

The 36 time-step trials examine numerical sensitivity. SUMO validation uses a shared actuator model and ballistic motion, disables SUMO safety rescue, checks all vehicles are inserted, and runs the same controller in feedback from SUMO state. Near-roundoff agreement is expected; this is cross-engine software consistency rather than independent physical validation.
