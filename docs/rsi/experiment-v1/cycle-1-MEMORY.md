# Robot memory

Evidence-bound observations and hypotheses, not hidden reasoning.

## Treat pixel reachability as unverified

Applies to: push-v3, peg-insert-side-v3

Pixel-selected targets can be unreachable or outside the workspace under yaw or low-light views. Treat move_to_pixel failure as a hard branch and do not issue dependent actions as if contact occurred.

Evidence: episodes/cycle-1-discover/c1t1-s11-combined, episodes/cycle-1-discover/c1t3-s11-combined

## Do not equate TCP motion with task completion

Applies to: button-press-v3

Repeated small forward motions do not establish button contact or completion. Use visual re-observation and a bounded retry policy, and judge success from the final state rather than tool completion.

Evidence: episodes/cycle-1-discover/c1t2-s11-combined

## Keep grasp status explicitly unverified

Applies to: peg-insert-side-v3

Gripper closure is not evidence of a grasp, and insertion should not be planned as though the peg is held. Verify task-relevant object motion or use conservative bounded actions.

Evidence: episodes/cycle-1-discover/c1t3-s11-combined
