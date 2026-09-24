# Robot memory

Evidence-bound observations and hypotheses, not hidden reasoning.

## Pixel projection can be unreachable or poorly conditioned

Applies to: push-v3, peg-insert-side-v3, *

Pixel targets repeatedly produced outside_workspace, target_not_reached, or motion_stalled, especially when the projected point was near a boundary or required an inferred depth. Treat move_to_pixel as a surface/above reach only, not as a free-space waypoint or reliable contact-pose estimator; use fresh observations and conservative follow-up motions.

Evidence: episodes/cycle-1-discover/c1t1-s11-combined, episodes/cycle-1-validate/c1t1-s31-combined, episodes/cycle-1-discover/c1t3-s11-combined

## TCP reach and forward motion do not verify a full press

Applies to: button-press-v3

Repeated successful TCP reaches and small forward motions did not establish a verified button press, and retries consumed decision/control budget. A reached TCP target is not evidence that contact occurred or that the button reached its terminal state; use a short, explicit contact-plus-inward sequence and validate from the task outcome.

Evidence: episodes/cycle-1-discover/c1t2-s11-combined, episodes/cycle-1-validate/c1t2-s31-baseline, episodes/cycle-1-validate/c1t2-s31-combined

## Gripper closure is not grasp confirmation

Applies to: peg-insert-side-v3, pick-place-v3

Closing the gripper returned grasp_verified=false in peg and pick-place attempts. Do not infer grasp, lift, transport, or placement success from closure or TCP motion; treat grasp as unverified unless the environment outcome visibly confirms object movement and placement.

Evidence: episodes/cycle-1-discover/c1t3-s11-combined, episodes/cycle-1-validate/c1t3-s31-combined, episodes/cycle-2-discover/c2t3-s11-combined

## Handle approach and contact are the bottleneck before pulling

Applies to: door-open-v3, drawer-open-v3

Door and drawer approaches often stalled during descent or pixel reaching, even when later relative motions could execute. Contact tasks need clearance-aware, incremental approach motions; large pull motions are only meaningful after a reachable handle pose is established.

Evidence: episodes/cycle-2-discover/c2t1-s11-combined, episodes/cycle-2-discover/c2t2-s11-combined

## Agent completion summaries do not establish environment success

Applies to: drawer-open-v3

The drawer episode ended unsuccessfully despite a sequence of successful approach, closure, and backward motions; the episode summary asserted visible opening, but environment_success remained false. Treat agent-reported completion and TCP step success as hypotheses, not task validation.

Evidence: episodes/cycle-2-discover/c2t2-s11-combined

## Open-loop transport can exhaust budget before placement

Applies to: pick-place-v3

Pick-place reached and closed on the object, then transported through several relative moves, but a later transport step returned target_not_reached and the tool protocol failed before placement. Long open-loop transports are vulnerable to workspace and budget limits; split transport conservatively and reserve steps for target placement and release.

Evidence: episodes/cycle-2-discover/c2t3-s11-combined
